/**
 * Background service worker for Canvas Deadline Tracker.
 * Handles API calls, caching, badge updates, and notifications.
 *
 * Architecture:
 * - IndexedDB cache with stale-while-revalidate (instant popup loads)
 * - Badge shows count of non-dismissed upcoming assignments
 * - Notifications at 24h and 1h before deadline
 * - Message passing to popup for data + cache operations
 */

import { getUpcomingAssignments, getCourses, getCourseAssignments, dismissAssignment, getDismissed, clearCache, getSetting, setSetting } from './lib/cache.js';

const API_BASE = "https://canvas.vt.edu/api/v1";
const NOTIFY_BEFORE = [24 * 3600, 3600]; // 24h and 1h before deadline

// ── Canvas API ────────────────────────────────────────────────────────────────

async function canvasGet(path) {
  const token = await getSetting("canvas_token", "settings");
  if (!token) throw new Error("Not authenticated");
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });
  if (res.status === 401) {
    await setSetting(null, "canvas_token", "settings");
    throw new Error("Token expired");
  }
  if (!res.ok) throw new Error(`Canvas API error: ${res.status}`);
  return res.json();
}

// ── Badge Update ─────────────────────────────────────────────────────────────

async function updateBadge() {
  try {
    const { data: events } = await getUpcomingAssignments(canvasGet);
    const dismissed = await getDismissed();
    const count = events.filter(e => e.type === "assignment" && !dismissed.has(String(e.assignment?.id))).length;
    chrome.action.setBadgeText({ text: count > 0 ? String(count) : "" });
    chrome.action.setBadgeBackgroundColor({ color: "#d63e36" });
  } catch {
    chrome.action.setBadgeText({ text: "?" });
    chrome.action.setBadgeBackgroundColor({ color: "#f48c06" });
  }
}

// ── Notifications ─────────────────────────────────────────────────────────────

async function checkDeadlines() {
  try {
    const { data: events } = await getUpcomingAssignments(canvasGet);
    const dismissed = await getDismissed();
    const now = Date.now();

    for (const event of events) {
      if (event.type !== "assignment") continue;
      const id = String(event.assignment?.id || event.id);
      if (dismissed.has(id)) continue;

      const due = new Date(event.due_at).getTime();
      const diff = due - now;

      for (const seconds of NOTIFY_BEFORE) {
        if (diff > 0 && diff <= seconds) {
          const notifiedKey = `notified:${id}:${seconds}`;
          const already = await getSetting(notifiedKey, "settings");
          if (!already) {
            const title = seconds >= 86400 ? "24h Reminder" : "1h Reminder";
            await chrome.notifications.create({
              title: `Canvas — ${title}`,
              message: event.title,
              iconUrl: "assets/icon-48.png",
              tag: id,
            });
            await setSetting("true", notifiedKey, "settings");
          }
        }
      }
    }
  } catch {
    // Silent — notification check failures shouldn't spam
  }
}

// ── Message Handlers ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_UPCOMING") {
    getUpcomingAssignments(canvasGet)
      .then(({ data, cached }) => sendResponse({ ok: true, data, cached }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "GET_COURSES") {
    getCourses(canvasGet)
      .then(({ data, cached }) => sendResponse({ ok: true, data, cached }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "DISMISS") {
    dismissAssignment(msg.assignmentId)
      .then(() => {
        updateBadge();
        sendResponse({ ok: true });
      })
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "CLEAR_CACHE") {
    clearCache().then(() => sendResponse({ ok: true })).catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "GET_TOKEN") {
    getSetting("canvas_token", "settings").then(t => sendResponse({ token: t })).catch(() => sendResponse({ token: null }));
    return true;
  }

  if (msg.type === "SET_TOKEN") {
    setSetting(msg.token, "canvas_token", "settings")
      .then(() => { updateBadge(); sendResponse({ ok: true }); })
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "REFRESH_BADGE") {
    clearCache().then(() => { updateBadge(); sendResponse({ ok: true }); }).catch(() => sendResponse({ ok: true }));
    return true;
  }
});

// ── Startup ──────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.session.clear();
  chrome.notifications.create({
    title: "Canvas Deadline Tracker",
    message: "Extension installed. Enter your Canvas API token in the popup settings to get started.",
    iconUrl: "assets/icon-48.png",
  });
});

// Periodically check for deadline notifications
setInterval(checkDeadlines, 10 * 60 * 1000); // every 10 min

// Badge and notification check on startup
updateBadge().then(checkDeadlines);
setInterval(updateBadge, 5 * 60 * 1000); // refresh badge every 5 min