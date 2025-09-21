"""
Standardized API Schemas for Chronos Engine
Provides consistent response models and error schemas across all endpoints
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum


# ==================== ERROR SCHEMAS ====================

class ErrorCode(str, Enum):
    """Standardized error codes for API responses"""

    # Authentication & Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INVALID_API_KEY = "INVALID_API_KEY"

    # Validation Errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

    # Resource Errors
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"

    # Business Logic Errors
    CALENDAR_SYNC_ERROR = "CALENDAR_SYNC_ERROR"
    CALDAV_CONNECTION_ERROR = "CALDAV_CONNECTION_ERROR"
    SCHEDULER_ERROR = "SCHEDULER_ERROR"

    # System Errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"


class APIErrorDetail(BaseModel):
    """Detailed error information"""
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Human-readable error message")
    code: Optional[str] = Field(None, description="Machine-readable error code")


class APIErrorResponse(BaseModel):
    """Standardized error response schema"""
    success: bool = Field(False, description="Always false for error responses")
    error: str = Field(..., description="Main error message")
    error_code: ErrorCode = Field(..., description="Standardized error code")
    details: Optional[List[APIErrorDetail]] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


# ==================== SUCCESS RESPONSE SCHEMAS ====================

class APISuccessResponse(BaseModel):
    """Base success response schema"""
    success: bool = Field(True, description="Always true for success responses")
    message: str = Field(..., description="Success message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class APIDataResponse(BaseModel):
    """Success response with data payload"""
    success: bool = Field(True, description="Always true for success responses")
    data: Any = Field(..., description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class APIPaginatedResponse(BaseModel):
    """Paginated response schema"""
    success: bool = Field(True, description="Always true for success responses")
    data: List[Any] = Field(..., description="Response data items")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


# ==================== OPERATION RESULT SCHEMAS ====================

class OperationResult(BaseModel):
    """Standard operation result schema"""
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Operation result message")
    operation_id: Optional[str] = Field(None, description="Operation tracking ID")
    duration_ms: Optional[int] = Field(None, description="Operation duration in milliseconds")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional operation metadata")


class BulkOperationResult(BaseModel):
    """Bulk operation result schema"""
    success: bool = Field(..., description="Overall operation success status")
    message: str = Field(..., description="Overall operation message")
    total_items: int = Field(..., description="Total number of items processed")
    successful_items: int = Field(..., description="Number of successfully processed items")
    failed_items: int = Field(..., description="Number of failed items")
    errors: List[APIErrorDetail] = Field(default_factory=list, description="Individual item errors")
    duration_ms: Optional[int] = Field(None, description="Total operation duration")


# ==================== HEALTH & STATUS SCHEMAS ====================

class HealthStatus(str, Enum):
    """Health status values"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Individual component health"""
    name: str = Field(..., description="Component name")
    status: HealthStatus = Field(..., description="Component status")
    message: Optional[str] = Field(None, description="Status details")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="Last health check time")
    response_time_ms: Optional[int] = Field(None, description="Component response time")


class SystemHealthResponse(BaseModel):
    """System health response"""
    success: bool = Field(True, description="Always true for health responses")
    overall_status: HealthStatus = Field(..., description="Overall system health")
    version: str = Field(..., description="System version")
    uptime_seconds: int = Field(..., description="System uptime in seconds")
    components: List[ComponentHealth] = Field(..., description="Individual component health")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")


# ==================== STATISTICS SCHEMAS ====================

class StatisticItem(BaseModel):
    """Individual statistic item"""
    name: str = Field(..., description="Statistic name")
    value: Union[int, float, str] = Field(..., description="Statistic value")
    unit: Optional[str] = Field(None, description="Value unit (e.g., 'count', 'ms', '%')")
    description: Optional[str] = Field(None, description="Statistic description")


class StatisticsResponse(BaseModel):
    """Statistics response schema"""
    success: bool = Field(True, description="Always true for statistics responses")
    category: str = Field(..., description="Statistics category")
    period: Optional[str] = Field(None, description="Time period for statistics")
    statistics: List[StatisticItem] = Field(..., description="Statistical data")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Statistics generation time")


# ==================== ADMIN OPERATION SCHEMAS ====================

class AdminOperationRequest(BaseModel):
    """Base admin operation request"""
    operation: str = Field(..., description="Operation name")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Operation parameters")
    dry_run: bool = Field(False, description="Whether to perform a dry run")


