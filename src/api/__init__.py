"""
Chronos Engine API Module
Complete API package initialization
"""

from .routes import ChronosAPI, SyncService
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
    'ChronosAPI',
    'SyncService', 
    'ChronosDashboard',
    'ChronosException',
    'CalendarConnectionError',
    'EventParsingError', 
    'AnalyticsError',
    'PluginError',
    'TaskQueueError',
    'ChronosErrorHandler'
]

__version__ = "2.0.0"
