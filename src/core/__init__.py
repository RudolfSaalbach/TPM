"""
Chronos Engine Core Module - FIXED EXPORTS
Exports all core components for easy imports
"""

from .models import (
    ChronosEvent,
    Priority,
    EventType, 
    EventStatus,
    TimeSlot,
    WorkingHours,
    AnalyticsData,
    PluginConfig
)

# GoogleCalendarClient removed - CalDAV is now primary backend
from .event_parser import EventParser
from .analytics_engine import AnalyticsEngine
from .ai_optimizer import AIOptimizer, OptimizationSuggestion
from .timebox_engine import TimeboxEngine, TimeboxSuggestion
from .replan_engine import ReplanEngine, ReplanSuggestion, Conflict, ConflictType
from .notification_engine import (
    NotificationEngine,
    NotificationChannel,
    WebhookChannel,
    EmailChannel,
    Notification,
    NotificationType
)
from .task_queue import TaskQueue, Task, TaskStatus, TaskPriority  # FIXED: Added TaskPriority
from .plugin_manager import (
    PluginManager,
    PluginInterface,
    EventPlugin,
    SchedulingPlugin,
    PluginInfo
)
from .scheduler import ChronosScheduler

__all__ = [
    # Models
    'ChronosEvent',
    'Priority',
    'EventType',
    'EventStatus', 
    'TimeSlot',
    'WorkingHours',
    'AnalyticsData',
    'PluginConfig',
    
    # Core Components
    'EventParser',
    'AnalyticsEngine',
    'AIOptimizer',
    'OptimizationSuggestion',
    'TimeboxEngine',
    'TimeboxSuggestion',
    'ReplanEngine',
    'ReplanSuggestion',
    'Conflict',
    'ConflictType',
    
    # Notification System
    'NotificationEngine',
    'NotificationChannel',
    'WebhookChannel',
    'EmailChannel',
    'Notification',
    'NotificationType',
    
    # Task System - FIXED
    'TaskQueue',
    'Task',
    'TaskStatus',
    'TaskPriority',
    
    # Plugin System
    'PluginManager',
    'PluginInterface',
    'EventPlugin', 
    'SchedulingPlugin',
    'PluginInfo',
    
    # Scheduler
    'ChronosScheduler'
]

# Version info
__version__ = "2.2.0"
__author__ = "Chronos Team"
__description__ = "Advanced Calendar Management System with AI-powered optimization"