class AdminOperationResponse(BaseModel):
    """Admin operation response"""
    success: bool = Field(..., description="Operation success status")
    operation: str = Field(..., description="Operation name")
    message: str = Field(..., description="Operation result message")
    dry_run: bool = Field(..., description="Whether this was a dry run")
    results: Optional[Dict[str, Any]] = Field(None, description="Operation results")
    executed_at: datetime = Field(default_factory=datetime.utcnow, description="Execution timestamp")


# ==================== SEARCH & FILTER SCHEMAS ====================

class SortOrder(str, Enum):
    """Sort order values"""
    ASC = "asc"
    DESC = "desc"


class FilterOperator(str, Enum):
    """Filter operator values"""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"


class FilterCriteria(BaseModel):
    """Individual filter criteria"""
    field: str = Field(..., description="Field to filter on")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: Any = Field(..., description="Filter value")


class SortCriteria(BaseModel):
    """Sort criteria"""
    field: str = Field(..., description="Field to sort by")
    order: SortOrder = Field(SortOrder.ASC, description="Sort order")


class SearchRequest(BaseModel):
    """Advanced search request"""
    query: Optional[str] = Field(None, description="Text search query")
    filters: Optional[List[FilterCriteria]] = Field(None, description="Filter criteria")
    sort: Optional[List[SortCriteria]] = Field(None, description="Sort criteria")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(50, ge=1, le=1000, description="Items per page")


class SearchResponse(BaseModel):
    """Search response with metadata"""
    success: bool = Field(True, description="Always true for search responses")
    data: List[Any] = Field(..., description="Search results")
    total_count: int = Field(..., description="Total number of matching items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there are more pages")
    has_previous: bool = Field(..., description="Whether there are previous pages")
    search_metadata: Optional[Dict[str, Any]] = Field(None, description="Search execution metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Search timestamp")


# ==================== CALDAV RESPONSE SCHEMAS ====================

class CalDAVConnectionTestResponse(BaseModel):
    """CalDAV connection test response"""
    success: bool = Field(..., description="Connection test success status")
    message: str = Field(..., description="Test result message")
    server_url: str = Field(..., description="Tested server URL")
    details: Dict[str, Any] = Field(..., description="Connection test details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Test timestamp")


class CalDAVBackendSwitchResponse(BaseModel):
    """CalDAV backend switch response"""
    success: bool = Field(..., description="Switch operation success status")
    message: str = Field(..., description="Switch operation message")
    current_backend: str = Field(..., description="Current active backend")
    previous_backend: Optional[str] = Field(None, description="Previous backend")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Switch timestamp")


class CalDAVCalendarListResponse(BaseModel):
    """CalDAV calendar list response"""
    success: bool = Field(True, description="Always true for successful responses")
    calendars: List[Dict[str, Any]] = Field(..., description="List of calendars")
    total_count: int = Field(..., description="Total number of calendars")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class CalDAVSyncResponse(BaseModel):
    """CalDAV calendar sync response"""
    success: bool = Field(..., description="Sync operation success status")
    message: str = Field(..., description="Sync operation message")
    calendar_id: str = Field(..., description="Synced calendar ID")
    sync_details: Dict[str, Any] = Field(..., description="Sync operation details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Sync timestamp")


class CalDAVEventResponse(BaseModel):
    """CalDAV event operation response"""
    success: bool = Field(..., description="Event operation success status")
    message: str = Field(..., description="Operation message")
    event_uid: Optional[str] = Field(None, description="Event UID")
    event_id: Optional[str] = Field(None, description="Event ID")
    calendar_id: str = Field(..., description="Calendar ID")
    new_etag: Optional[str] = Field(None, description="New event ETag (for updates)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Operation timestamp")


# ==================== COMMANDS RESPONSE SCHEMAS ====================

class CommandResponse(BaseModel):
    """Individual command response"""
    command_id: str = Field(..., description="Command ID")
    system_id: str = Field(..., description="Target system ID")
    command_type: str = Field(..., description="Command type")
    command_data: Dict[str, Any] = Field(..., description="Command data")
    status: str = Field(..., description="Command status")
    created_at: datetime = Field(..., description="Command creation time")
    expires_at: Optional[datetime] = Field(None, description="Command expiration time")


