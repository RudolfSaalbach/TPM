"""
CalDAV API Router
Handles CalDAV backend management and calendar operations
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from src.api.dependencies import verify_api_key, get_scheduler
from src.api.error_handling import handle_api_errors
from src.api.standard_schemas import (
    APISuccessResponse, CalDAVConnectionTestResponse, CalDAVBackendSwitchResponse,
    CalDAVCalendarListResponse, CalDAVSyncResponse, CalDAVEventResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)


# CalDAV-specific schemas
class CalDAVBackendInfo(BaseModel):
    backend_type: str
    capabilities: Dict[str, Any]
    calendars: List[Dict[str, Any]]


class CalDAVConnectionTest(BaseModel):
    server_url: str
    username: Optional[str] = None
    password: Optional[str] = None


class CalDAVBackendSwitch(BaseModel):
    backend_type: str  # "caldav" or "google"


class CalDAVEventCreate(BaseModel):
    summary: str
    description: Optional[str] = None
    start_time: str  # ISO format
    end_time: str    # ISO format
    location: Optional[str] = None


@router.get("/backend/info", response_model=CalDAVBackendInfo)
@handle_api_errors
async def get_backend_info(
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Get current CalDAV backend information and capabilities"""
    try:
        # Get source manager from scheduler
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        # Get adapter capabilities
        capabilities = await adapter.capabilities()
        calendars = await adapter.list_calendars()

        return CalDAVBackendInfo(
            backend_type=capabilities.name,
            capabilities={
                "name": capabilities.name,
                "can_write": capabilities.can_write,
                "supports_sync_token": capabilities.supports_sync_token,
                "timezone": capabilities.timezone
            },
            calendars=[
                {
                    "id": cal.id,
                    "alias": cal.alias,
                    "url": cal.url,
                    "read_only": cal.read_only,
                    "timezone": cal.timezone
                }
                for cal in calendars
            ]
        )

    except Exception as e:
        logger.error(f"Error getting backend info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get backend info: {str(e)}"
        )


