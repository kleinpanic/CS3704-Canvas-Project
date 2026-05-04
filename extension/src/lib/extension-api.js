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

export async function dismissAssignmentRemote(assignmentId) {
  return send(MESSAGE_TYPES.dismiss, { assignmentId });
}
