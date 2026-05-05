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
  getRmpRating: 'GET_RMP_RATING',
  getCourseAnnouncements: 'GET_COURSE_ANNOUNCEMENTS',
  getCourseModules: 'GET_COURSE_MODULES',
  getCourseGrades: 'GET_COURSE_GRADES',
  getTodo: 'GET_TODO',
  getCourseFiles: 'GET_COURSE_FILES',
  getPlannerNotes: 'GET_PLANNER_NOTES',
};
