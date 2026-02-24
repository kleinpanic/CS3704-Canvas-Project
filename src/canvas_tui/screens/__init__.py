"""TUI screens for Canvas TUI."""

from .announcements import AnnouncementDetailScreen, AnnouncementsScreen
from .course_overview import CourseOverviewScreen
from .courses import CourseManagerScreen
from .dashboard import DashboardScreen
from .details import DetailsScreen
from .files import FileManagerScreen
from .grades import GradesScreen
from .help import HelpScreen
from .modals import ConfirmPath, InputPrompt, LoadingScreen
from .syllabi import SyllabiScreen
from .weekview import WeekViewScreen

__all__ = [
    "AnnouncementDetailScreen",
    "AnnouncementsScreen",
    "ConfirmPath",
    "CourseManagerScreen",
    "CourseOverviewScreen",
    "DashboardScreen",
    "DetailsScreen",
    "FileManagerScreen",
    "GradesScreen",
    "HelpScreen",
    "InputPrompt",
    "LoadingScreen",
    "SyllabiScreen",
    "WeekViewScreen",
]
