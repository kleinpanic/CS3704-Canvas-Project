# SPDX-License-Identifier: GPL-3.0-or-later
"""TUI screens for Canvas TUI."""

from .analytics import AnalyticsScreen
from .announcements import AnnouncementDetailScreen, AnnouncementsScreen
from .base import BaseScreen
from .course_overview import CourseOverviewScreen
from .courses import CourseManagerScreen
from .dashboard import DashboardScreen
from .details import DetailsScreen
from .files import FileManagerScreen
from .grades import GradesScreen
from .help import HelpScreen
from .home import HomeScreen
from .modals import ConfirmPath, InputPrompt, LoadingScreen
from .rmp import RMPScreen
from .settings import SettingsScreen
from .syllabi import SyllabiScreen
from .weekview import WeekViewScreen

__all__ = [
    "AnalyticsScreen",
    "AnnouncementDetailScreen",
    "AnnouncementsScreen",
    "BaseScreen",
    "ConfirmPath",
    "CourseManagerScreen",
    "CourseOverviewScreen",
    "DashboardScreen",
    "DetailsScreen",
    "FileManagerScreen",
    "GradesScreen",
    "HelpScreen",
    "HomeScreen",
    "InputPrompt",
    "LoadingScreen",
    "RMPScreen",
    "SettingsScreen",
    "SyllabiScreen",
    "WeekViewScreen",
]
