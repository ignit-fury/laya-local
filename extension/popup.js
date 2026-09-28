/*
 * Laya Study Mode — Popup UI
 *
 * Shows server status and latest classification result.
 * Clicking "Classify This Page" triggers the content script to
 * extract page text and send it to the background worker.
 */

const SERVER_URL = "http://localhost:8765";

// ── DOM refs ───────────────────────────────────────────────────────────────

const serverDot    = document.getElementById("serverDot");
const serverText   = document.getElementById("serverText");
const resultSection = document.getElementById("resultSection");
const errorSection  = document.getElementById("errorSection");
const errorText     = document.getElementById("errorText");
const classifyBtn   = document.getElementById("classifyBtn");
const probValue     = document.getElementById("probValue");
const probFill      = document.getElementById("probFill");
const inferTime     = document.getElementById("inferTime");
const questionText  = document.getElementById("questionText");

// ── Initialize ─────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  // Check server health
  await checkServer();

  // Load any existing result from the content script
  const stored = await chrome.storage.session.get(["layaResult", "layaError"]);
  if (stored.layaResult) {
    showResult(stored.layaResult);
  }
  if (stored.layaError) {
    showError(stored.layaError);
  }

  // Button click → tell content script to classify
  classifyBtn.addEventListener("click", async () => {
    classifyBtn.disabled = true;
    classifyBtn.textContent = "Classifying...";

    // Clear previous result/error
    hideResult();
    hideError();

    try {
      // Send message to content script (active tab)
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      if (!tab) {
        showError("No active tab found");
        classifyBtn.disabled = false;
        classifyBtn.textContent = "Classify This Page";
        return;
      }

      // Send to content script
      const response = await chrome.tabs.sendMessage(tab.id, {
        type: "LAYA_CLASSIFY_NOW",
      });

      if (response?.started) {
        // Poll for result for up to 30s
        await pollForResult(tab.id);
      } else {
        showError("Content script not available on this page");
        classifyBtn.disabled = false;
        classifyBtn.textContent = "Classify This Page";
      }
    } catch (err) {
      showError(`Could not reach page: ${err.message}`);
      classifyBtn.disabled = false;
      classifyBtn.textContent = "Classify This Page";
    }
  });
});

// ── Server check ───────────────────────────────────────────────────────────

async function checkServer() {
  try {
    const resp = await fetch(`${SERVER_URL}/health`, {
      signal: AbortSignal.timeout(5000),
    });

    if (resp.ok) {
      const data = await resp.json();
      serverDot.className = "dot online";
      serverText.textContent = `Running on ${data.model_info?.providers?.join(", ") || "unknown"}`;
      serverText.style.color = "var(--good)";
      return true;
    }
  } catch (err) {
    // Server not reachable
  }

  serverDot.className = "dot offline";
  serverText.textContent = "Not running — start with ./setup_mac.sh";
  serverText.style.color = "var(--bad)";
  return false;
}

// ── Result display ─────────────────────────────────────────────────────────

function showResult(result) {
  resultSection.classList.remove("hidden");

  const p = result.probability;
  probValue.textContent = p.toFixed(4);

  // Color the probability bar
  probFill.style.width = `${p * 100}%`;
  if (p >= 0.7) {
    probFill.className = "prob-fill good";
  } else if (p >= 0.4) {
    probFill.className = "prob-fill mid";
  } else {
    probFill.className = "prob-fill low";
  }

  inferTime.textContent = `${result.inferenceTimeMs} ms`;
  questionText.textContent = result.question || "Is this page study-relevant?";
}

function hideResult() {
  resultSection.classList.add("hidden");
  probValue.textContent = "—";
  probFill.style.width = "0%";
  inferTime.textContent = "—";
  questionText.textContent = "—";
}

function showError(msg) {
  errorSection.classList.remove("hidden");
  errorText.textContent = msg;
  setTimeout(hideError, 8000);
}

function hideError() {
  errorSection.classList.add("hidden");
  errorText.textContent = "";
}

// ── Poll for classification result ─────────────────────────────────────────

async function pollForResult(tabId, attempts = 0) {
  if (attempts > 120) { // 60s total (500ms interval)
    showError("Classification timed out — server may be overloaded");
    classifyBtn.disabled = false;
    classifyBtn.textContent = "Classify This Page";
    return;
  }

  try {
    const response = await chrome.tabs.sendMessage(tabId, {
      type: "LAYA_GET_RESULT",
    });

    if (response?.layaResult) {
      showResult(response.layaResult);
      classifyBtn.disabled = false;
      classifyBtn.textContent = "Classify This Page";
      return;
    }

    if (response?.layaError) {
      showError(response.layaError);
      classifyBtn.disabled = false;
      classifyBtn.textContent = "Classify This Page";
      return;
    }

    // No result yet, wait and retry
    await new Promise(r => setTimeout(r, 500));
    await pollForResult(tabId, attempts + 1);
  } catch (err) {
    // Tab may have navigated away
    showError("Page navigated — try again");
    classifyBtn.disabled = false;
    classifyBtn.textContent = "Classify This Page";
  }
}
