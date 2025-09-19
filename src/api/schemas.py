"""
Pydantic schemas for API request/response models
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class PriorityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class EventTypeEnum(str, Enum):
    MEETING = "meeting"
    TASK = "task"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"
    BLOCK = "block"


class EventStatusEnum(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class SubTaskSchema(BaseModel):
    id: str
    text: str
    completed: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    priority: PriorityEnum = PriorityEnum.MEDIUM
    event_type: EventTypeEnum = EventTypeEnum.TASK
    status: EventStatusEnum = EventStatusEnum.SCHEDULED
    tags: List[str] = Field(default_factory=list)
    attendees: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    sub_tasks: Optional[List[SubTaskSchema]] = None


class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    priority: Optional[PriorityEnum] = None
    event_type: Optional[EventTypeEnum] = None
    status: Optional[EventStatusEnum] = None
    tags: Optional[List[str]] = None
    attendees: Optional[List[str]] = None
    location: Optional[str] = None
    sub_tasks: Optional[List[SubTaskSchema]] = None


class EventResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    priority: PriorityEnum
    event_type: EventTypeEnum
    status: EventStatusEnum
    tags: List[str]
    attendees: List[str]
    location: Optional[str] = None
    calendar_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sub_tasks: Optional[List[SubTaskSchema]] = None
    linked_events: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True


class SyncRequest(BaseModel):
    days_ahead: int = Field(default=7, ge=1, le=365)
    force_refresh: bool = False
    calendar_id: str = "primary"


class SyncResponse(BaseModel):
    success: bool
    events_processed: int
    events_created: int
    events_updated: int
    sync_time: str
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    scheduler: Dict[str, Any]


class AnalyticsRequest(BaseModel):
    days_back: int = Field(default=30, ge=1, le=365)
    include_weekends: bool = True


class AnalyticsResponse(BaseModel):
    period_days: int
    total_events: int
    completed_events: int
    completion_rate: float
    productivity_score: float
    metrics: Dict[str, Any]


# Template schemas
class TemplateCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    all_day: bool = False
    default_time: Optional[str] = Field(None, pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440)
    calendar_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    all_day: Optional[bool] = None
    default_time: Optional[str] = Field(None, pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440)
    calendar_id: Optional[str] = None
    tags: Optional[List[str]] = None


class TemplateResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    all_day: bool
    default_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    calendar_id: Optional[str] = None
    tags: List[str]
    usage_count: int
    created_at: str
    updated_at: str
    author: Optional[str] = None

    class Config:
        from_attributes = True


class TemplateUsageResponse(BaseModel):
    id: int
    template_id: int
    used_at: str
    actor: Optional[str] = None

    class Config:
        from_attributes = True


class TemplatesListResponse(BaseModel):
    items: List[TemplateResponse]
    page: int = 1
    page_size: int = 100
    total_count: Optional[int] = None


# Enhanced Event schemas for new filtering
class EventsListResponse(BaseModel):
    items: List[EventResponse]
    page: int = 1
    page_size: int = 100
    total_count: Optional[int] = None


class EventDirection(str, Enum):
    PAST = "past"
    FUTURE = "future"
    ALL = "all"


# v2.2 Feature Schemas

class EventLinkCreate(BaseModel):
    source_event_id: str
    target_event_id: str
    link_type: str = "related"

    class Config:
        from_attributes = True


class EventLinkResponse(BaseModel):
    id: int
    source_event_id: str
    target_event_id: str
    link_type: str
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class AvailabilityRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    attendees: List[str] = Field(default_factory=list)
    calendar_ids: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AvailabilitySlot(BaseModel):
    start_time: datetime
    end_time: datetime
    available: bool
    conflicts: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AvailabilityResponse(BaseModel):
    attendee: str
    slots: List[AvailabilitySlot]

    class Config:
        from_attributes = True


class WorkflowCreate(BaseModel):
    trigger_command: str
    trigger_system: str
    follow_up_command: str
    follow_up_system: str
    follow_up_params: Optional[Dict[str, Any]] = None
    delay_seconds: int = 0
    enabled: bool = True

    class Config:
        from_attributes = True


class WorkflowResponse(BaseModel):
    id: int
    trigger_command: str
    trigger_system: str
    follow_up_command: str
    follow_up_system: str
    follow_up_params: Optional[Dict[str, Any]] = None
    delay_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True