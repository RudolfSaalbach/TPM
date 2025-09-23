"""
Core data models for Chronos Engine v2.1 - SQLAlchemy Integration
All models now support database persistence
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
import uuid
import json

from sqlalchemy import Column, String, DateTime, Integer, Float, Text, Boolean, JSON, ForeignKey
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

    # New UTC timestamp fields for enhanced filtering
    start_utc = Column(DateTime, nullable=True, index=True)
    end_utc = Column(DateTime, nullable=True, index=True)
    all_day_date = Column(String(10), nullable=True, index=True)  # YYYY-MM-DD format

    # v2.2 Feature: Sub-tasks checklist support
    sub_tasks = Column(JSON, nullable=True)
    
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
            priority=Priority[self.priority] if isinstance(self.priority, str) else self.priority,
            event_type=next((et for et in EventType if et.value == self.event_type), EventType.TASK),
            status=next((es for es in EventStatus if es.value == self.status), EventStatus.SCHEDULED),
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
            requires_focus=self.requires_focus,
            sub_tasks=[SubTask.from_dict(task) for task in self.sub_tasks] if self.sub_tasks else [],
            created_at=self.created_at or datetime.utcnow(),
            updated_at=self.updated_at or self.created_at or datetime.utcnow(),
            version=1
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


class TemplateDB(Base):
    """SQLAlchemy model for event templates"""
    __tablename__ = 'templates'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False, index=True)
    description = Column(Text, nullable=True)
    all_day = Column(Integer, nullable=False, default=0)
    default_time = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    calendar_id = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=False, default='[]')
    usage_count = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(Text, nullable=False, default=lambda: datetime.utcnow().isoformat())
    author = Column(Text, nullable=True)

    def to_domain_model(self) -> 'Template':
        """Convert to domain model"""
        import json
        return Template(
            id=self.id,
            title=self.title,
            description=self.description,
            all_day=bool(self.all_day),
            default_time=self.default_time,
            duration_minutes=self.duration_minutes,
            calendar_id=self.calendar_id,
            tags=json.loads(self.tags_json) if self.tags_json else [],
            usage_count=self.usage_count,
            created_at=self.created_at,
            updated_at=self.updated_at,
            author=self.author
        )


class TemplateUsageDB(Base):
    """SQLAlchemy model for template usage tracking"""
    __tablename__ = 'template_usage'

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, nullable=False, index=True)
    used_at = Column(Text, nullable=False, default=lambda: datetime.utcnow().isoformat())
    actor = Column(Text, nullable=True)

    def to_domain_model(self) -> 'TemplateUsage':
        """Convert to domain model"""
        return TemplateUsage(
            id=self.id,
            template_id=self.template_id,
            used_at=self.used_at,
            actor=self.actor
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

    # v2.2 Features
    sub_tasks: List['SubTask'] = field(default_factory=list)

    # Tracking metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1

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

    def is_flexible(self) -> bool:
        """Return True when the event can be safely moved."""
        if not self.flexible_timing:
            return False
        # Meetings and appointments are typically fixed unless explicitly marked flexible
        if self.event_type in {EventType.MEETING, EventType.APPOINTMENT}:
            return False
        return True

    def get_time_slot(self) -> Optional[TimeSlot]:
        """Return a TimeSlot representing the event window."""
        if self.start_time and self.end_time:
            return TimeSlot(self.start_time, self.end_time)
        return None

    def conflicts_with(self, other: 'ChronosEvent') -> bool:
        """Determine whether two events overlap in time."""
        my_slot = self.get_time_slot()
        other_slot = other.get_time_slot()
        if not my_slot or not other_slot:
            return False
        return my_slot.overlaps_with(other_slot)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to a dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'priority': self.priority.name,
            'event_type': self.event_type.value,
            'status': self.status.value,
            'calendar_id': self.calendar_id,
            'attendees': list(self.attendees),
            'location': self.location,
            'tags': list(self.tags),
            'estimated_duration': self.estimated_duration.total_seconds() if self.estimated_duration else None,
            'actual_duration': self.actual_duration.total_seconds() if self.actual_duration else None,
            'preparation_time': self.preparation_time.total_seconds(),
            'buffer_time': self.buffer_time.total_seconds(),
            'productivity_score': self.productivity_score,
            'completion_rate': self.completion_rate,
            'stress_level': self.stress_level,
            'min_duration': self.min_duration.total_seconds(),
            'max_duration': self.max_duration.total_seconds(),
            'flexible_timing': self.flexible_timing,
            'requires_focus': self.requires_focus,
            'sub_tasks': [task.to_dict() for task in self.sub_tasks],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'version': self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChronosEvent':
        """Deserialize event from a dictionary representation."""

        def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            return datetime.fromisoformat(value)

        def _parse_timedelta(seconds: Optional[float]) -> Optional[timedelta]:
            if seconds is None:
                return None
            return timedelta(seconds=float(seconds))

        priority_value = data.get('priority')
        if isinstance(priority_value, Priority):
            priority = priority_value
        elif isinstance(priority_value, str):
            try:
                priority = Priority[priority_value.upper()]
            except KeyError:
                priority = Priority.MEDIUM
        else:
            priority = Priority.MEDIUM

        event_type_value = data.get('event_type')
        if isinstance(event_type_value, EventType):
            event_type = event_type_value
        elif isinstance(event_type_value, str):
            event_type = next(
                (et for et in EventType if et.value == event_type_value.lower() or et.name == event_type_value.upper()),
                EventType.TASK
            )
        else:
            event_type = EventType.TASK

        status_value = data.get('status')
        if isinstance(status_value, EventStatus):
            status = status_value
        elif isinstance(status_value, str):
            status = next(
                (es for es in EventStatus if es.value == status_value.lower() or es.name == status_value.upper()),
                EventStatus.SCHEDULED
            )
        else:
            status = EventStatus.SCHEDULED

        sub_tasks_data = data.get('sub_tasks') or []
        sub_tasks = [
            task if isinstance(task, SubTask) else SubTask.from_dict(task)
            for task in sub_tasks_data
        ]

        created_at = _parse_datetime(data.get('created_at')) or datetime.utcnow()
        updated_at = _parse_datetime(data.get('updated_at')) or created_at

        return cls(
            id=data.get('id', str(uuid.uuid4())),
            title=data.get('title', ''),
            description=data.get('description', ''),
            start_time=_parse_datetime(data.get('start_time')),
            end_time=_parse_datetime(data.get('end_time')),
            priority=priority,
            event_type=event_type,
            status=status,
            calendar_id=data.get('calendar_id', ''),
            attendees=list(data.get('attendees', [])),
            location=data.get('location', ''),
            tags=list(data.get('tags', [])),
            estimated_duration=_parse_timedelta(data.get('estimated_duration')),
            actual_duration=_parse_timedelta(data.get('actual_duration')),
            preparation_time=_parse_timedelta(data.get('preparation_time')) or timedelta(minutes=5),
            buffer_time=_parse_timedelta(data.get('buffer_time')) or timedelta(minutes=10),
            productivity_score=data.get('productivity_score'),
            completion_rate=data.get('completion_rate'),
            stress_level=data.get('stress_level'),
            min_duration=_parse_timedelta(data.get('min_duration')) or timedelta(minutes=15),
            max_duration=_parse_timedelta(data.get('max_duration')) or timedelta(hours=4),
            flexible_timing=data.get('flexible_timing', True),
            requires_focus=data.get('requires_focus', False),
            sub_tasks=sub_tasks,
            created_at=created_at,
            updated_at=updated_at,
            version=int(data.get('version', 1)),
        )

    def to_db_model(self) -> ChronosEventDB:
        """Convert to SQLAlchemy model"""

        def _normalize_to_utc(dt: Optional[datetime]) -> Optional[datetime]:
            if dt is None:
                return None
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt

        start_utc = _normalize_to_utc(self.start_time)
        end_utc = _normalize_to_utc(self.end_time)

        all_day_date = None
        if start_utc and end_utc and self.start_time and self.end_time:
            duration = end_utc - start_utc
            if (
                self.start_time.hour == 0
                and self.start_time.minute == 0
                and self.end_time.hour == 0
                and self.end_time.minute == 0
                and duration >= timedelta(days=1)
            ):
                all_day_date = start_utc.date().isoformat()

        return ChronosEventDB(
            id=self.id,
            title=self.title,
            description=self.description,
            start_time=self.start_time,
            end_time=self.end_time,
            start_utc=start_utc,
            end_utc=end_utc,
            all_day_date=all_day_date,
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
            requires_focus=self.requires_focus,
            sub_tasks=[task.to_dict() for task in self.sub_tasks] if self.sub_tasks else None,
            created_at=self.created_at,
            updated_at=self.updated_at
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


@dataclass
class Template:
    """Event template domain model"""
    id: Optional[int] = None
    title: str = ""
    description: Optional[str] = None
    all_day: bool = False
    default_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    calendar_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    author: Optional[str] = None

    def to_db_model(self) -> TemplateDB:
        """Convert to SQLAlchemy model"""
        return TemplateDB(
            id=self.id,
            title=self.title,
            description=self.description,
            all_day=int(self.all_day),
            default_time=self.default_time,
            duration_minutes=self.duration_minutes,
            calendar_id=self.calendar_id,
            tags_json=json.dumps(self.tags),
            usage_count=self.usage_count,
            created_at=self.created_at,
            updated_at=self.updated_at,
            author=self.author
        )


@dataclass
class TemplateUsage:
    """Template usage tracking domain model"""
    id: Optional[int] = None
    template_id: int = 0
    used_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    actor: Optional[str] = None

    def to_db_model(self) -> TemplateUsageDB:
        """Convert to SQLAlchemy model"""
        return TemplateUsageDB(
            id=self.id,
            template_id=self.template_id,
            used_at=self.used_at,
            actor=self.actor
        )


class CommandStatus(Enum):
    """External command execution status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# SQLAlchemy Models for Command Layer

