/**
 * IndexedDB cache adapter for the browser extension.
 * Implements stale-while-revalidate so popup opens are instant.
 */

const DB_NAME = "canvas-tracker";
const DB_VERSION = 1;

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains("cache")) {
        db.createObjectStore("cache", { keyPath: "key" });
      }
      if (!db.objectStoreNames.contains("settings")) {
        db.createObjectStore("settings", { keyPath: "key" });
      }
      if (!db.objectStoreNames.contains("dismissed")) {
        db.createObjectStore("dismissed", { keyPath: "assignment_id" });
      }
    };
  });
}

async function idbGet(key, store = "cache") {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbSet(key, value, store = "cache", ttl = null) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    const item = { key, value, cachedAt: Date.now(), expiresAt: ttl ? Date.now() + ttl * 1000 : null };
    const req = tx.objectStore(store).put(item);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

async function idbDelete(key, store = "cache") {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    const req = tx.objectStore(store).delete(key);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// ── Stale-While-Revalidate ────────────────────────────────────────────────────

async function swrGet(key, fetchFn, ttlSeconds = 300) {
  const cached = await idbGet(key).catch(() => null);
  const isExpired = cached?.expiresAt && Date.now() > cached.expiresAt;

  if (cached && !isExpired) {
    // Fresh cache — return immediately, refresh in background
    refreshInBackground(key, fetchFn, ttlSeconds);
    return { data: cached.value, cached: true };
  }

  // Stale or missing — fetch fresh
  try {
    const fresh = await fetchFn();
    await idbSet(key, fresh, "cache", ttlSeconds);
    return { data: fresh, cached: false };
  } catch (err) {
    // Network error — return stale cache if available
    if (cached) return { data: cached.value, cached: true, stale: true };
    throw err;
  }
}

async function refreshInBackground(key, fetchFn, ttlSeconds) {
  try {
    const fresh = await fetchFn();
    await idbSet(key, fresh, "cache", ttlSeconds);
  } catch {
    // Silent — don't interrupt user experience
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

function callFetcher(fetcher, path) {
  return fetcher.length === 0 ? fetcher() : fetcher(path);
}

export async function getUpcomingAssignments(fetcher) {
  return swrGet(
    "upcoming",
    () => callFetcher(fetcher, "/users/self/upcoming_events?per_page=20"),
    300 // 5 min TTL
  );
}

export async function getCourses(fetcher) {
  return swrGet(
    "courses",
    () => callFetcher(fetcher, "/courses?per_page=100&enrollment_state=active"),
    3600 // 1 hour TTL
  );
}

export async function getCourseAssignments(fetcher, courseId) {
  return swrGet(
    `assignments:${courseId}`,
    () => callFetcher(fetcher, `/courses/${courseId}/assignments?per_page=50`),
    300
  );
}

export async function dismissAssignment(assignmentId) {
  await idbSet(String(assignmentId), { assignment_id: String(assignmentId), dismissedAt: Date.now() }, "dismissed");
}

export async function getDismissed() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("dismissed", "readonly");
    const req = tx.objectStore("dismissed").getAllKeys();
    req.onsuccess = () => resolve(new Set(req.result));
    req.onerror = () => reject(req.error);
  });
}

export async function clearCache() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("cache", "readwrite");
    const req = tx.objectStore("cache").clear();
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

export { idbGet as getSetting, idbSet as setSetting };