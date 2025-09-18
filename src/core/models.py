"""
Core data models for Chronos Engine v2.1 - SQLAlchemy Integration
All models now support database persistence
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional
import uuid
import json

from sqlalchemy import Column, String, DateTime, Integer, Float, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, VARCHAR

Base = declarative_base()


class Priority(Enum):
    """Event priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class EventType(Enum):
    """Event types for categorization"""
    MEETING = "meeting"
    TASK = "task"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"
    BLOCK = "block"


class EventStatus(Enum):
    """Event status tracking"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


# Custom SQLAlchemy types
class TimedeltaType(TypeDecorator):
    """Custom type for timedelta storage"""
    impl = Integer
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return int(value.total_seconds())
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return timedelta(seconds=value)
        return value


# SQLAlchemy Models
class ChronosEventDB(Base):
    """SQLAlchemy model for ChronosEvent"""
    __tablename__ = 'events'
    
    # Core attributes
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False, default="")
    description = Column(Text, default="")
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    
    # Categorization
    priority = Column(String(10), nullable=False, default="MEDIUM")
    event_type = Column(String(20), nullable=False, default="TASK")
    status = Column(String(20), nullable=False, default="SCHEDULED")
    
    # Metadata
    calendar_id = Column(String(100), default="")
    attendees = Column(JSON, default=list)
    location = Column(String(200), default="")
    tags = Column(JSON, default=list)
    
    # Duration fields
    estimated_duration = Column(TimedeltaType, nullable=True)
    actual_duration = Column(TimedeltaType, nullable=True)
    preparation_time = Column(TimedeltaType, default=lambda: timedelta(minutes=5))
    buffer_time = Column(TimedeltaType, default=lambda: timedelta(minutes=10))
    
    # AI/Analytics
    productivity_score = Column(Float, nullable=True)
    completion_rate = Column(Float, nullable=True)
    stress_level = Column(Float, nullable=True)
    
    # Scheduling constraints
    min_duration = Column(TimedeltaType, default=lambda: timedelta(minutes=15))
    max_duration = Column(TimedeltaType, default=lambda: timedelta(hours=4))
    flexible_timing = Column(Boolean, default=True)
    requires_focus = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_domain_model(self) -> 'ChronosEvent':
        """Convert SQLAlchemy model to domain model"""
        return ChronosEvent(
            id=self.id,
            title=self.title,
            description=self.description,
            start_time=self.start_time,
            end_time=self.end_time,
            priority=Priority[self.priority],
            event_type=EventType[self.event_type],
            status=EventStatus[self.status],
            calendar_id=self.calendar_id,
            attendees=self.attendees or [],
            location=self.location,
            tags=self.tags or [],
            estimated_duration=self.estimated_duration,
            actual_duration=self.actual_duration,
            preparation_time=self.preparation_time or timedelta(minutes=5),
            buffer_time=self.buffer_time or timedelta(minutes=10),
            productivity_score=self.productivity_score,
            completion_rate=self.completion_rate,
            stress_level=self.stress_level,
            min_duration=self.min_duration or timedelta(minutes=15),
            max_duration=self.max_duration or timedelta(hours=4),
            flexible_timing=self.flexible_timing,
            requires_focus=self.requires_focus
        )


class AnalyticsDataDB(Base):
    """SQLAlchemy model for AnalyticsData"""
    __tablename__ = 'analytics_data'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), nullable=False)
    date = Column(DateTime, nullable=False)
    metrics = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_domain_model(self) -> 'AnalyticsData':
        """Convert to domain model"""
        return AnalyticsData(
            event_id=self.event_id,
            date=self.date,
            metrics=self.metrics or {}
        )


class TaskDB(Base):
    """SQLAlchemy model for background tasks"""
    __tablename__ = 'tasks'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    function_name = Column(String(100), nullable=False)
    args = Column(JSON, default=list)
    kwargs = Column(JSON, default=dict)
    priority = Column(String(10), nullable=False, default="MEDIUM")
    status = Column(String(20), nullable=False, default="PENDING")
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    def to_domain_model(self) -> 'Task':
        """Convert to domain model"""
        return Task(
            id=self.id,
            name=self.name,
            function=self.function_name,
            args=self.args or [],
            kwargs=self.kwargs or {},
            priority=TaskPriority[self.priority],
            status=TaskStatus[self.status],
            result=self.result,
            error=self.error_message,
            progress=self.progress,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at
        )


# Domain Models (unchanged interface)
from dataclasses import dataclass, field


@dataclass
class TimeSlot:
    """Represents a time slot for scheduling"""
    start: datetime
    end: datetime
    available: bool = True
    
    @property
    def duration(self) -> timedelta:
        return self.end - self.start
    
    def overlaps_with(self, other: 'TimeSlot') -> bool:
        """Check if this slot overlaps with another"""
        return self.start < other.end and self.end > other.start
    
    def contains(self, dt: datetime) -> bool:
        """Check if datetime is within this slot"""
        return self.start <= dt < self.end


@dataclass
class ChronosEvent:
    """Enhanced event model with database persistence"""
    
    # Core attributes
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Categorization
    priority: Priority = Priority.MEDIUM
    event_type: EventType = EventType.TASK
    status: EventStatus = EventStatus.SCHEDULED
    
    # Metadata
    calendar_id: str = ""
    attendees: List[str] = field(default_factory=list)
    location: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Duration fields
    estimated_duration: Optional[timedelta] = None
    actual_duration: Optional[timedelta] = None
    preparation_time: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    buffer_time: timedelta = field(default_factory=lambda: timedelta(minutes=10))
    
    # AI/Analytics
    productivity_score: Optional[float] = None
    completion_rate: Optional[float] = None
    stress_level: Optional[float] = None
    
    # Scheduling constraints
    min_duration: timedelta = field(default_factory=lambda: timedelta(minutes=15))
    max_duration: timedelta = field(default_factory=lambda: timedelta(hours=4))
    flexible_timing: bool = True
    requires_focus: bool = False
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate duration from start and end times"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return self.estimated_duration
    
    @property
    def total_time_needed(self) -> timedelta:
        """Calculate total time including preparation and buffer"""
        base_duration = self.duration or self.estimated_duration or timedelta(hours=1)
        return base_duration + self.preparation_time + self.buffer_time
    
    def to_db_model(self) -> ChronosEventDB:
        """Convert to SQLAlchemy model"""
        return ChronosEventDB(
            id=self.id,
            title=self.title,
            description=self.description,
            start_time=self.start_time,
            end_time=self.end_time,
            priority=self.priority.name,
            event_type=self.event_type.value,
            status=self.status.value,
            calendar_id=self.calendar_id,
            attendees=self.attendees,
            location=self.location,
            tags=self.tags,
            estimated_duration=self.estimated_duration,
            actual_duration=self.actual_duration,
            preparation_time=self.preparation_time,
            buffer_time=self.buffer_time,
            productivity_score=self.productivity_score,
            completion_rate=self.completion_rate,
            stress_level=self.stress_level,
            min_duration=self.min_duration,
            max_duration=self.max_duration,
            flexible_timing=self.flexible_timing,
            requires_focus=self.requires_focus
        )


@dataclass
class WorkingHours:
    """Working hours configuration"""
    start_hour: int = 9
    end_hour: int = 17
    break_start: int = 12
    break_end: int = 13
    working_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])


@dataclass
class AnalyticsData:
    """Analytics data structure"""
    event_id: str
    date: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'date': self.date.isoformat(),
            'metrics': self.metrics
        }
    
    def to_db_model(self) -> AnalyticsDataDB:
        """Convert to SQLAlchemy model"""
        return AnalyticsDataDB(
            event_id=self.event_id,
            date=self.date,
            metrics=self.metrics
        )


@dataclass
class Task:
    """Background task model"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    function: str = ""
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_db_model(self) -> TaskDB:
        """Convert to SQLAlchemy model"""
        return TaskDB(
            id=self.id,
            name=self.name,
            function_name=self.function,
            args=self.args,
            kwargs=self.kwargs,
            priority=self.priority.name,
            status=self.status.value,
            result=self.result,
            error_message=self.error,
            progress=self.progress,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at
        )


@dataclass
class PluginConfig:
    """Plugin configuration"""
    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'enabled': self.enabled,
            'config': self.config
        }