class NoteDB(Base):
    """Database model for notes from NOTIZ: commands"""
    __tablename__ = 'notes'

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    event_timestamp = Column(DateTime, nullable=True)
    event_details = Column(JSON, nullable=True)
    calendar_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExternalCommandDB(Base):
    """Database model for external commands from ACTION: commands"""
    __tablename__ = 'external_commands'

    id = Column(Integer, primary_key=True, index=True)
    target_system = Column(String(100), nullable=False, index=True)
    command = Column(String(100), nullable=False)
    parameters = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default=CommandStatus.PENDING.value, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)


class URLPayloadDB(Base):
    """Database model for URL payloads from URL: commands"""
    __tablename__ = 'url_payloads'

    id = Column(Integer, primary_key=True, index=True)
    url = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    event_details = Column(JSON, nullable=True)
    calendar_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False, index=True)


# v2.2 Feature Tables

class EventLinkDB(Base):
    """Database model for event links (n:m relationships)"""
    __tablename__ = 'event_links'

    id = Column(Integer, primary_key=True, index=True)
    source_event_id = Column(String(36), nullable=False, index=True)
    target_event_id = Column(String(36), nullable=False, index=True)
    link_type = Column(String(50), nullable=False, default='related', index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)


class ActionWorkflowDB(Base):
    """Database model for ACTION command workflows"""
    __tablename__ = 'action_workflows'

    id = Column(Integer, primary_key=True, index=True)
    trigger_command = Column(String(100), nullable=False, index=True)
    trigger_system = Column(String(100), nullable=False, index=True)
    follow_up_command = Column(String(100), nullable=False)
    follow_up_system = Column(String(100), nullable=False)
    follow_up_params = Column(JSON, nullable=True)
    delay_seconds = Column(Integer, default=0)
    enabled = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowDB(Base):
    """Database model for general workflows (admin interface)"""
    __tablename__ = 'workflows'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='active', index=True)  # active, paused, error
    triggers = Column(JSON, nullable=False)  # List of trigger conditions
    actions = Column(JSON, nullable=False)   # List of actions to execute
    execution_count = Column(Integer, default=0)
    last_execution = Column(DateTime, nullable=True)
    success_rate = Column(Float, default=0.0)
    avg_runtime = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to execution logs
    executions = relationship("WorkflowExecutionDB", back_populates="workflow")


