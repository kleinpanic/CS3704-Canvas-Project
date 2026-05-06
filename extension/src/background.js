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

// ── Lightweight Local Agent ───────────────────────────────────────────────────
// Deterministic query handler that uses extension tools as "agent tools".
// Falls through to native host (Gemma4) if installed and query is complex.

function eventDate(e) {
  const raw = e.due_at || e.start_at || e.end_at || null;
  if (!raw) return null;
  const d = new Date(raw);
  return isNaN(d) ? null : d;
}

function fmtDate(d) {
  if (!d) return 'No due date';
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

async function runLocalAgent(query = '') {
  const q = query.toLowerCase();
  const toolCalls = [];
  let answer = '';

  const track = (name, label) => toolCalls.push({ tool: name, label, status: 'done' });

  // Intent: grades
  if (/grade|score|gpa|point/.test(q)) {
    track('canvas.get_courses', 'Fetching courses');
    const cRes = await getCourses(() => canvasClient.getCourses());
    const courses = cRes.data || [];

    track('canvas.get_grades', `Fetching grades for ${courses.length} courses`);
    const gradesResults = await Promise.all(
      courses.slice(0, 10).map(c =>
        canvasClient.getCourseGrades(c.id)
          .then(d => ({ course: c, enrollments: Array.isArray(d) ? d : [] }))
          .catch(() => ({ course: c, enrollments: [] }))
      )
    );

    const lines = gradesResults.flatMap(({ course, enrollments }) => {
      const enr = enrollments[0];
      const score = enr?.grades?.current_score;
      const grade = enr?.grades?.current_grade;
      if (score == null) return [];
      return [`• ${course.course_code || course.name}: **${grade || '—'}** (${score}%)`];
    });

    answer = lines.length
      ? `Your current grades:\n\n${lines.join('\n')}`
      : 'No grade data available yet — Canvas may not have published scores.';

  // Intent: prioritize / rank / what first
  } else if (/prioriti|rank|first|urgent|important|focus/.test(q)) {
    track('canvas.get_assignments', 'Fetching upcoming assignments');
    const uRes = await getUpcomingAssignments(() => canvasClient.getUpcomingAssignments());
    const items = (uRes.data || []).filter(e => e.type === 'assignment');

    const now = Date.now();
    const sorted = [...items].sort((a, b) => {
      const da = eventDate(a), db = eventDate(b);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      return da - db;
    });

    const lines = sorted.slice(0, 8).map(e => {
      const due = eventDate(e);
      const diffH = due ? (due - now) / 3600000 : null;
      const tag = diffH === null ? '⚪' : diffH < 0 ? '🔴 OVERDUE' : diffH < 24 ? '🟠 Due today' : diffH < 72 ? '🟡 Due soon' : '🟢';
      const pts = e.assignment?.points_possible;
      return `${tag} **${e.title}** — ${fmtDate(due)}${pts ? ` (${pts}pts)` : ''}`;
    });

    answer = lines.length
      ? `Here's your priority order by deadline:\n\n${lines.join('\n')}`
      : 'No upcoming assignments found.';

  // Intent: study plan / schedule
  } else if (/study|plan|schedule|exam|spaced|review/.test(q)) {
    track('canvas.get_assignments', 'Searching for upcoming exams');
    const uRes = await getUpcomingAssignments(() => canvasClient.getUpcomingAssignments());
    const items = (uRes.data || []).filter(e =>
      /exam|midterm|final|quiz|test/.test((e.title || '').toLowerCase())
    );

    if (!items.length) {
      answer = 'No upcoming exams found in your Canvas calendar. Try asking about specific assignments.';
    } else {
      const exam = items.find(e => eventDate(e)) || items[0];
      const examDate = eventDate(exam);
      const now = Date.now();
      const daysUntil = examDate ? (examDate - now) / 86400000 : 7;

      const gaps = daysUntil > 10 ? [10, 5, 2, 1] : daysUntil > 6 ? [5, 3, 1] : [Math.max(1, Math.floor(daysUntil / 2)), 1];
      const sessions = gaps.map(g => {
        const base = examDate ? new Date(examDate.getTime() - g * 86400000) : new Date(Date.now() + g * 86400000);
        base.setHours(9, 0, 0, 0);
        return `• ${base.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })} — 90 min review (${g}d before)`;
      });

      answer = `Spaced study plan for **${exam.title}** (${fmtDate(examDate)}):\n\n${sessions.join('\n')}\n\nStart early, short sessions beat cramming.`;
    }

  // Intent: announcements
  } else if (/announce|news|update|post/.test(q)) {
    track('canvas.get_courses', 'Fetching courses');
    const cRes = await getCourses(() => canvasClient.getCourses());
    const courses = (cRes.data || []).slice(0, 5);

    track('canvas.list_announcements', `Checking ${courses.length} courses`);
    const annResults = await Promise.all(
      courses.map(c =>
        canvasClient.getCourseAnnouncements(c.id)
          .then(d => (Array.isArray(d) ? d : []).slice(0, 2).map(a => ({ ...a, courseName: c.course_code || c.name })))
          .catch(() => [])
      )
    );
    const all = annResults.flat().sort((a, b) => new Date(b.posted_at) - new Date(a.posted_at)).slice(0, 6);

    const lines = all.map(a => {
      const d = new Date(a.posted_at).toLocaleDateString();
      return `• **[${a.courseName}]** ${a.title} — _${d}_`;
    });

    answer = lines.length
      ? `Recent announcements:\n\n${lines.join('\n')}`
      : 'No recent announcements found.';

  // Intent: what's due / upcoming
  } else if (/due|upcoming|deadline|assignm|homework|hw/.test(q)) {
    track('canvas.get_assignments', 'Fetching upcoming assignments');
    const uRes = await getUpcomingAssignments(() => canvasClient.getUpcomingAssignments());
    const items = (uRes.data || []).filter(e => e.type === 'assignment');
    const now = Date.now();

    const lines = items.slice(0, 10).map(e => {
      const due = eventDate(e);
      const diffH = due ? (due - now) / 3600000 : null;
      const when = diffH !== null && diffH < 24
        ? `Today ${due.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
        : fmtDate(due);
      return `• **${e.title}** — ${when}`;
    });

    answer = lines.length
      ? `You have ${items.length} upcoming assignment${items.length !== 1 ? 's' : ''}:\n\n${lines.join('\n')}`
      : 'No upcoming assignments — nice!';

  // Intent: courses / what am I taking
  } else if (/course|class|taking|enrolled/.test(q)) {
    track('canvas.list_courses', 'Fetching enrolled courses');
    const cRes = await getCourses(() => canvasClient.getCourses());
    const courses = cRes.data || [];
    const lines = courses.map(c => `• **${c.course_code}** — ${c.name}`);
    answer = lines.length
      ? `You're enrolled in ${lines.length} course${lines.length !== 1 ? 's' : ''}:\n\n${lines.join('\n')}`
      : 'No active courses found.';

  } else {
    // Fall through to native host (Gemma4) if available
    const nativeRes = await tryNative('agentQuery', { query });
    if (nativeRes !== null) {
      return { ok: true, answer: nativeRes.answer || nativeRes, toolCalls: nativeRes.toolCalls || [] };
    }
    answer = `I can help with:\n\n• **"What's due?"** — upcoming deadlines\n• **"Prioritize my week"** — ranked by urgency\n• **"Study plan"** — spaced review schedule\n• **"My grades"** — current scores\n• **"Any announcements?"** — recent course posts\n\nTry one of those!`;
  }

  return { ok: true, answer, toolCalls };
}

// ── Native-host-first routing helper ─────────────────────────────────────────

/**
 * Try the native host first; fall back to clientFallback() if unavailable.
 * @param {string} nativeMethod  - method name for the host (e.g. "getCourses")
 * @param {object} params        - extra params forwarded to host
 * @param {Function} clientFallback - async function returning { data } on the direct path
 */
async function routeViaHost(nativeMethod, params, clientFallback) {
  const nativeData = await tryNative(nativeMethod, params);
  if (nativeData !== null) return { data: nativeData };
  return clientFallback();
}

// ── Message Handlers ──────────────────────────────────────────────────────────

const messageHandlers = {
  [MESSAGE_TYPES.getUpcoming]: () =>
    routeViaHost(
      'getUpcomingAssignments', {},
      () => getUpcomingAssignments(() => canvasClient.getUpcomingAssignments()),
    ),

  [MESSAGE_TYPES.getCourses]: () =>
    routeViaHost(
      'getCourses', {},
      () => getCourses(() => canvasClient.getCourses()),
    ),

  [MESSAGE_TYPES.getCourseAssignments]: (msg) =>
    routeViaHost(
      'getCourseAssignments', { courseId: msg.courseId },
      () => getCourseAssignments((courseId) => canvasClient.getCourseAssignments(courseId), msg.courseId),
    ),

  [MESSAGE_TYPES.getCourseAnnouncements]: (msg) =>
    routeViaHost(
      'getCourseAnnouncements', { courseId: msg.courseId },
      () => getCourseAnnouncements((courseId) => canvasClient.getCourseAnnouncements(courseId), msg.courseId),
    ),

  [MESSAGE_TYPES.getCourseModules]: (msg) =>
    routeViaHost(
      'getCourseModules', { courseId: msg.courseId },
      () => getCourseModules((courseId) => canvasClient.getCourseModules(courseId), msg.courseId),
    ),

  [MESSAGE_TYPES.validateToken]: async () => {
    const nativeData = await tryNative('validateToken');
    if (nativeData !== null) return { user: nativeData.user ?? nativeData };
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
    const nativeData = await tryNative('getPlannerNotes');
    return { data: nativeData ?? [] };
  },

  [MESSAGE_TYPES.getDashboardCards]: async () =>
    routeViaHost(
      'getDashboardCards', {},
      async () => ({ data: await canvasClient.getDashboardCards() }),
    ),

  [MESSAGE_TYPES.getSyllabus]: async (msg) =>
    routeViaHost(
      'getSyllabus', { courseId: msg.courseId },
      async () => ({ data: await canvasClient.getCourseSyllabus(msg.courseId) }),
    ),

  [MESSAGE_TYPES.getAssignmentGroups]: async (msg) =>
    routeViaHost(
      'getAssignmentGroups', { courseId: msg.courseId },
      async () => ({ data: await canvasClient.getAssignmentGroups(msg.courseId) }),
    ),

  [MESSAGE_TYPES.getSubmission]: async (msg) =>
    routeViaHost(
      'getSubmission', { courseId: msg.courseId, assignmentId: msg.assignmentId },
      async () => ({ data: await canvasClient.getSubmission(msg.courseId, msg.assignmentId) }),
    ),

  [MESSAGE_TYPES.agentQuery]: async (msg) => {
    return runLocalAgent(msg.query);
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
