/**
 * Shared extension runtime contract.
 *
 * Keeps message type names centralized so UI/background stay in sync.
 */

export const MESSAGE_TYPES = {
  // Core data
  getUpcoming: 'GET_UPCOMING',
  getCourses: 'GET_COURSES',
  getCourseAssignments: 'GET_COURSE_ASSIGNMENTS',
  getCourseAnnouncements: 'GET_COURSE_ANNOUNCEMENTS',
  getCourseModules: 'GET_COURSE_MODULES',
  getCourseGrades: 'GET_COURSE_GRADES',
  getCourseFiles: 'GET_COURSE_FILES',
  getDashboardCards: 'GET_DASHBOARD_CARDS',
  // SDK parity additions
  getSyllabus: 'GET_COURSE_SYLLABUS',
  getAssignmentGroups: 'GET_ASSIGNMENT_GROUPS',
  getSubmission: 'GET_SUBMISSION',
  // Auth / settings
  validateToken: 'VALIDATE_TOKEN',
  getToken: 'GET_TOKEN',
  setToken: 'SET_TOKEN',
  dismiss: 'DISMISS',
  clearCache: 'CLEAR_CACHE',
  refreshBadge: 'REFRESH_BADGE',
  // External enrichment
  getRmpRating: 'GET_RMP_RATING',
  // Planner / todo
  getTodo: 'GET_TODO',
  getPlannerNotes: 'GET_PLANNER_NOTES',
  // Agentic
  agentQuery: 'AGENT_QUERY',
};
