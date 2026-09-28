"""
Laya Local Server — Run the open-source Laya decision model on your machine.

A lightweight FastAPI server that loads the Laya typed-decisions ONNX model
and serves classification inference via a simple HTTP API. Designed to run
locally so a browser extension or other local tool can call it without
sending data to any external service.

Requirements:
    pip install -r requirements.txt

Run:
    uvicorn laya_server:app --host 127.0.0.1 --port 8765

Or use the bundled setup script (macOS):
    ./setup_mac.sh

API:
    POST /classify   — classify text with a typed question
    GET  /health     — server health + model status
    POST /reload     — reload the model (after updating files)

Model:
    Downloads automatically from Hugging Face on first run.
    Repo: codenamev/laya-onnx (typed-decisions checkpoint)
    License: Apache 2.0
"""

import os
import time
import logging
import psutil
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from huggingface_hub import hf_hub_download
import onnxruntime as ort
from transformers import AutoTokenizer

# ── Configuration ──────────────────────────────────────────────────────────

MODEL_REPO = "codenamev/laya-onnx"
MODEL_SUBFOLDER = "typed-decisions"
MODEL_FILENAME = "model.onnx"
TOKENIZER_SUBFOLDER = "typed-decisions/tokenizer"

HOST = "127.0.0.1"
PORT = 8765

# Where to cache the model. Set HF_HOME env var to change.
CACHE_DIR = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("laya-server")

# ── Model state ────────────────────────────────────────────────────────────

_model = None
_tokenizer = None
_session = None
_model_info = {}


def get_memory_mb():
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


# ── Model loading ──────────────────────────────────────────────────────────

def select_providers():
    """Pick the best available execution providers."""
    providers = ["CPUExecutionProvider"]
    available = ort.get_available_providers()
    log.info("Available ORT providers: %s", available)

    if "CoreMLExecutionProvider" in available:
        log.info("Using CoreML Execution Provider (Apple Silicon GPU)")
        providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    elif "MetalExecutionProvider" in available:
        log.info("Using Metal Execution Provider (Apple GPU)")
        providers = ["MetalExecutionProvider", "CPUExecutionProvider"]

    return providers


def download_model():
    """Download the model and tokenizer from Hugging Face if not cached."""
    log.info("Ensuring model files are cached...")

    model_path = hf_hub_download(
        repo_id=MODEL_REPO,
        repo_type="model",
        subdirectory=MODEL_SUBFOLDER,
        filename=MODEL_FILENAME,
    )
    log.info("Model: %s (%.1f MB)", model_path, os.path.getsize(model_path) / (1024 * 1024))

    return model_path


def load_model():
    """Load the Laya ONNX model and tokenizer into memory."""
    global _model, _tokenizer, _session, _model_info

    mem_before = get_memory_mb()
    t0 = time.time()

    log.info("Loading Laya model...")

    # Download (or use cached)
    model_path = download_model()

    # Tokenizer
    _tokenizer = AutoTokenizer.from_pretrained(
        MODEL_REPO, subfolder=TOKENIZER_SUBFOLDER
    )
    log.info("Tokenizer loaded: vocab=%d", _tokenizer.vocab_size)

    # ONNX session
    providers = select_providers()
    _session = ort.InferenceSession(
        str(model_path),
        providers=providers,
    )
    log.info("ONNX session created. Providers: %s", _session.get_providers())

    # Inspect I/O
    inputs = {inp.name: inp.shape for inp in _session.get_inputs()}
    outputs = {out.name: out.shape for out in _session.get_outputs()}
    _model_info = {
        "model_repo": MODEL_REPO,
        "model_path": str(model_path),
        "file_size_mb": round(os.path.getsize(model_path) / (1024 * 1024), 1),
        "tokenizer_vocab": _tokenizer.vocab_size,
        "providers": _session.get_providers(),
        "inputs": inputs,
        "outputs": outputs,
        "load_time_s": round(time.time() - t0, 2),
        "ram_mb": round(get_memory_mb() - mem_before, 1),
    }
    _model_info["total_ram_mb"] = round(get_memory_mb(), 1)

    log.info(
        "Model loaded in %.1fs. RAM: %s MB total, %s MB for model+tokenizer",
        time.time() - t0,
        _model_info["total_ram_mb"],
        _model_info["ram_mb"],
    )


# ── Inference ──────────────────────────────────────────────────────────────

