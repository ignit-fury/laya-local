# Laya Local Server

Run the open-source [Laya](https://github.com/NandhaKishorM/laya) decision model entirely on your own machine — no cloud API, no data leaves your device.

<p align="center">
  <img src="https://img.shields.io/badge/Laya-convaiinnovations-blue?logo=github&logoColor=white" alt="Laya">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/platform-macOS%20ARM%20%7C%20Linux%20ARM%20%7C%20Linux%20x86-lightgrey" alt="Platforms">
</p>

---

## What it does

Laya is a 421M-parameter **decision model** — not a chatbot. You give it a piece of text and a yes/no question, and it returns a **calibrated probability** (0.0–1.0) in a single forward pass. It never generates text, so there's nothing to hallucinate.

This server wraps the [typed-decisions checkpoint](https://huggingface.co/codenamev/laya-onnx) in a local FastAPI API so your browser extension, script, or app can classify page content locally.

| Endpoint | What it does |
|---|---|
| `POST /classify` | Send text → get back a probability score |
| `GET /health` | Check if the model is loaded and see resource usage |
| `POST /reload` | Reload the model (after updates) |

## Quick start (macOS)

```bash
# 1. Clone and enter the directory
git clone https://github.com/ignit-fury/laya-local.git
cd laya-local

# 2. Run the setup script — creates a venv, installs deps, starts the server
./setup_mac.sh
```

The server starts at **http://localhost:8765**. The model downloads automatically on first run (~800 MB).

## Manual setup

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn laya_server:app --host 127.0.0.1 --port 8765
```

## API reference

### `POST /classify`

Classify text with a calibrated probability.

**Request:**
```json
{
  "text": "Photosynthesis is the process by which green plants use sunlight...",
  "question": "Is this about biology?"
}
```

**Response:**
```json
{
  "probability": 0.8732,
  "inference_time_ms": 127.3,
  "question": "Is this about biology?",
  "text_length": 1234,
  "tokens_used": 512,
  "model_ram_mb": 2240
}
```

### `GET /health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_info": {
    "model_repo": "codenamev/laya-onnx",
    "file_size_mb": 806.9,
    "tokenizer_vocab": 50280,
    "providers": ["CoreMLExecutionProvider", "CPUExecutionProvider"],
    "load_time_s": 4.2,
    "ram_mb": 2149.0,
    "total_ram_mb": 2242.8
  },
  "process_ram_mb": 2250,
  "system_free_ram_mb": 14800,
  "uptime_s": 45.3
}
```

## Using from a browser extension

The server runs on `localhost`, so a browser extension can call it from a background script or service worker:

```javascript
// Background script / service worker
const text = await getPageText();  // however you extract page content

const resp = await fetch("http://localhost:8765/classify", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    text: text,
    question: "Is this a study-relevant page?"
  })
});

const result = await resp.json();
console.log("Relevance probability:", result.probability);
```

**Note for Manifest V3:** The background script needs host permission for `http://localhost:8765/`. Add this to `manifest.json`:

```json
"host_permissions": [
  "http://localhost:8765/"
]
```

Also add an error check — if the server isn't running, the fetch will fail:

```javascript
if (!resp.ok) {
  console.error("Laya server not available:", await resp.text());
  // Fall back to a simpler heuristic or ask the user to start the server
}
```

## Hardware requirements

| Platform | Minimum | Recommended |
|---|---|---|
| macOS (Apple Silicon) | M1, 8 GB RAM | M2/M3/M4, 16 GB RAM |
| Linux (x86_64) | 4 GB RAM, any CPU | 8 GB RAM, multi-core |
| Linux (ARM) | 4 GB RAM, any CPU | 8 GB RAM, multi-core |

**RAM usage:** ~2.1 GB for the model + tokenizer (FP32). If you're tight on memory, consider using the quantized version.

**Inference speed:** sub-100ms on Apple Silicon GPU (CoreML/Metal), ~12s on a single ARM core without GPU. Speed varies significantly with hardware.

## Browser extension

A companion browser extension (Manifest V3, Chrome + Firefox) is included in the `extension/` directory. It extracts page text and sends it to the local Laya server for classification.

### Files

```
extension/
├── manifest.json    — Extension manifest (host permissions, content script, popup)
├── background.js    — Service worker: talks to Laya server, handles messages
├── content.js       — Content script: extracts page text, polls for results
├── popup.html       — Popup UI: server status, classification result, action button
├── popup.js         — Popup logic: health checks, result display, polling
└── icons/           — Extension icons (16, 48, 128 px)
```

### Setup

The extension is a separate load — it's not bundled with the server.

**Chrome / Chromium:**

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** and select the `extension/` directory
4. The Laya icon appears in your toolbar

**Firefox:**

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select `extension/manifest.json`

### How it works

```
[Page] → content.js extracts text
         → background.js receives via chrome.runtime.sendMessage
         → background.js fetches http://localhost:8765/classify
         → result returned to popup via chrome.storage.session
```

### Manifest permissions

The extension requires `http://localhost:8765/` in `host_permissions` so the background service worker can fetch from the local server. No other permissions are needed — the content script reads page text directly from the DOM (no extra permissions required).

### Popup UI

Click the Laya icon in the toolbar to open the popup:

- **Server status** — green dot if the server is running, red if not
- **Classify This Page** — extracts text from the active tab and sends it for classification
- **Result** — shows probability score with color-coded bar (green ≥ 0.7, yellow ≥ 0.4, red < 0.4)
- **Inference time** — how long the forward pass took

### Development

The extension is tied to the server running on `localhost:8765`. To test:

1. Start the server: `uvicorn laya_server:app --host 127.0.0.1 --port 8765`
2. Load the extension unpacked in Chrome/Firefox
3. Open any page, click the Laya icon, click **Classify This Page**

## Model details

- **Model:** Laya typed-decisions checkpoint (Convai Innovations)
- **Architecture:** ModernBERT-large encoder + decision head (421M parameters)
- **License:** Apache 2.0
- **Source:** [github.com/NandhaKishorM/laya](https://github.com/NandhaKishorM/laya)
- **ONNX export:** [codenamev/laya-onnx](https://huggingface.co/codenamev/laya-onnx)

### What "typed decisions" means

Laya answers three kinds of questions, all defined at request time with **no retraining needed**:

| Type | Description | Example |
|---|---|---|
| **choice** | Pick one option from a list | "Which subject is this?" → Biology / History / Math |
| **score** | Rate on an ordinal scale | "How difficult is this?" → 0 / 1 / 2 / 3 |
| **noul** | Boolean probability | "Is this about biology?" → P(true) = 0.87 |

The server currently implements the `noul` primitive. Extending to `choice` and `score` is straightforward — you send different `qtype` values and more markers.

## Development

```bash
# Install dev dependencies
pip install pytest

# Run the example client (requires server running)
python src/client_example.py
```

## License

This wrapper is MIT-licensed. The underlying Laya model is Apache 2.0 — see the [original repo](https://github.com/NandhaKishorM/laya) for model-specific terms.

## Acknowledgments

- [Convai Innovations](https://github.com/NandhaKishorM/laya) — Laya model creators
- [codenamev](https://huggingface.co/codenamev/laya-onnx) — ONNX export
- [ONNX Runtime](https://onnxruntime.ai/) — inference engine