@router.post("/test-connection", response_model=CalDAVConnectionTestResponse)
@handle_api_errors
async def test_caldav_connection(
    connection_data: CalDAVConnectionTest,
    authenticated: bool = Depends(verify_api_key)
):
    """Test CalDAV server connection"""
    try:
        # This would create a temporary adapter to test the connection
        # For now, we'll return a simple success response
        # In a full implementation, this would actually test the connection

        logger.info(f"Testing connection to {connection_data.server_url}")

        # Implement actual connection testing
        try:
            import caldav
            from caldav import DAVClient

            # Create temporary CalDAV client
            client = DAVClient(
                url=connection_data.server_url,
                username=connection_data.username,
                password=connection_data.password
            )

            # Test connection by getting principal
            principal = client.principal()

            # Try to get calendar home set
            calendar_home = principal.calendar_home_set

            # Try to list calendars
            calendars = principal.calendars()
            calendar_count = len(calendars)

            return CalDAVConnectionTestResponse(
                success=True,
                message=f"Connection successful! Found {calendar_count} calendar(s)",
                server_url=connection_data.server_url,
                details={
                    "calendar_count": calendar_count,
                    "principal_url": str(principal.url) if principal else None,
                    "calendar_home": str(calendar_home) if calendar_home else None,
                    "calendars": [{"name": cal.name, "url": str(cal.url)} for cal in calendars[:5]]  # Max 5 for preview
                }
            )

        except ImportError:
            return CalDAVConnectionTestResponse(
                success=False,
                message="CalDAV library not available - install python-caldav",
                server_url=connection_data.server_url,
                details={"error": "python-caldav package not installed"}
            )
        except Exception as conn_error:
            return CalDAVConnectionTestResponse(
                success=False,
                message=f"Connection failed: {str(conn_error)}",
                server_url=connection_data.server_url,
                details={
                "server_type": "Unknown",  # Would be detected
                "supports_caldav": True,
                "supports_sync": True
            }
        )

    except Exception as e:
        logger.error(f"Error testing CalDAV connection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


@router.post("/backend/switch", response_model=CalDAVBackendSwitchResponse)
@handle_api_errors
async def switch_backend(
    switch_data: CalDAVBackendSwitch,
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Switch between CalDAV and Google Calendar backends"""
    try:
        # Get source manager from scheduler
        source_manager = scheduler.source_manager

        # Switch backend
        if switch_data.backend_type == "caldav":
            await source_manager.switch_to_caldav()
        elif switch_data.backend_type == "google":
            await source_manager.switch_to_google()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown backend type: {switch_data.backend_type}"
            )

        return CalDAVBackendSwitchResponse(
            success=True,
            message=f"Switched to {switch_data.backend_type} backend",
            current_backend=switch_data.backend_type
        )

    except Exception as e:
        logger.error(f"Error switching backend: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch backend: {str(e)}"
        )


@router.get("/calendars", response_model=CalDAVCalendarListResponse)
@handle_api_errors
async def list_calendars(
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """List all available CalDAV calendars"""
    try:
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        calendars = await adapter.list_calendars()

        return CalDAVCalendarListResponse(
            calendars=[
                {
                    "id": cal.id,
                    "alias": cal.alias,
                    "url": cal.url,
                    "read_only": cal.read_only,
                    "timezone": cal.timezone
                }
                for cal in calendars
            ],
            total_count=len(calendars)
        )

    except Exception as e:
        logger.error(f"Error listing calendars: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list calendars: {str(e)}"
        )


@router.post("/calendars/{calendar_id}/sync", response_model=CalDAVSyncResponse)
@handle_api_errors
async def sync_calendar(
    calendar_id: str,
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Manually sync a specific calendar"""
    try:
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        # Find the calendar
        calendars = await adapter.list_calendars()
        target_calendar = None
        for cal in calendars:
            if cal.id == calendar_id:
                target_calendar = cal
                break

        if not target_calendar:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calendar {calendar_id} not found"
            )

        # Sync the calendar
        # This would typically involve calling the scheduler's sync method
        # with a specific calendar filter
        logger.info(f"Syncing calendar {calendar_id}")

        # TODO: Implement actual calendar-specific sync
        # For now, trigger a general sync
        sync_result = await scheduler.sync_events()

        return CalDAVSyncResponse(
            success=True,
            message=f"Calendar {calendar_id} synced successfully",
            calendar_id=calendar_id,
            sync_details={
                "events_processed": sync_result.get("events_processed", 0),
                "errors": sync_result.get("errors", [])
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing calendar {calendar_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync calendar: {str(e)}"
        )


@router.post("/calendars/{calendar_id}/events", response_model=CalDAVEventResponse)
@handle_api_errors
async def create_caldav_event(
    calendar_id: str,
    event_data: CalDAVEventCreate,
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Create event directly in CalDAV calendar"""
    try:
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        # Find the calendar
        calendars = await adapter.list_calendars()
        target_calendar = None
        for cal in calendars:
            if cal.id == calendar_id:
                target_calendar = cal
                break

        if not target_calendar:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calendar {calendar_id} not found"
            )

        if target_calendar.read_only:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Calendar {calendar_id} is read-only"
            )

        # Create event data for adapter
        from datetime import datetime
        adapter_event_data = {
            'summary': event_data.summary,
            'description': event_data.description,
            'start_time': datetime.fromisoformat(event_data.start_time.replace('Z', '+00:00')),
            'end_time': datetime.fromisoformat(event_data.end_time.replace('Z', '+00:00')),
            'location': event_data.location
        }

        # Create event via adapter
        event_uid = await adapter.create_event(target_calendar, adapter_event_data)

        return CalDAVEventResponse(
            success=True,
            message=f"Event created in calendar {calendar_id}",
            event_uid=event_uid,
            calendar_id=calendar_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating event in calendar {calendar_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}"
        )


@router.get("/calendars/{calendar_id}/events/{event_id}", response_model=Dict[str, Any])
@handle_api_errors
async def get_caldav_event(
    calendar_id: str,
    event_id: str,
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Get specific event from CalDAV calendar"""
    try:
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        # Find the calendar
        calendars = await adapter.list_calendars()
        target_calendar = None
        for cal in calendars:
            if cal.id == calendar_id:
                target_calendar = cal
                break

        if not target_calendar:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calendar {calendar_id} not found"
            )

        # Get event
        event = await adapter.get_event(target_calendar, event_id)

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found in calendar {calendar_id}"
            )

        return {
            "event": event,
            "calendar_id": calendar_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event {event_id} from calendar {calendar_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get event: {str(e)}"
        )


@router.patch("/calendars/{calendar_id}/events/{event_id}", response_model=CalDAVEventResponse)
@handle_api_errors
async def update_caldav_event(
    calendar_id: str,
    event_id: str,
    patch_data: Dict[str, Any],
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Update specific event in CalDAV calendar"""
    try:
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        # Find the calendar
        calendars = await adapter.list_calendars()
        target_calendar = None
        for cal in calendars:
            if cal.id == calendar_id:
                target_calendar = cal
                break

        if not target_calendar:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calendar {calendar_id} not found"
            )

        if target_calendar.read_only:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Calendar {calendar_id} is read-only"
            )

        # Update event via adapter
        new_etag = await adapter.patch_event(target_calendar, event_id, patch_data)

        return CalDAVEventResponse(
            success=True,
            message=f"Event {event_id} updated in calendar {calendar_id}",
            event_id=event_id,
            calendar_id=calendar_id,
            new_etag=new_etag
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating event {event_id} in calendar {calendar_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update event: {str(e)}"
        )


@router.delete("/calendars/{calendar_id}/events/{event_id}", response_model=CalDAVEventResponse)
@handle_api_errors
async def delete_caldav_event(
    calendar_id: str,
    event_id: str,
    authenticated: bool = Depends(verify_api_key),
    scheduler = Depends(get_scheduler)
):
    """Delete specific event from CalDAV calendar"""
    try:
        source_manager = scheduler.source_manager
        adapter = source_manager.adapter

        # Find the calendar
        calendars = await adapter.list_calendars()
        target_calendar = None
        for cal in calendars:
            if cal.id == calendar_id:
                target_calendar = cal
                break

        if not target_calendar:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calendar {calendar_id} not found"
            )

        if target_calendar.read_only:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Calendar {calendar_id} is read-only"
            )

        # Delete event via adapter
        success = await adapter.delete_event(target_calendar, event_id)

        if success:
            return CalDAVEventResponse(
                success=True,
                message=f"Event {event_id} deleted from calendar {calendar_id}",
                event_id=event_id,
                calendar_id=calendar_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete event {event_id}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting event {event_id} from calendar {calendar_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete event: {str(e)}"
        )