def run_inference(text: str, question: str = "") -> dict:
    """
    Run a Laya 'noul' (boolean) inference on the given text.

    Returns a dict with:
        probability: P(true) for the question
        inference_time_ms: how long the forward pass took
        model_info: reference to model metadata
    """
    if _session is None or _tokenizer is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")

    # Tokenize
    tokens = _tokenizer(
        text,
        return_tensors="np",
        padding="max_length",
        max_length=512,
        truncation=True,
    )
    input_ids = tokens["input_ids"].astype(np.int64)
    attention_mask = tokens["attention_mask"].astype(np.int64)

    # Build marker inputs for a noul question
    seq_len = int(np.sum(attention_mask[0]))
    marker_pos = np.array([[seq_len - 1]], dtype=np.int64)
    marker_mask = np.array([[True, False]], dtype=bool)
    qtype = np.array([2], dtype=np.int64)  # 2 = noul

    feeds = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "marker_pos": marker_pos,
        "marker_mask": marker_mask,
        "qtype": qtype,
    }

    t0 = time.time()
    outputs = _session.run(None, feeds)
    elapsed_ms = (time.time() - t0) * 1000

    logits = outputs[0]  # [batch, markers]
    probability = float(1.0 / (1.0 + np.exp(-logits[0][0])))  # sigmoid

    return {
        "probability": round(probability, 4),
        "inference_time_ms": round(elapsed_ms, 1),
        "question": question or "Is this relevant?",
        "text_length": len(text),
        "tokens_used": seq_len,
    }


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Laya Local Server",
    description=(
        "Local inference server for the open-source Laya decision model. "
        "Classify text with calibrated probabilities — runs entirely on your machine."
    ),
    version="1.0.0",
)


# ── Startup ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Load the model when the server starts."""
    load_model()


# ── Endpoints ──────────────────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000,
                      description="Text to classify (up to 4000 chars)")
    question: str = Field("", description="Optional question context (for logging)")


class ClassifyResponse(BaseModel):
    probability: float = Field(..., description="Calibrated P(true) for the question")
    inference_time_ms: float = Field(..., description="Forward pass time in milliseconds")
    question: str = Field("", description="Question that was asked")
    text_length: int = Field(..., description="Length of input text in characters")
    tokens_used: int = Field(..., description="Number of tokens processed")
    model_ram_mb: int = Field(..., description="Total process RAM usage in MB")


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Server status")
    model_loaded: bool = Field(..., description="Whether the Laya model is loaded")
    model_info: dict = Field(..., description="Model metadata")
    process_ram_mb: int = Field(..., description="Process RAM usage")
    system_free_ram_mb: int = Field(..., description="System free RAM")
    uptime_s: float = Field(..., description="Server uptime in seconds")


class ReloadResponse(BaseModel):
    status: str = Field("ok", description="Reload status")
    message: str = Field(..., description="Human-readable status message")


@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest):
    """
    Classify a piece of text with a calibrated probability.

    Send raw text and get back a probability score. The model runs a
    single forward pass (~33ms on a GPU, slower on CPU) and returns
    a calibrated P(true) for the implicit question "Is this relevant?".

    No data leaves your machine — everything runs locally.
    """
    if _session is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        result = run_inference(req.text, req.question)
        result["model_ram_mb"] = round(get_memory_mb())
        return ClassifyResponse(**result)
    except Exception as e:
        log.error("Classification failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    """Check server health and model status."""
    import time as _time

    return HealthResponse(
        status="ok",
        model_loaded=_session is not None,
        model_info=_model_info,
        process_ram_mb=round(get_memory_mb()),
        system_free_ram_mb=round(psutil.virtual_memory().available / (1024 * 1024)),
        uptime_s=round(_time.time() - startup.__wrapped__.start_time
                       if hasattr(startup, '__wrapped__') else 0, 1),
    )


@app.post("/reload", response_model=ReloadResponse)
async def reload_model():
    """Reload the model — useful after updating model files."""
    global _session, _tokenizer, _model_info

    log.info("Reloading model...")
    _session = None
    _tokenizer = None
    _model_info = {}

    try:
        load_model()
        return ReloadResponse(
            status="ok",
            message=f"Model reloaded in {_model_info.get('load_time_s', '?')}s",
        )
    except Exception as e:
        log.error("Reload failed: %s", e)
        _session = None
        return ReloadResponse(
            status="error",
            message=f"Reload failed: {e}",
        )


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  LAYA LOCAL SERVER")
    print("=" * 60)
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  URL:  http://{HOST}:{PORT}")
    print("=" * 60)
    print()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