class WorkflowExecutionDB(Base):
    """Database model for workflow execution logs"""
    __tablename__ = 'workflow_executions'

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey('workflows.id'), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)  # success, error, timeout
    runtime_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationship back to workflow
    workflow = relationship("WorkflowDB", back_populates="executions")


class EmailTemplateCategoryDB(Base):
    """Database model for email template categories"""
    __tablename__ = 'email_template_categories'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String(10), nullable=True)  # Emoji icon
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to templates
    templates = relationship("EmailTemplateDB", back_populates="category")


class EmailTemplateDB(Base):
    """Database model for email templates"""
    __tablename__ = 'email_templates'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    subject = Column(String(300), nullable=False)
    html_content = Column(Text, nullable=True)
    text_content = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey('email_template_categories.id'), nullable=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    usage_count = Column(Integer, default=0)
    open_rate = Column(Float, default=0.0)  # Percentage 0.0-1.0
    click_rate = Column(Float, default=0.0)  # Percentage 0.0-1.0
    variables = Column(JSON, nullable=True)  # Available template variables
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category = relationship("EmailTemplateCategoryDB", back_populates="templates")
    sent_emails = relationship("SentEmailDB", back_populates="template")


class SentEmailDB(Base):
    """Database model for tracking sent emails"""
    __tablename__ = 'sent_emails'

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey('email_templates.id'), nullable=True, index=True)
    recipient_email = Column(String(300), nullable=False, index=True)
    subject = Column(String(300), nullable=False)
    html_content = Column(Text, nullable=True)
    text_content = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='sent', index=True)  # sent, delivered, opened, clicked, failed
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationship back to template
    template = relationship("EmailTemplateDB", back_populates="sent_emails")


