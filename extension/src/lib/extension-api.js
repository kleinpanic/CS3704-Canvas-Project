/**
 * Shared runtime bridge for popup/content-script code.
 *
 * Keeps Chrome message names and background contract details out of UI files.
 */

import { MESSAGE_TYPES } from './extension-contract.js';

function send(type, payload = {}) {
  return chrome.runtime.sendMessage({ type, ...payload });
}

export async function getUpcomingAssignments() {
  return send(MESSAGE_TYPES.getUpcoming);
}

export async function getCourses() {
  return send(MESSAGE_TYPES.getCourses);
}

export async function getCourseAssignments(courseId) {
  return send(MESSAGE_TYPES.getCourseAssignments, { courseId });
}

export async function getCourseAnnouncements(courseId) {
  return send(MESSAGE_TYPES.getCourseAnnouncements, { courseId });
}

export async function getCourseModules(courseId) {
  return send(MESSAGE_TYPES.getCourseModules, { courseId });
}

export async function validateToken() {
  return send(MESSAGE_TYPES.validateToken);
}

export async function setToken(token) {
  return send(MESSAGE_TYPES.setToken, { token });
}

export async function getToken() {
  return send(MESSAGE_TYPES.getToken);
}

export async function clearCache() {
  return send(MESSAGE_TYPES.clearCache);
}

export async function refreshBadge() {
  return send(MESSAGE_TYPES.refreshBadge);
}

export async function getRmpRating(professorName) {
  return send(MESSAGE_TYPES.getRmpRating, { professorName });
}

export async function getCourseGrades(courseId) {
  return send(MESSAGE_TYPES.getCourseGrades, { courseId });
}

export async function getTodo() {
  return send(MESSAGE_TYPES.getTodo);
}

export async function getCourseFiles(courseId) {
  return send(MESSAGE_TYPES.getCourseFiles, { courseId });
}

export async function getPlannerNotes() {
  return send(MESSAGE_TYPES.getPlannerNotes);
}

export async function dismissAssignmentRemote(assignmentId) {
  return send(MESSAGE_TYPES.dismiss, { assignmentId });
}

// ── Local preferences (stored directly in chrome.storage.local) ──────────────
// Preferences that only affect popup rendering don't need a background round-trip.

const PREFS_KEY = "canvas_tui_prefs";

const DEFAULT_PREFS = {
  theme: "dark",
  daysAhead: 7,
};

export async function getPreferences() {
  try {
    const result = await chrome.storage.local.get(PREFS_KEY);
    return { ...DEFAULT_PREFS, ...(result[PREFS_KEY] || {}) };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export async function savePreferences(prefs) {
  try {
    const current = await getPreferences();
    await chrome.storage.local.set({ [PREFS_KEY]: { ...current, ...prefs } });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}
