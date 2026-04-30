/**
 * Background service worker for Canvas Deadline Tracker.
 * Handles API calls, caching, badge updates, and notifications.
 *
 * Architecture:
 * - Shared Canvas client layer for auth + endpoint access
 * - IndexedDB cache with stale-while-revalidate (instant popup loads)
 * - Badge shows count of non-dismissed upcoming assignments
 * - Notifications at 24h and 1h before deadline
 * - Message passing to popup for data + cache operations
 */

import {
  getUpcomingAssignments,
  getCourses,
  getCourseAssignments,
  dismissAssignment,
  getDismissed,
  clearCache,
} from './lib/cache.js';
import { createCanvasClient } from './lib/canvas-client.js';

const NOTIFY_BEFORE = [24 * 3600, 3600]; // 24h and 1h before deadline
const canvasClient = createCanvasClient();

// ── Badge Update ─────────────────────────────────────────────────────────────

async function updateBadge() {
  try {
    const { data: events } = await getUpcomingAssignments(() => canvasClient.getUpcomingAssignments());
    const dismissed = await getDismissed();
    const count = events.filter((e) => e.type === 'assignment' && !dismissed.has(String(e.assignment?.id))).length;
    chrome.action.setBadgeText({ text: count > 0 ? String(count) : '' });
    chrome.action.setBadgeBackgroundColor({ color: '#d63e36' });
  } catch {
    chrome.action.setBadgeText({ text: '?' });
    chrome.action.setBadgeBackgroundColor({ color: '#f48c06' });
  }
}

// ── Notifications ─────────────────────────────────────────────────────────────

async function checkDeadlines() {
  try {
    const { data: events } = await getUpcomingAssignments(() => canvasClient.getUpcomingAssignments());
    const dismissed = await getDismissed();
    const now = Date.now();

    for (const event of events) {
      if (event.type !== 'assignment') continue;
      const id = String(event.assignment?.id || event.id);
      if (dismissed.has(id)) continue;

      const due = new Date(event.due_at).getTime();
      const diff = due - now;

      for (const seconds of NOTIFY_BEFORE) {
        if (diff > 0 && diff <= seconds) {
          const notifiedKey = `notified:${id}:${seconds}`;
          const already = await canvasClient.tokenStore(notifiedKey, 'settings');
          if (!already?.value) {
            const title = seconds >= 86400 ? '24h Reminder' : '1h Reminder';
            await chrome.notifications.create({
              title: `Canvas — ${title}`,
              message: event.title,
              iconUrl: 'assets/icon-48.png',
              tag: id,
            });
            await canvasClient.tokenWriter('true', notifiedKey, 'settings');
          }
        }
      }
    }
  } catch {
    // Silent — notification check failures shouldn't spam
  }
}

function sendOk(sendResponse, payload = {}) {
  sendResponse({ ok: true, ...payload });
}

function sendError(sendResponse, error) {
  sendResponse({ ok: false, error: error?.message || String(error) });
}

// ── Message Handlers ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'GET_UPCOMING') {
    getUpcomingAssignments(() => canvasClient.getUpcomingAssignments())
      .then(({ data, cached, stale }) => sendOk(sendResponse, { data, cached, stale }))
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'GET_COURSES') {
    getCourses(() => canvasClient.getCourses())
      .then(({ data, cached, stale }) => sendOk(sendResponse, { data, cached, stale }))
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'GET_COURSE_ASSIGNMENTS') {
    getCourseAssignments(() => canvasClient.getCourseAssignments(msg.courseId), msg.courseId)
      .then(({ data, cached, stale }) => sendOk(sendResponse, { data, cached, stale }))
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'VALIDATE_TOKEN') {
    canvasClient
      .validateToken()
      .then(({ user }) => sendOk(sendResponse, { user }))
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'DISMISS') {
    dismissAssignment(msg.assignmentId)
      .then(() => {
        updateBadge();
        sendOk(sendResponse);
      })
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'CLEAR_CACHE') {
    clearCache()
      .then(() => sendOk(sendResponse))
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'GET_TOKEN') {
    canvasClient
      .getToken()
      .then((token) => sendOk(sendResponse, { token }))
      .catch(() => sendOk(sendResponse, { token: null }));
    return true;
  }

  if (msg.type === 'SET_TOKEN') {
    canvasClient
      .setToken(msg.token)
      .then(() => canvasClient.validateToken())
      .then(({ user }) => {
        clearCache().catch(() => {});
        updateBadge();
        sendOk(sendResponse, { user });
      })
      .catch((err) => sendError(sendResponse, err));
    return true;
  }

  if (msg.type === 'REFRESH_BADGE') {
    clearCache()
      .then(() => updateBadge())
      .then(() => sendOk(sendResponse))
      .catch(() => sendOk(sendResponse));
    return true;
  }
});

// ── Startup ──────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.session.clear();
  chrome.notifications.create({
    title: 'Canvas Deadline Tracker',
    message: 'Extension installed. Enter your Canvas API token in the popup settings to get started.',
    iconUrl: 'assets/icon-48.png',
  });
});

setInterval(checkDeadlines, 10 * 60 * 1000); // every 10 min
updateBadge().then(checkDeadlines);
setInterval(updateBadge, 5 * 60 * 1000); // refresh badge every 5 min
