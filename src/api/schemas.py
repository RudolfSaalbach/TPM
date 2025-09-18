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