class WhitelistDB(Base):
    """Database model for system whitelists"""
    __tablename__ = 'whitelists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=False, index=True)  # ip, domain, api_key, action
    entries = Column(JSON, nullable=False)  # List of allowed entries
    enabled = Column(Boolean, default=True, index=True)
    usage_count = Column(Integer, default=0)  # How often it's been checked
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    access_logs = relationship("WhitelistAccessLogDB", back_populates="whitelist")


class WhitelistAccessLogDB(Base):
    """Database model for whitelist access logging"""
    __tablename__ = 'whitelist_access_logs'

    id = Column(Integer, primary_key=True, index=True)
    whitelist_id = Column(Integer, ForeignKey('whitelists.id'), nullable=False, index=True)
    requested_value = Column(String(500), nullable=False, index=True)  # What was being checked
    result = Column(String(20), nullable=False, index=True)  # allowed, denied
    source_ip = Column(String(50), nullable=True, index=True)
    user_agent = Column(Text, nullable=True)
    additional_data = Column(JSON, nullable=True)  # Extra context data
    accessed_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationship back to whitelist
    whitelist = relationship("WhitelistDB", back_populates="access_logs")


# Domain Models for Command Layer

@dataclass
class Note:
    """Note domain model"""
    id: Optional[int] = None
    content: str = ""
    event_timestamp: Optional[datetime] = None
    event_details: Optional[Dict[str, Any]] = None
    calendar_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> NoteDB:
        """Convert to SQLAlchemy model"""
        return NoteDB(
            id=self.id,
            content=self.content,
            event_timestamp=self.event_timestamp,
            event_details=self.event_details,
            calendar_id=self.calendar_id,
            created_at=self.created_at
        )


@dataclass
class ExternalCommand:
    """External command domain model"""
    id: Optional[int] = None
    target_system: str = ""
    command: str = ""
    parameters: Optional[Dict[str, Any]] = None
    status: CommandStatus = CommandStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    def to_db_model(self) -> ExternalCommandDB:
        """Convert to SQLAlchemy model"""
        return ExternalCommandDB(
            id=self.id,
            target_system=self.target_system,
            command=self.command,
            parameters=self.parameters,
            status=self.status.value,
            created_at=self.created_at,
            processed_at=self.processed_at,
            completed_at=self.completed_at,
            result=self.result,
            error_message=self.error_message
        )


