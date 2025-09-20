"""
Chronos Engine API Module
Complete API package initialization
"""

from .routes import ChronosUnifiedAPIRoutes
from .dashboard import ChronosDashboard
from .exceptions import (
    ChronosException,
    CalendarConnectionError,
    EventParsingError,
    AnalyticsError,
    PluginError,
    TaskQueueError,
    ChronosErrorHandler
)

__all__ = [
    'ChronosUnifiedAPIRoutes',
    'ChronosDashboard',
    'ChronosException',
    'CalendarConnectionError',
    'EventParsingError',
    'AnalyticsError',
    'PluginError',
    'TaskQueueError',
    'ChronosErrorHandler'
]

__version__ = "2.2.0"
