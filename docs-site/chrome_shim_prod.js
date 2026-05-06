/**
 * Production Chrome Extension API shim for GitHub Pages live demo.
 *
 * Serves data from pre-fetched static JSON files (no CORS needed).
 * NO secrets baked into this shim — Canvas data is pre-fetched at CI time
 * and stored as static JSON; the popup never calls canvas.vt.edu at runtime
 * in demo mode (the shim's handlers below intercept every message).
 *
 * AGENT_QUERY routes through a Cloudflare Worker proxy that holds the
 * HF_TOKEN as a server-side secret. The browser only sees the proxy URL.
 */
(function () {
  'use strict';

  const TOKEN = 'DEMO_MODE_NO_TOKEN'; // cosmetic only — no runtime canvas calls
  const PROXY_URL = 'https://cs3704-demo-proxy.kleinpanic.workers.dev/chat';
  // Popup lives at extension/src/popup/ — data is 3 levels up at site root /data/
  const DATA_BASE = '../../../data/';

  const storage = {};
  storage['canvas_token'] = TOKEN;

  async function fetchJson(path) {
    try {
      const res = await fetch(DATA_BASE + path);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      return { ok: false, error: e.message };
    }
  }

  const dismissed = new Set();

  const handlers = {
    GET_TOKEN: async () => ({ ok: true, data: TOKEN, token: TOKEN }),
    VALIDATE_TOKEN: async () => ({ ok: true }),
    SET_TOKEN: async () => ({ ok: true }),

    GET_COURSES: async () => fetchJson('courses.json'),
    GET_UPCOMING: async () => fetchJson('upcoming.json'),
    GET_COURSE_ASSIGNMENTS: async (msg) => fetchJson(`course_${msg.courseId}_assignments.json`),
    GET_COURSE_ANNOUNCEMENTS: async (msg) => fetchJson(`course_${msg.courseId}_announcements.json`),
    GET_COURSE_MODULES: async (msg) => fetchJson(`course_${msg.courseId}_modules.json`),
    GET_COURSE_GRADES: async (msg) => fetchJson(`course_${msg.courseId}_grades.json`),
    GET_TODO: async () => fetchJson('todo.json'),
    GET_COURSE_FILES: async (msg) => fetchJson(`course_${msg.courseId}_files.json`),
    GET_PLANNER_NOTES: async () => fetchJson('planner_notes.json'),

    GET_RMP_RATING: async (msg) => {
      const name = (msg.professorName || '').trim();
      if (!name) return { ok: true, rating: null, difficulty: null, numRatings: 0 };
      const lastName = name.split(' ').pop();
      const map = await fetchJson('rmp.json');
      if (!map?.ok) return { ok: true, rating: null, difficulty: null, numRatings: 0 };
      const hit = map.data[name] || map.data[lastName] || null;
      return hit
        ? { ok: true, rating: hit.rating, difficulty: hit.difficulty, numRatings: hit.numRatings }
        : { ok: true, rating: null, difficulty: null, numRatings: 0 };
    },
    GET_DASHBOARD_CARDS: async () => fetchJson('dashboard_cards.json'),
    GET_COURSE_SYLLABUS: async (msg) => fetchJson(`course_${msg.courseId}_syllabus.json`),
    GET_ASSIGNMENT_GROUPS: async (msg) => fetchJson(`course_${msg.courseId}_assignment_groups.json`),
    GET_SUBMISSION: async () => ({ ok: false, error: 'Not available in demo' }),
    AGENT_QUERY: async (msg) => {
      const userMsg = msg.query || '';
      try {
        const resp = await fetch(PROXY_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: userMsg }),
        });
        if (!resp.ok) {
          return { ok: false, error: `Proxy error: HTTP ${resp.status}` };
        }
        const result = await resp.json();
        if (result.error) return { ok: false, error: result.error };
        const finalAnswer = result.final_answer || '(empty response)';
        const toolCalls = (result.tool_calls || []).map(tc => ({
          tool: tc.tool || '(unknown)',
          label: tc.args ? JSON.stringify(tc.args).slice(0, 60) : '',
        }));
        return { ok: true, answer: finalAnswer, toolCalls };
      } catch (e) {
        return { ok: false, error: `Network error: ${e.message}` };
      }
    },
    DISMISS: async (msg) => { dismissed.add(msg.assignmentId); return { ok: true }; },
    GET_DISMISSED: async () => ({ ok: true, data: [...dismissed] }),
    GET_PREFERENCES: async () => ({ ok: true, theme: 'light', daysAhead: 14 }),
    SAVE_PREFERENCES: async () => ({ ok: true }),
    CLEAR_CACHE: async () => ({ ok: true }),
    REFRESH_BADGE: async () => ({ ok: true }),
  };

  const storageApi = {
    get: (keys) => {
      if (typeof keys === 'string') keys = [keys];
      const result = {};
      (Array.isArray(keys) ? keys : Object.keys(keys)).forEach(k => {
        if (k in storage) result[k] = storage[k];
      });
      return Promise.resolve(result);
    },
    set: (items) => { Object.assign(storage, items); return Promise.resolve(); },
    remove: (keys) => {
      (Array.isArray(keys) ? keys : [keys]).forEach(k => delete storage[k]);
      return Promise.resolve();
    },
    clear: () => { Object.keys(storage).forEach(k => delete storage[k]); return Promise.resolve(); },
  };

  window.chrome = {
    runtime: {
      sendMessage: function (_extId, _msg, _cb) {
        let msg = _extId, cb = _msg;
        if (typeof _extId === 'string') { msg = _msg; cb = _cb; }
        const h = handlers[msg.type];
        const p = h
          ? h(msg).catch(e => ({ ok: false, error: e.message }))
          : Promise.resolve({ ok: false, error: `Unknown type: ${msg.type}` });
        if (typeof cb === 'function') { p.then(cb); return; }
        return p;
      },
      onMessage: { addListener: () => {} },
      onInstalled: { addListener: () => {} },
      id: 'live-demo',
    },
    storage: {
      local: storageApi,
      session: storageApi,
      sync: storageApi,
    },
    action: {
      setBadgeText: () => {},
      setBadgeBackgroundColor: () => {},
    },
  };

  console.log('[shim] Chrome API shim installed — live demo mode (static data)');
})();