@dataclass
class URLPayload:
    """URL payload domain model"""
    id: Optional[int] = None
    url: str = ""
    title: Optional[str] = None
    description: Optional[str] = None
    event_details: Optional[Dict[str, Any]] = None
    calendar_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed: bool = False

    def to_db_model(self) -> URLPayloadDB:
        """Convert to SQLAlchemy model"""
        return URLPayloadDB(
            id=self.id,
            url=self.url,
            title=self.title,
            description=self.description,
            event_details=self.event_details,
            calendar_id=self.calendar_id,
            created_at=self.created_at,
            processed=self.processed
        )


# v2.2 Domain Models

@dataclass
class Workflow:
    """General workflow domain model for admin interface"""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    status: str = "active"  # active, paused, error
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    execution_count: int = 0
    last_execution: Optional[datetime] = None
    success_rate: float = 0.0
    avg_runtime: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> WorkflowDB:
        """Convert to SQLAlchemy model"""
        return WorkflowDB(
            id=self.id,
            name=self.name,
            description=self.description,
            status=self.status,
            triggers=self.triggers,
            actions=self.actions,
            execution_count=self.execution_count,
            last_execution=self.last_execution,
            success_rate=self.success_rate,
            avg_runtime=self.avg_runtime,
            created_at=self.created_at,
            updated_at=self.updated_at
        )


@dataclass
class WorkflowExecution:
    """Workflow execution log domain model"""
    id: Optional[int] = None
    workflow_id: int = 0
    status: str = "success"  # success, error, timeout
    runtime_seconds: Optional[float] = None
    error_message: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> WorkflowExecutionDB:
        """Convert to SQLAlchemy model"""
        return WorkflowExecutionDB(
            id=self.id,
            workflow_id=self.workflow_id,
            status=self.status,
            runtime_seconds=self.runtime_seconds,
            error_message=self.error_message,
            result_data=self.result_data,
            executed_at=self.executed_at
        )


@dataclass
class EmailTemplateCategory:
    """Email template category domain model"""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    icon: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> EmailTemplateCategoryDB:
        """Convert to SQLAlchemy model"""
        return EmailTemplateCategoryDB(
            id=self.id,
            name=self.name,
            description=self.description,
            icon=self.icon,
            created_at=self.created_at,
            updated_at=self.updated_at
        )