class CommandListResponse(BaseModel):
    """Command list response"""
    success: bool = Field(True, description="Always true for successful responses")
    commands: List[CommandResponse] = Field(..., description="List of commands")
    total_count: int = Field(..., description="Total number of commands")
    system_id: str = Field(..., description="System ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class CommandStatusResponse(BaseModel):
    """Command status response"""
    success: bool = Field(True, description="Always true for successful responses")
    system_id: str = Field(..., description="System ID")
    pending_count: int = Field(..., description="Number of pending commands")
    processing_count: int = Field(..., description="Number of processing commands")
    completed_count: int = Field(..., description="Number of completed commands")
    failed_count: int = Field(..., description="Number of failed commands")
    last_activity: Optional[datetime] = Field(None, description="Last command activity")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Status timestamp")


class CommandOperationResponse(BaseModel):
    """Command operation response (complete/fail/delete)"""
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Operation message")
    command_id: str = Field(..., description="Command ID")
    new_status: Optional[str] = Field(None, description="New command status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Operation timestamp")


# ==================== ADMIN RESPONSE SCHEMAS ====================

class SystemInfoResponse(BaseModel):
    """System information response"""
    success: bool = Field(True, description="Always true for successful responses")
    system_info: Dict[str, Any] = Field(..., description="System information")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Info timestamp")


class AdminStatisticsResponse(BaseModel):
    """Admin statistics response"""
    success: bool = Field(True, description="Always true for successful responses")
    statistics: Dict[str, Any] = Field(..., description="System statistics")
    period: Optional[str] = Field(None, description="Statistics period")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Statistics timestamp")


class RepairRulesResponse(BaseModel):
    """Calendar repair rules response"""
    success: bool = Field(True, description="Always true for successful responses")
    rules: List[Dict[str, Any]] = Field(..., description="Repair rules")
    total_count: int = Field(..., description="Total number of rules")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class RepairMetricsResponse(BaseModel):
    """Calendar repair metrics response"""
    success: bool = Field(True, description="Always true for successful responses")
    metrics: Dict[str, Any] = Field(..., description="Repair metrics")
    period: Optional[str] = Field(None, description="Metrics period")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metrics timestamp")


class CalendarRepairResponse(BaseModel):
    """Calendar repair operation response"""
    success: bool = Field(..., description="Repair operation success status")
    message: str = Field(..., description="Repair operation message")
    dry_run: bool = Field(..., description="Whether this was a dry run")
    repair_summary: Dict[str, Any] = Field(..., description="Repair operation summary")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Repair timestamp")


# ==================== SYNC ADDITIONAL RESPONSE SCHEMAS ====================

class SyncStatusResponse(BaseModel):
    """Enhanced sync status response"""
    success: bool = Field(True, description="Always true for successful responses")
    is_running: bool = Field(..., description="Whether sync is currently running")
    last_sync: Optional[datetime] = Field(None, description="Last sync time")
    next_sync: Optional[datetime] = Field(None, description="Next scheduled sync time")
    status: str = Field(..., description="Current sync status")
    sync_stats: Optional[Dict[str, Any]] = Field(None, description="Sync statistics")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Status timestamp")


class ProductivityMetricsResponse(BaseModel):
    """Productivity metrics response"""
    success: bool = Field(True, description="Always true for successful responses")
    period_start: datetime = Field(..., description="Metrics period start")
    period_end: datetime = Field(..., description="Metrics period end")
    metrics: Dict[str, Any] = Field(..., description="Productivity metrics")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Generation timestamp")


class ScheduleOptimizationResponse(BaseModel):
    """Schedule optimization response"""
    success: bool = Field(..., description="Optimization success status")
    message: str = Field(..., description="Optimization message")
    optimizations: List[Dict[str, Any]] = Field(..., description="Optimization suggestions")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Generation timestamp")


# ==================== UTILITY FUNCTIONS ====================

def create_success_response(message: str, data: Any = None) -> Dict[str, Any]:
    """Create a standardized success response"""
    response = {
        "success": True,
        "message": message,
        "timestamp": datetime.utcnow()
    }

    if data is not None:
        response["data"] = data

    return response


def create_error_response(
    error: str,
    error_code: ErrorCode,
    details: Optional[List[APIErrorDetail]] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """Create a standardized error response"""
    return {
        "success": False,
        "error": error,
        "error_code": error_code.value,
        "details": details or [],
        "timestamp": datetime.utcnow(),
        "request_id": request_id
    }


def create_operation_result(
    success: bool,
    message: str,
    operation_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a standardized operation result"""
    result = {
        "success": success,
        "message": message,
        "timestamp": datetime.utcnow()
    }

    if operation_id:
        result["operation_id"] = operation_id
    if duration_ms is not None:
        result["duration_ms"] = duration_ms
    if metadata:
        result["metadata"] = metadata

    return result