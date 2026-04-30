/**
 * Shared extension runtime contract.
 *
 * Keeps message type names centralized so UI/background stay in sync.
 */

export const MESSAGE_TYPES = {
  getUpcoming: 'GET_UPCOMING',
  getCourses: 'GET_COURSES',
  getCourseAssignments: 'GET_COURSE_ASSIGNMENTS',
  validateToken: 'VALIDATE_TOKEN',
  getToken: 'GET_TOKEN',
  setToken: 'SET_TOKEN',
  dismiss: 'DISMISS',
  clearCache: 'CLEAR_CACHE',
  refreshBadge: 'REFRESH_BADGE',
};
