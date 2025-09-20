"""
SourceAdapter Interface for Calendar Backends
Unified interface for Google Calendar and CalDAV/Radicale integration
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
import logging


@dataclass
class CalendarRef:
    """Reference to a calendar/collection"""
    id: str                   # Internal identifier
    alias: str               # Human-readable name
    url: Optional[str]       # CalDAV URL or Google Calendar ID
    read_only: bool = False  # Whether write operations are allowed
    timezone: str = "UTC"    # Default timezone for this calendar


@dataclass
class AdapterCapabilities:
    """Capabilities of a calendar adapter"""
    name: str                    # Human-readable name
    can_write: bool             # Supports write operations
    supports_sync_token: bool   # Supports incremental sync
    timezone: str               # Default timezone


@dataclass
class EventListResult:
    """Result of listing events"""
    events: List[Dict[str, Any]]           # Normalized event objects
    next_page_token: Optional[str] = None  # For pagination
    sync_token: Optional[str] = None       # For incremental sync


class SourceAdapter(ABC):
    """
    Abstract base class for calendar source adapters

    Provides unified interface for Google Calendar and CalDAV backends.
    All events are normalized to internal format with UTC timestamps and timezone info.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def capabilities(self) -> AdapterCapabilities:
        """Get adapter capabilities"""
        pass

    @abstractmethod
    async def list_calendars(self) -> List[CalendarRef]:
        """List available calendars"""
        pass

    @abstractmethod
    async def list_events(
        self,
        calendar: CalendarRef,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None
    ) -> EventListResult:
        """
        List events from calendar

        Args:
            calendar: Calendar reference
            since: Start of time window (UTC)
            until: End of time window (UTC)
            page_token: For pagination
            sync_token: For incremental sync

        Returns:
            EventListResult with normalized events
        """
        pass

    @abstractmethod
    async def get_event(self, calendar: CalendarRef, event_id: str) -> Optional[Dict[str, Any]]:
        """Get single event by ID"""
        pass

    @abstractmethod
    async def patch_event(
        self,
        calendar: CalendarRef,
        event_id: str,
        patch_data: Dict[str, Any],
        if_match_etag: Optional[str] = None
    ) -> str:
        """
        Patch existing event

        Args:
            calendar: Calendar reference
            event_id: Event identifier
            patch_data: Changes to apply
            if_match_etag: ETag for conflict detection

        Returns:
            New ETag

        Raises:
            ConflictError: If ETag doesn't match
            PermissionError: If calendar is read-only
        """
        pass

    @abstractmethod
    async def create_override(
        self,
        calendar: CalendarRef,
        master_id: str,
        recurrence_id: datetime,
        patch_data: Dict[str, Any]
    ) -> str:
        """
        Create recurrence override/exception

        Args:
            calendar: Calendar reference
            master_id: Master event ID
            recurrence_id: Which occurrence to override
            patch_data: Override data

        Returns:
            New event ID for the override
        """
        pass

    @abstractmethod
    async def get_series_master(self, calendar: CalendarRef, event_id: str) -> Optional[Dict[str, Any]]:
        """Get master event for a recurring series"""
        pass

    @abstractmethod
    async def create_event(self, calendar: CalendarRef, event_data: Dict[str, Any]) -> str:
        """
        Create new event

        Args:
            calendar: Calendar reference
            event_data: Event data in normalized format

        Returns:
            New event ID

        Raises:
            PermissionError: If calendar is read-only
            ValidationError: If event data is invalid
        """
        pass

    @abstractmethod
    async def delete_event(self, calendar: CalendarRef, event_id: str) -> bool:
        """
        Delete event

        Args:
            calendar: Calendar reference
            event_id: Event identifier

        Returns:
            True if deleted successfully

        Raises:
            PermissionError: If calendar is read-only
        """
        pass

    # Utility methods for normalization

    def normalize_event(self, raw_event: Dict[str, Any], calendar: CalendarRef) -> Dict[str, Any]:
        """
        Normalize event to internal format

        Internal format:
        - UTC timestamps with timezone info
        - Boolean all_day flag
        - Standardized recurrence rules
        - Unified metadata structure
        """
        # To be implemented by subclasses with backend-specific logic
        raise NotImplementedError("Subclasses must implement normalize_event")

    def extract_idempotency_markers(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Chronos idempotency markers from event"""
        # Default implementation - to be overridden by adapters
        return {}

    def inject_idempotency_markers(self, event: Dict[str, Any], markers: Dict[str, Any]) -> Dict[str, Any]:
        """Inject Chronos idempotency markers into event"""
        # Default implementation - to be overridden by adapters
        return event

    async def validate_connection(self) -> bool:
        """Test if adapter can connect to backend"""
        try:
            await self.capabilities()
            return True
        except Exception as e:
            self.logger.error(f"Connection validation failed: {e}")
            return False


class ConflictError(Exception):
    """Raised when there's an ETag/version conflict"""
    def __init__(self, message: str, expected_etag: str, actual_etag: str):
        super().__init__(message)
        self.expected_etag = expected_etag
        self.actual_etag = actual_etag


class PermissionError(Exception):
    """Raised when operation is not permitted (e.g., read-only calendar)"""
    pass


class ValidationError(Exception):
    """Raised when event data is invalid"""
    pass


# Utility functions for event normalization

def parse_datetime_with_timezone(dt_str: str, default_tz: str = "UTC") -> datetime:
    """Parse datetime string with timezone awareness"""
    # Implementation depends on format (ISO, CalDAV, etc.)
    # This is a placeholder
    if dt_str.endswith('Z'):
        return datetime.fromisoformat(dt_str[:-1]).replace(tzinfo=None)
    return datetime.fromisoformat(dt_str)


def format_datetime_for_backend(dt: datetime, backend_type: str, all_day: bool = False) -> str:
    """Format datetime for specific backend"""
    if backend_type == "caldav":
        if all_day:
            return dt.strftime('%Y%m%d')
        else:
            return dt.strftime('%Y%m%dT%H%M%SZ')
    elif backend_type == "google":
        if all_day:
            return dt.strftime('%Y-%m-%d')
        else:
            return dt.isoformat() + 'Z'
    else:
        return dt.isoformat()


def normalize_recurrence_rule(rrule: str, backend_type: str) -> str:
    """Normalize RRULE to standard format"""
    # Handle backend-specific RRULE differences
    return rrule  # Placeholder implementation


def extract_timezone_from_event(event: Dict[str, Any], backend_type: str) -> str:
    """Extract timezone from event data"""
    if backend_type == "caldav":
        # Look for DTSTART TZID parameter
        return "UTC"  # Placeholder
    elif backend_type == "google":
        # Look in start.timeZone
        start = event.get('start', {})
        return start.get('timeZone', 'UTC')
    return "UTC"