"""
Pydantic schemas for API request/response models
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator
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
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: bool = False
    priority: PriorityEnum = PriorityEnum.MEDIUM
    event_type: EventTypeEnum = EventTypeEnum.TASK
    status: EventStatusEnum = EventStatusEnum.SCHEDULED
    tags: List[str] = Field(default_factory=list)
    attendees: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    calendar_id: Optional[str] = None
    sub_tasks: Optional[List[SubTaskSchema]] = None

    @model_validator(mode='after')
    def validate_times(self):
        if not self.all_day:
            if not self.start_time or not self.end_time:
                raise ValueError("start_time and end_time required for non-all-day events")
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be after start_time")
        return self


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
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: bool = False
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
    message: str
    events_processed: int
    events_added: int = 0
    events_updated: int = 0
    events_deleted: int = 0
    sync_duration_ms: int = 0
    errors: List[str] = []
    timestamp: datetime


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


# Admin Workflow Schemas (General Workflows)
class AdminWorkflowTrigger(BaseModel):
    type: str = Field(..., description="Trigger type (event, schedule, webhook)")
    conditions: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AdminWorkflowAction(BaseModel):
    type: str = Field(..., description="Action type (email, api_call, command)")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AdminWorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    triggers: List[AdminWorkflowTrigger] = Field(default_factory=list)
    actions: List[AdminWorkflowAction] = Field(default_factory=list)
    status: str = Field("active", pattern="^(active|paused|error)$")


class AdminWorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    triggers: Optional[List[AdminWorkflowTrigger]] = None
    actions: Optional[List[AdminWorkflowAction]] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|error)$")


class AdminWorkflowResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    triggers: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    execution_count: int
    last_execution: Optional[datetime] = None
    success_rate: float
    avg_runtime: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminWorkflowsListResponse(BaseModel):
    success: bool = True
    total: int
    page: int
    page_size: int
    workflows: List[AdminWorkflowResponse]


class AdminWorkflowExecutionResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    runtime_seconds: Optional[float] = None
    error_message: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    executed_at: datetime

    class Config:
        from_attributes = True


# Email Template Schemas
class EmailTemplateCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=10)


class EmailTemplateCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=10)


class EmailTemplateCategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    template_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    subject: str = Field(..., min_length=1, max_length=300)
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    category_id: Optional[int] = None
    is_active: bool = True
    variables: Optional[List[str]] = Field(default_factory=list)


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    subject: Optional[str] = Field(None, min_length=1, max_length=300)
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None
    variables: Optional[List[str]] = None


class EmailTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    subject: str
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_icon: Optional[str] = None
    is_active: bool
    usage_count: int
    open_rate: float
    click_rate: float
    variables: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailTemplatesListResponse(BaseModel):
    success: bool = True
    total: int
    page: int
    page_size: int
    templates: List[EmailTemplateResponse]


class EmailTemplateCategoriesListResponse(BaseModel):
    success: bool = True
    total: int
    categories: List[EmailTemplateCategoryResponse]


class EmailTemplateStatsResponse(BaseModel):
    total_templates: int
    active_templates: int
    total_categories: int
    total_sent: int
    avg_open_rate: float
    avg_click_rate: float


# Whitelist Schemas
class WhitelistTypeEnum(str, Enum):
    IP = "ip"
    DOMAIN = "domain"
    API_KEY = "api_key"
    ACTION = "action"


class WhitelistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    type: WhitelistTypeEnum
    entries: List[str] = Field(default_factory=list, description="List of whitelist entries")
    enabled: bool = True


class WhitelistUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    type: Optional[WhitelistTypeEnum] = None
    entries: Optional[List[str]] = None
    enabled: Optional[bool] = None


class WhitelistResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    type: str
    entries: List[str]
    enabled: bool
    usage_count: int
    last_used: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WhitelistsListResponse(BaseModel):
    success: bool = True
    total: int
    page: int
    page_size: int
    whitelists: List[WhitelistResponse]


class WhitelistCheckRequest(BaseModel):
    whitelist_id: Optional[int] = None
    whitelist_name: Optional[str] = None
    value: str = Field(..., description="Value to check against whitelist")
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


class WhitelistCheckResponse(BaseModel):
    allowed: bool
    whitelist_id: int
    whitelist_name: str
    requested_value: str
    result: str  # allowed, denied
    message: Optional[str] = None


class WhitelistAccessLogResponse(BaseModel):
    id: int
    whitelist_id: int
    requested_value: str
    result: str
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
    accessed_at: datetime

    class Config:
        from_attributes = True


class WhitelistStatsResponse(BaseModel):
    total_whitelists: int
    active_whitelists: int
    total_checks: int
    allowed_checks: int
    denied_checks: int
    success_rate: float