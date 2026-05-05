/**
 * Production Chrome Extension API shim for GitHub Pages live demo.
 *
 * Serves data from pre-fetched static JSON files (no CORS needed).
 * TOKEN is injected by CI as __CANVAS_TOKEN__ → actual value at build time.
 * DATA_BASE points to the pre-fetched JSON snapshots baked at CI time.
 */
(function () {
  'use strict';

  const TOKEN = '__CANVAS_TOKEN__';
  const DATA_BASE = '../data/';

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

    GET_RMP_RATING: async () => ({ ok: false, error: 'Not available in demo' }),
    DISMISS: async (msg) => { dismissed.add(msg.assignmentId); return { ok: true }; },
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
