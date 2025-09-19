"""
Core data models for Chronos Engine v2.1 - SQLAlchemy Integration
All models now support database persistence
"""

from datetime import datetime, timedelta
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
            sub_tasks=[SubTask.from_dict(task) for task in self.sub_tasks] if self.sub_tasks else []
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
            requires_focus=self.requires_focus,
            sub_tasks=[task.to_dict() for task in self.sub_tasks] if self.sub_tasks else None
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