@dataclass
class EmailTemplate:
    """Email template domain model"""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    subject: str = ""
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    category_id: Optional[int] = None
    is_active: bool = True
    usage_count: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    variables: Optional[List[str]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> EmailTemplateDB:
        """Convert to SQLAlchemy model"""
        return EmailTemplateDB(
            id=self.id,
            name=self.name,
            description=self.description,
            subject=self.subject,
            html_content=self.html_content,
            text_content=self.text_content,
            category_id=self.category_id,
            is_active=self.is_active,
            usage_count=self.usage_count,
            open_rate=self.open_rate,
            click_rate=self.click_rate,
            variables=self.variables,
            created_at=self.created_at,
            updated_at=self.updated_at
        )


@dataclass
class SentEmail:
    """Sent email tracking domain model"""
    id: Optional[int] = None
    template_id: Optional[int] = None
    recipient_email: str = ""
    subject: str = ""
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    status: str = "sent"  # sent, delivered, opened, clicked, failed
    sent_at: datetime = field(default_factory=datetime.utcnow)
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_db_model(self) -> SentEmailDB:
        """Convert to SQLAlchemy model"""
        return SentEmailDB(
            id=self.id,
            template_id=self.template_id,
            recipient_email=self.recipient_email,
            subject=self.subject,
            html_content=self.html_content,
            text_content=self.text_content,
            status=self.status,
            sent_at=self.sent_at,
            opened_at=self.opened_at,
            clicked_at=self.clicked_at,
            error_message=self.error_message
        )


@dataclass
class Whitelist:
    """Whitelist domain model"""
    id: Optional[int] = None
    name: str = ""
    description: Optional[str] = None
    type: str = ""  # ip, domain, api_key, action
    entries: List[str] = field(default_factory=list)
    enabled: bool = True
    usage_count: int = 0
    last_used: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> WhitelistDB:
        """Convert to SQLAlchemy model"""
        return WhitelistDB(
            id=self.id,
            name=self.name,
            description=self.description,
            type=self.type,
            entries=self.entries,
            enabled=self.enabled,
            usage_count=self.usage_count,
            last_used=self.last_used,
            created_at=self.created_at,
            updated_at=self.updated_at
        )

    def is_allowed(self, value: str) -> bool:
        """Check if a value is allowed by this whitelist"""
        if not self.enabled:
            return False

        if self.type == "ip":
            return self._check_ip(value)
        elif self.type == "domain":
            return self._check_domain(value)
        elif self.type == "api_key":
            return value in self.entries
        elif self.type == "action":
            return value in self.entries
        else:
            return False

    def _check_ip(self, ip: str) -> bool:
        """Check IP address against entries (supports CIDR)"""
        import ipaddress
        try:
            check_ip = ipaddress.ip_address(ip)
            for entry in self.entries:
                try:
                    if '/' in entry:  # CIDR notation
                        network = ipaddress.ip_network(entry, strict=False)
                        if check_ip in network:
                            return True
                    else:  # Exact IP match
                        if check_ip == ipaddress.ip_address(entry):
                            return True
                except ValueError:
                    continue
            return False
        except ValueError:
            return False

    def _check_domain(self, domain: str) -> bool:
        """Check domain against entries (supports wildcards)"""
        domain = domain.lower()
        for entry in self.entries:
            entry = entry.lower()
            if entry.startswith('*.'):
                # Wildcard subdomain match
                if domain.endswith(entry[2:]) or domain == entry[2:]:
                    return True
            elif entry == domain:
                return True
        return False


@dataclass
class WhitelistAccessLog:
    """Whitelist access log domain model"""
    id: Optional[int] = None
    whitelist_id: int = 0
    requested_value: str = ""
    result: str = "denied"  # allowed, denied
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
    accessed_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> WhitelistAccessLogDB:
        """Convert to SQLAlchemy model"""
        return WhitelistAccessLogDB(
            id=self.id,
            whitelist_id=self.whitelist_id,
            requested_value=self.requested_value,
            result=self.result,
            source_ip=self.source_ip,
            user_agent=self.user_agent,
            additional_data=self.additional_data,
            accessed_at=self.accessed_at
        )


@dataclass
class EventLink:
    """Event link domain model for n:m relationships"""
    id: Optional[int] = None
    source_event_id: str = ""
    target_event_id: str = ""
    link_type: str = "related"
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    def to_db_model(self) -> EventLinkDB:
        """Convert to SQLAlchemy model"""
        return EventLinkDB(
            id=self.id,
            source_event_id=self.source_event_id,
            target_event_id=self.target_event_id,
            link_type=self.link_type,
            created_at=self.created_at,
            created_by=self.created_by
        )


@dataclass
class ActionWorkflow:
    """Action workflow domain model"""
    id: Optional[int] = None
    trigger_command: str = ""
    trigger_system: str = ""
    follow_up_command: str = ""
    follow_up_system: str = ""
    follow_up_params: Optional[Dict[str, Any]] = None
    delay_seconds: int = 0
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> ActionWorkflowDB:
        """Convert to SQLAlchemy model"""
        return ActionWorkflowDB(
            id=self.id,
            trigger_command=self.trigger_command,
            trigger_system=self.trigger_system,
            follow_up_command=self.follow_up_command,
            follow_up_system=self.follow_up_system,
            follow_up_params=self.follow_up_params,
            delay_seconds=self.delay_seconds,
            enabled=self.enabled,
            created_at=self.created_at,
            updated_at=self.updated_at
        )


@dataclass
class SubTask:
    """Sub-task model for event checklists"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    completed: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return {
            'id': self.id,
            'text': self.text,
            'completed': self.completed,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubTask':
        """Create from dictionary"""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            text=data.get('text', ''),
            completed=data.get('completed', False),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.utcnow().isoformat())),
            completed_at=datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None
        )
