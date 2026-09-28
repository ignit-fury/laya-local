/*
 * Laya Study Mode — Background Service Worker
 *
 * Listens for messages from content scripts, forwards page text to the
 * local Laya server, and returns classification results.
 *
 * The Laya server must be running on localhost:8765.
 * Start it with: uvicorn laya_server:app --host 127.0.0.1 --port 8765
 */

const LAYA_SERVER = "http://localhost:8765";
const CLASSIFY_TIMEOUT = 60_000; // 60s — generous for CPU fallback

// ── State ──────────────────────────────────────────────────────────────────

let serverAvailable = null; // null = unknown, true/false = cached result

// ── Startup: health check ──────────────────────────────────────────────────

async function checkServer_health() {
  try {
    const resp = await fetch(`${LAYA_SERVER}/health`, { signal: AbortSignal.timeout(5000) });
    if (resp.ok) {
      const data = await resp.json();
      serverAvailable = true;
      console.log("[Laya BG] Server healthy:", data.model_info?.providers?.join(", ") || "unknown");
      return true;
    }
  } catch (err) {
    serverAvailable = false;
    console.warn("[Laya BG] Server unreachable:", err.message);
    return false;
  }
}

// Check on startup (service workers can be woken up arbitrarily)
checkServer_health().then(healthy => {
  if (!healthy) {
    chrome.storage.local.set({ layaServerUp: false });
  }
});

// Periodic re-check every 60s in case the server was restarted
setInterval(checkServer_health, 60_000);

// ── Message handling ───────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "LAYA_CLASSIFY") {
    handleClassify(message.text, message.question, sendResponse);
    return true; // keep channel open for async response
  }

  if (message.type === "LAYA_IS_SERVER_UP") {
    sendResponse({ up: serverAvailable });
    return true;
  }

  if (message.type === "LAYA_PING") {
    sendResponse({ pong: Date.now() });
    return true;
  }
});

// ── Classification ─────────────────────────────────────────────────────────

async function handleClassify(text, question, sendResponse) {
  // Guard: empty text
  if (!text || text.trim().length === 0) {
    sendResponse({ success: false, error: "Empty text" });
    return;
  }

  // Guard: server not available
  if (serverAvailable === false) {
    sendResponse({ success: false, error: "Laya server is not running. Start it with setup_mac.sh" });
    return;
  }

  try {
    const resp = await fetch(`${LAYA_SERVER}/classify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, question: question || "" }),
      signal: AbortSignal.timeout(CLASSIFY_TIMEOUT),
    });

    if (!resp.ok) {
      const errBody = await resp.text();
      throw new Error(`Server returned ${resp.status}: ${errBody}`);
    }

    const result = await resp.json();
    sendResponse({ success: true, data: result });
  } catch (err) {
    serverAvailable = false; // likely crashed or stopped
    chrome.storage.local.set({ layaServerUp: false });
    console.error("[Laya BG] Classification failed:", err);
    sendResponse({
      success: false,
      error: err.name === "TimeoutError" ? "Classification timed out" : err.message,
    });
  }
}

// ── Commands from popup ────────────────────────────────────────────────────

chrome.action.onClicked.addListener(async (tab) => {
  // If server is down, try to wake the user
  if (serverAvailable === false) {
    chrome.storage.local.get("layaServerUp", (data) => {
      chrome.tabs.create({
        url: "popup.html",
        active: true,
      });
    });
  }
});
