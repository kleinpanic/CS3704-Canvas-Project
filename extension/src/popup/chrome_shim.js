if (typeof chrome === 'undefined') {
  window.chrome = {
    runtime: {
      lastError: null,
      sendMessage: function (_msg) {
        return Promise.resolve(null);
      },
    },
    storage: {
      local: {
        get: function (key) {
          try {
            var raw = localStorage.getItem(key);
            var parsed;
            try { parsed = raw !== null ? JSON.parse(raw) : undefined; } catch (_) { parsed = undefined; }
            var result = {};
            result[key] = parsed;
            return Promise.resolve(result);
          } catch (_) {
            var fallback = {};
            fallback[key] = undefined;
            return Promise.resolve(fallback);
          }
        },
        set: function (obj) {
          try {
            var keys = Object.keys(obj);
            for (var i = 0; i < keys.length; i++) {
              localStorage.setItem(keys[i], JSON.stringify(obj[keys[i]]));
            }
          } catch (_) {}
          return Promise.resolve();
        },
      },
    },
  };
}
