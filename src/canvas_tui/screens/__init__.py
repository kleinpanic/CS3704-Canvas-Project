"""TUI screens for Canvas TUI."""

from .announcements import AnnouncementDetailScreen, AnnouncementsScreen
from .details import DetailsScreen
from .modals import ConfirmPath, InputPrompt, LoadingScreen
from .syllabi import SyllabiScreen

__all__ = [
    "AnnouncementDetailScreen",
    "AnnouncementsScreen",
    "ConfirmPath",
    "DetailsScreen",
    "InputPrompt",
    "LoadingScreen",
    "SyllabiScreen",
]
