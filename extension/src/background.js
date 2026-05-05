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
  getCourseAnnouncements,
  getCourseModules,
  dismissAssignment,
  getDismissed,
  clearCache,
} from './lib/cache.js';
import { createCanvasClient } from './lib/canvas-client.js';
import { MESSAGE_TYPES } from './lib/extension-contract.js';
import { nativeCall, isNativeHostAvailable } from './lib/native-host.js';

const NOTIFY_BEFORE = [24 * 3600, 3600]; // 24h and 1h before deadline
const canvasClient = createCanvasClient();

// ── Native Host Helper ────────────────────────────────────────────────────────

/**
 * Attempt a call via the native messaging host.
 * Returns the response data on success, or null if unavailable / errored.
 */
async function tryNative(method, params = {}) {
  if (!isNativeHostAvailable()) return null;
  try {
    const token = await canvasClient.getToken().catch(() => null);
    if (!token) return null;
    return await nativeCall(method, token, canvasClient.baseUrl, params);
  } catch {
    return null;
  }
}

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

const messageHandlers = {
  [MESSAGE_TYPES.getUpcoming]: () =>
    getUpcomingAssignments(() => canvasClient.getUpcomingAssignments()),

  [MESSAGE_TYPES.getCourses]: () =>
    getCourses(() => canvasClient.getCourses()),

  [MESSAGE_TYPES.getCourseAssignments]: (msg) =>
    getCourseAssignments((courseId) => canvasClient.getCourseAssignments(courseId), msg.courseId),

  [MESSAGE_TYPES.getCourseAnnouncements]: (msg) =>
    getCourseAnnouncements((courseId) => canvasClient.getCourseAnnouncements(courseId), msg.courseId),

  [MESSAGE_TYPES.getCourseModules]: (msg) =>
    getCourseModules((courseId) => canvasClient.getCourseModules(courseId), msg.courseId),

  [MESSAGE_TYPES.validateToken]: async () => {
    const { user } = await canvasClient.validateToken();
    return { user };
  },

  [MESSAGE_TYPES.dismiss]: async (msg) => {
    await dismissAssignment(msg.assignmentId);
    await updateBadge();
    return {};
  },

  [MESSAGE_TYPES.clearCache]: async () => {
    await clearCache();
    return {};
  },

  [MESSAGE_TYPES.getToken]: async () => {
    const token = await canvasClient.getToken().catch(() => null);
    return { token };
  },

  [MESSAGE_TYPES.setToken]: async (msg) => {
    await canvasClient.setToken(msg.token);
    const { user } = await canvasClient.validateToken();
    clearCache().catch(() => {});
    updateBadge();
    return { user };
  },

  [MESSAGE_TYPES.refreshBadge]: async () => {
    await clearCache().catch(() => {});
    await updateBadge().catch(() => {});
    return {};
  },

  [MESSAGE_TYPES.getRmpRating]: async (msg) => {
    const lastName = (msg.professorName || '').split(' ').pop();
    if (!lastName) return { rating: null, difficulty: null, numRatings: 0 };
    const url = `https://www.ratemyprofessors.com/filter/teacher?institution_id=1346&query=${encodeURIComponent(lastName)}`;
    const res = await fetch(url);
    if (!res.ok) return { rating: null, difficulty: null, numRatings: 0 };
    const json = await res.json();
    const teacher = (json.data || [])[0];
    if (!teacher) return { rating: null, difficulty: null, numRatings: 0 };
    return {
      rating: teacher.avg_rating ?? null,
      difficulty: teacher.avg_difficulty ?? null,
      numRatings: teacher.num_ratings ?? 0,
    };
  },

  [MESSAGE_TYPES.getCourseGrades]: async (msg) => {
    // Try native host first; fall back to Canvas enrollments endpoint
    const nativeData = await tryNative('getCourseGrades', { courseId: msg.courseId });
    if (nativeData !== null) return { data: nativeData };

    // Direct Canvas API fallback: enrollments with grades
    const data = await canvasClient.request(
      `/courses/${msg.courseId}/enrollments`,
      { params: { type: 'StudentEnrollment', include: 'grades', per_page: 1 } }
    );
    return { data };
  },

  [MESSAGE_TYPES.getTodo]: async () => {
    // Native host only; return empty array fallback if unavailable
    const nativeData = await tryNative('getTodo');
    return { data: nativeData ?? [] };
  },

  [MESSAGE_TYPES.getCourseFiles]: async (msg) => {
    // Try native host first; fall back to canvasClient.getCourseFiles
    const nativeData = await tryNative('getCourseFiles', { courseId: msg.courseId });
    if (nativeData !== null) return { data: nativeData };

    const data = await canvasClient.getCourseFiles(msg.courseId);
    return { data };
  },

  [MESSAGE_TYPES.getPlannerNotes]: async () => {
    // Native host only; return empty array fallback if unavailable
    const nativeData = await tryNative('getPlannerNotes');
    return { data: nativeData ?? [] };
  },
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const handler = messageHandlers[msg.type];
  if (!handler) return false;

  Promise.resolve(handler(msg))
    .then((payload) => sendOk(sendResponse, payload))
    .catch((err) => sendError(sendResponse, err));
  return true;
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
