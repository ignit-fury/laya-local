/*
 * Laya Study Mode — Content Script
 *
 * Extracts visible text from the current page and sends it to the
 * background service worker for classification via the local Laya server.
 */

const CLASSIFY_QUESTION = "Is this page study-relevant?";

// ── Helpers ────────────────────────────────────────────────────────────────

/** Extract meaningful text content from the page */
function extractPageText() {
  // Try to get main content areas first
  const main = document.querySelector("main");
  const article = document.querySelector("article");
  const body = document.body;

  // Pick the best container
  const container = main || article || body;
  if (!container) return "";

  // Clone to avoid modifying the live DOM
  const clone = container.cloneNode(true);

  // Remove non-text elements
  const removable = clone.querySelectorAll(
    "script, style, noscript, iframe, canvas, svg, video, audio, picture, img, navigation, nav, footer, header, aside, .ads, .ad, .nav, .menu, .button, .btn, .link"
  );
  removable.forEach(el => el.remove());

  // Get text, clean up whitespace
  let text = clone.textContent || "";
  text = text.replace(/\s+/g, " ").trim();

  // Truncate to a reasonable size for the model (max 4000 chars for the API)
  const MAX_CHARS = 3500;
  if (text.length > MAX_CHARS) {
    text = text.slice(0, MAX_CHARS) + "... [truncated]";
  }

  return text;
}

/** Send text to background for classification */
async function classifyPage() {
  const text = extractPageText();

  if (!text || text.length < 50) {
    console.log("[Laya CS] Page too short to classify:", text.length, "chars");
    return;
  }

  console.log("[Laya CS] Extracted", text.length, "chars from page");

  try {
    const response = await chrome.runtime.sendMessage({
      type: "LAYA_CLASSIFY",
      text: text,
      question: CLASSIFY_QUESTION,
    });

    if (response && response.success) {
      // Store the result so the popup can read it
      chrome.storage.session.set({
        layaResult: {
          probability: response.data.probability,
          inferenceTimeMs: response.data.inference_time_ms,
          question: response.data.question,
          timestamp: Date.now(),
        },
      });

      console.log("[Laya CS] Classification result:", response.data.probability);
    } else {
      console.warn("[Laya CS] Classification failed:", response?.error);
      chrome.storage.session.set({ layaError: response?.error });
    }
  } catch (err) {
    console.error("[Laya CS] Message failed:", err);
    chrome.storage.session.set({ layaError: err.message });
  }
}

// ── Expose to popup ────────────────────────────────────────────────────────

// Listen for requests from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "LAYA_GET_RESULT") {
    chrome.storage.session.get(["layaResult", "layaError"], (data) => {
      sendResponse(data);
    });
    return true;
  }

  if (message.type === "LAYA_CLASSIFY_NOW") {
    classifyPage();
    sendResponse({ started: true });
    return true;
  }
});
