/**
 * Native Messaging host bridge for Canvas Deadline Tracker.
 *
 * Manages a persistent chrome.runtime.connectNative connection to the
 * 'com.cs3704.canvas_tracker' host. Uses a single port with reconnect logic
 * and per-message id-based promise resolution.
 *
 * Wire protocol (host side):
 *   Outgoing: { id, method, token, baseUrl, params }
 *   Incoming: { id, ok, data } | { id, ok, error }
 */

const HOST_NAME = 'com.cs3704.canvas_tracker';
const RESPONSE_TIMEOUT_MS = 10_000;

let port = null;
let pendingCalls = new Map(); // id -> { resolve, reject, timer }
let nextId = 1;
let _available = null; // null = unchecked, true/false = result cached

// ── Port Lifecycle ─────────────────────────────────────────────────────────────

function connect() {
  try {
    port = chrome.runtime.connectNative(HOST_NAME);
    port.onMessage.addListener(onMessage);
    port.onDisconnect.addListener(onDisconnect);
    return true;
  } catch {
    port = null;
    return false;
  }
}

function onMessage(response) {
  const { id, ok, data, error } = response || {};
  const pending = pendingCalls.get(id);
  if (!pending) return;

  clearTimeout(pending.timer);
  pendingCalls.delete(id);

  if (ok) {
    pending.resolve(data);
  } else {
    pending.reject(new Error(error || 'Native host returned an error'));
  }
}

function onDisconnect() {
  port = null;

  // Reject all outstanding calls
  for (const [, pending] of pendingCalls) {
    clearTimeout(pending.timer);
    pending.reject(new Error('Native host disconnected'));
  }
  pendingCalls.clear();
}

function ensureConnected() {
  if (port) return true;
  return connect();
}

// ── Public API ─────────────────────────────────────────────────────────────────

/**
 * Returns true if the native host is installed and connectable.
 * Result is cached after the first successful check.
 */
export function isNativeHostAvailable() {
  if (_available !== null) return _available;

  try {
    const testPort = chrome.runtime.connectNative(HOST_NAME);
    // If we reach here without lastError the host exists
    const err = chrome.runtime.lastError;
    testPort.disconnect();
    _available = !err;
  } catch {
    _available = false;
  }

  return _available;
}

/**
 * Sends a call to the native host and returns a promise for the response.
 *
 * @param {string} method   - e.g. "getCourses"
 * @param {string} token    - Canvas API token
 * @param {string} baseUrl  - Canvas base URL
 * @param {object} params   - extra parameters for the method
 * @returns {Promise<any>}  - resolves with response data, or rejects on error/timeout
 */
export function nativeCall(method, token, baseUrl, params = {}) {
  return new Promise((resolve, reject) => {
    if (!ensureConnected()) {
      reject(new Error('Native host is not available'));
      return;
    }

    const id = nextId++;
    const message = { id, method, token, baseUrl, params };

    const timer = setTimeout(() => {
      pendingCalls.delete(id);
      reject(new Error(`Native host timed out waiting for response to '${method}'`));
    }, RESPONSE_TIMEOUT_MS);

    pendingCalls.set(id, { resolve, reject, timer });

    try {
      port.postMessage(message);
    } catch (err) {
      clearTimeout(timer);
      pendingCalls.delete(id);
      port = null;
      reject(err);
    }
  });
}
