"""TUI screens for Canvas TUI."""

from .announcements import AnnouncementDetailScreen, AnnouncementsScreen
from .details import DetailsScreen
from .grades import GradesScreen
from .help import HelpScreen
from .modals import ConfirmPath, InputPrompt, LoadingScreen
from .syllabi import SyllabiScreen

__all__ = [
    "AnnouncementDetailScreen",
    "AnnouncementsScreen",
    "ConfirmPath",
    "DetailsScreen",
    "GradesScreen",
    "HelpScreen",
    "InputPrompt",
    "LoadingScreen",
    "SyllabiScreen",
]
