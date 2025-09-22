"""
Consolidated API routes for Chronos Engine v2.2
Unified single API combining all features from multiple versions
"""

import json
import logging
import uuid
import platform
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends, Request, Query, Form, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, or_, func, select, update, text
from sqlalchemy.orm import Session, selectinload

from src.core.scheduler import ChronosScheduler
from src.core.database import db_service, get_db_session
from src.core.schema_extensions import EmailTemplateDB
from src.core.models import (
    ChronosEvent, Priority, EventType, EventStatus,
    ChronosEventDB, TemplateDB, TemplateUsageDB,
    EventLinkDB, ActionWorkflowDB, ExternalCommandDB,
    Template, TemplateUsage, EventLink, ActionWorkflow, SubTask,
    CommandStatus
)
from src.api.schemas import (
    EventCreate, EventUpdate, EventResponse,
    SyncRequest, SyncResponse,
    AnalyticsRequest, AnalyticsResponse,
    EventsListResponse, EventDirection,
    TemplateCreate, TemplateUpdate, TemplateResponse,
    TemplatesListResponse, TemplateUsageResponse,
    EventLinkCreate, EventLinkResponse,
    AvailabilityRequest, AvailabilityResponse, AvailabilitySlot,
    WorkflowCreate, WorkflowResponse,
    SubTaskSchema
)
from src.api.exceptions import (
    ValidationError,
    CalendarSyncError,
    EventNotFoundError,
    handle_api_errors
)


class ChronosUnifiedAPIRoutes:
    """Consolidated API routes for all Chronos Engine features"""

    def __init__(self, scheduler: ChronosScheduler, api_key: str, email_service=None):
        self.scheduler = scheduler
        self.api_key = api_key
        self.email_service = email_service
        self.logger = logging.getLogger(__name__)
        self.router = APIRouter()
        self.security = HTTPBearer(auto_error=False)
        self.templates = Jinja2Templates(directory="templates")

        # Register all routes
        self._register_routes()

    def _register_routes(self):
        """Register all consolidated API routes"""

        # CORE EVENT ROUTES

        @self.router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
        async def create_event(
            event_data: EventCreate,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Create a new event with transactional consistency"""
            self._verify_api_key(credentials)

            transaction_id = str(uuid.uuid4())

            try:
                # Convert to ChronosEvent for scheduler
                chronos_event = ChronosEvent(
                    title=event_data.title,
                    description=event_data.description,
                    start_time=event_data.start_time,
                    end_time=event_data.end_time,
                    priority=Priority[event_data.priority.value],
                    event_type=EventType[event_data.event_type.value],
                    status=EventStatus[event_data.status.value],
                    tags=event_data.tags,
                    attendees=event_data.attendees,
                    location=event_data.location
                )

                # Create through scheduler with transaction support
                created_event = await self.scheduler.create_event(chronos_event)

                return EventResponse(
                    id=created_event.id,
                    title=created_event.title,
                    description=created_event.description,
                    start_time=created_event.start_time,
                    end_time=created_event.end_time,
                    priority=created_event.priority.name,
                    event_type=created_event.event_type.value,
                    status=created_event.status.value,
                    tags=created_event.tags,
                    attendees=created_event.attendees,
                    location=created_event.location,
                    calendar_id=created_event.calendar_id,
                    created_at=created_event.created_at,
                    updated_at=created_event.updated_at
                )

            except CalendarSyncError:
                raise
            except Exception as e:
                self.logger.error(f"Error creating event: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create event: {e}")

        @self.router.get("/events", response_model=EventsListResponse)
        async def get_events_advanced(
            calendar: Optional[str] = Query(None, description="Filter by calendar ID"),
            anchor: str = Query(default_factory=lambda: datetime.utcnow().strftime('%Y-%m-%d'),
                              description="Anchor date (YYYY-MM-DD)"),
            range_days: int = Query(7, alias="range", description="Range in days (7|14|30|60|360|-1)"),
            direction: EventDirection = Query(EventDirection.FUTURE, description="Time direction"),
            q: Optional[str] = Query(None, description="Search query"),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(100, ge=1, le=500, description="Page size"),
            # Legacy parameters for backward compatibility
            limit: int = Query(None, description="Legacy limit parameter"),
            offset: int = Query(None, description="Legacy offset parameter"),
            priority_filter: Optional[str] = Query(None, description="Legacy priority filter"),
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get events with advanced filtering and legacy support"""
            self._verify_api_key(credentials)

            try:
                # Handle legacy parameters
                if limit is not None and offset is not None:
                    page = (offset // limit) + 1 if limit > 0 else 1
                    page_size = limit

                # Parse anchor date
                try:
                    anchor_date = datetime.strptime(anchor, '%Y-%m-%d')
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid anchor date format. Use YYYY-MM-DD")

                # Validate range
                if range_days not in [-1, 7, 14, 30, 60, 360]:
                    raise HTTPException(status_code=400, detail="Invalid range. Use 7, 14, 30, 60, 360, or -1")

                # Handle range=-1 logic
                if range_days == -1:
                    direction = EventDirection.ALL
                    range_days = 36500  # ~100 years for "unlimited"

                # Build and execute query
                async with db_service.get_session() as session:
                    filters = []

                    # Calendar filter
                    if calendar:
                        filters.append(ChronosEventDB.calendar_id == calendar)

                    # Priority filter (legacy)
                    if priority_filter:
                        filters.append(ChronosEventDB.priority == priority_filter)

                    # Time range filtering
                    if direction == EventDirection.PAST:
                        anchor_end = anchor_date.replace(hour=23, minute=59, second=59)
                        range_start = anchor_date - timedelta(days=range_days)
                        filters.append(
                            and_(
                                ChronosEventDB.end_utc <= anchor_end,
                                ChronosEventDB.start_utc >= range_start
                            )
                        )
                    elif direction == EventDirection.FUTURE:
                        anchor_start = anchor_date.replace(hour=0, minute=0, second=0)
                        range_end = anchor_date + timedelta(days=range_days)
                        filters.append(
                            and_(
                                ChronosEventDB.start_utc >= anchor_start,
                                ChronosEventDB.end_utc <= range_end
                            )
                        )
                    else:  # ALL
                        range_start = anchor_date - timedelta(days=range_days)
                        range_end = anchor_date + timedelta(days=range_days)
                        filters.append(
                            and_(
                                ChronosEventDB.start_utc <= range_end,
                                ChronosEventDB.end_utc >= range_start
                            )
                        )

                    # Text search filter
                    if q:
                        search_term = f"%{q}%"
                        filters.append(
                            or_(
                                ChronosEventDB.title.ilike(search_term),
                                ChronosEventDB.description.ilike(search_term)
                            )
                        )

                    # Build base statements
                    count_stmt = select(func.count(ChronosEventDB.id))
                    events_stmt = select(ChronosEventDB)

                    if filters:
                        count_stmt = count_stmt.where(*filters)
                        events_stmt = events_stmt.where(*filters)

                    # Count total for pagination
                    total_result = await session.execute(count_stmt)
                    total_count = total_result.scalar() or 0

                    # Apply pagination
                    offset_calc = (page - 1) * page_size
                    events_stmt = events_stmt.offset(offset_calc).limit(page_size)

                    result = await session.execute(events_stmt)
                    events = result.scalars().all()

                    # Convert to response models
                    event_responses = []
                    for event in events:
                        event_responses.append(EventResponse(
                            id=event.id,
                            title=event.title,
                            description=event.description,
                            start_time=event.start_time or event.start_utc,
                            end_time=event.end_time or event.end_utc,
                            priority=event.priority,
                            event_type=event.event_type,
                            status=event.status,
                            tags=event.tags or [],
                            attendees=event.attendees or [],
                            location=event.location,
                            calendar_id=event.calendar_id,
                            created_at=event.created_at,
                            updated_at=event.updated_at
                        ))

                    return EventsListResponse(
                        items=event_responses,
                        page=page,
                        page_size=page_size,
                        total_count=total_count
                    )

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting events: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get events: {e}")

        @self.router.put("/events/{event_id}", response_model=EventResponse)
        async def update_event(
            event_id: str,
            event_update: EventUpdate,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Update an event with transactional consistency"""
            self._verify_api_key(credentials)

            try:
                # Check if event exists first
                async with db_service.get_session() as session:
                    existing_event = await session.get(ChronosEventDB, event_id)
                    if not existing_event:
                        raise EventNotFoundError(event_id=event_id)

                # Update through scheduler
                updated_event = await self.scheduler.update_event(event_id, event_update)

                return EventResponse(
                    id=updated_event.id,
                    title=updated_event.title,
                    description=updated_event.description,
                    start_time=updated_event.start_time,
                    end_time=updated_event.end_time,
                    priority=updated_event.priority.name,
                    event_type=updated_event.event_type.value,
                    status=updated_event.status.value,
                    tags=updated_event.tags,
                    attendees=updated_event.attendees,
                    location=updated_event.location,
                    calendar_id=updated_event.calendar_id,
                    created_at=updated_event.created_at,
                    updated_at=updated_event.updated_at
                )

            except (EventNotFoundError, CalendarSyncError):
                raise
            except Exception as e:
                self.logger.error(f"Error updating event: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update event: {e}")

        # SYNC AND HEALTH ROUTES

        @self.router.post("/sync/calendar", response_model=SyncResponse)
        async def sync_calendar(
            sync_request: SyncRequest,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Manually trigger calendar synchronization"""
            self._verify_api_key(credentials)

            try:
                result = await self.scheduler.sync_calendar(
                    days_ahead=sync_request.days_ahead,
                    force_refresh=sync_request.force_refresh
                )

                return SyncResponse(
                    success=result['success'],
                    events_processed=result.get('events_processed', 0),
                    events_created=result.get('events_created', 0),
                    events_updated=result.get('events_updated', 0),
                    sync_time=result['sync_time'],
                    error=result.get('error')
                )

            except Exception as e:
                self.logger.error(f"Error syncing calendar: {e}")
                raise HTTPException(status_code=500, detail=f"Calendar sync failed: {e}")

        @self.router.get("/sync/health")
        async def health_check(request: Request):
            """Health check endpoint - no auth required"""
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "version": "2.1"
            }

        @self.router.get("/test/simple")
        async def test_simple():
            """Simple test endpoint without validation"""
            return {"test": "success", "timestamp": datetime.utcnow().isoformat()}

        # ANALYTICS ROUTES

        @self.router.get("/analytics/productivity")
        async def get_productivity_metrics(
            days_back: int = 30,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get productivity analytics"""
            self._verify_api_key(credentials)

            try:
                if self.scheduler and self.scheduler.analytics:
                    # This would need to be implemented in analytics engine
                    return {
                        "period_days": days_back,
                        "productivity_score": 7.5,
                        "completion_rate": 0.85,
                        "metrics": {
                            "total_events": 150,
                            "completed_events": 127,
                            "focus_time_hours": 45.5
                        }
                    }
                else:
                    raise HTTPException(status_code=503, detail="Analytics engine not available")

            except Exception as e:
                self.logger.error(f"Error getting analytics: {e}")
                raise HTTPException(status_code=500, detail=f"Analytics failed: {e}")

        # AI OPTIMIZATION ROUTES

        @self.router.post("/ai/optimize")
        async def optimize_schedule(
            optimization_window_days: int = 7,
            auto_apply: bool = False,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get AI schedule optimization suggestions"""
            self._verify_api_key(credentials)

            try:
                if self.scheduler and self.scheduler.ai_optimizer:
                    return {
                        "optimization_window_days": optimization_window_days,
                        "suggestions": [
                            {
                                "type": "time_block",
                                "title": "Focus Time Block",
                                "suggestion": "Block 2 hours for deep work tomorrow morning",
                                "confidence": 0.85
                            }
                        ],
                        "auto_applied": auto_apply
                    }
                else:
                    raise HTTPException(status_code=503, detail="AI optimizer not available")

            except Exception as e:
                self.logger.error(f"Error optimizing schedule: {e}")
                raise HTTPException(status_code=500, detail=f"Optimization failed: {e}")

        # TEMPLATE MANAGEMENT ROUTES

        @self.router.get("/templates", response_model=TemplatesListResponse)
        async def get_templates(
            q: Optional[str] = Query(None, description="Search query"),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(100, ge=1, le=500, description="Page size"),
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Search templates with ranking"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    stmt = select(TemplateDB)

                    if q:
                        # Token-based AND search with ranking
                        search_tokens = q.lower().split()

                        # Build search conditions for each token
                        conditions = []
                        for token in search_tokens:
                            token_pattern = f"%{token}%"
                            token_condition = or_(
                                TemplateDB.title.ilike(token_pattern),
                                TemplateDB.description.ilike(token_pattern),
                                TemplateDB.tags_json.ilike(token_pattern)
                            )
                            conditions.append(token_condition)

                        # All tokens must match (AND)
                        if conditions:
                            stmt = stmt.where(and_(*conditions))

                        # Add ranking
                        stmt = stmt.order_by(
                            TemplateDB.usage_count.desc(),
                            TemplateDB.title
                        )
                    else:
                        # No search, just order by usage
                        stmt = stmt.order_by(
                            TemplateDB.usage_count.desc(),
                            TemplateDB.created_at.desc()
                        )

                    # Count total
                    count_stmt = select(func.count(TemplateDB.id))
                    if q and conditions:
                        count_stmt = count_stmt.where(and_(*conditions))

                    total_result = await session.execute(count_stmt)
                    total_count = total_result.scalar()

                    # Apply pagination
                    offset = (page - 1) * page_size
                    stmt = stmt.offset(offset).limit(page_size)

                    result = await session.execute(stmt)
                    templates = result.scalars().all()

                    # Convert to response models
                    template_responses = []
                    for template in templates:
                        template_responses.append(TemplateResponse(
                            id=template.id,
                            title=template.title,
                            description=template.description,
                            all_day=bool(template.all_day),
                            default_time=template.default_time,
                            duration_minutes=template.duration_minutes,
                            calendar_id=template.calendar_id,
                            tags=json.loads(template.tags_json) if template.tags_json else [],
                            usage_count=template.usage_count,
                            created_at=template.created_at,
                            updated_at=template.updated_at,
                            author=template.author
                        ))

                    return TemplatesListResponse(
                        items=template_responses,
                        page=page,
                        page_size=page_size,
                        total_count=total_count
                    )

            except Exception as e:
                self.logger.error(f"Error getting templates: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get templates: {e}")

        @self.router.post("/templates", response_model=TemplateResponse)
        async def create_template(
            template_data: TemplateCreate,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Create a new template"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Create template
                    now = datetime.utcnow().isoformat()
                    template_db = TemplateDB(
                        title=template_data.title,
                        description=template_data.description,
                        all_day=int(template_data.all_day),
                        default_time=template_data.default_time,
                        duration_minutes=template_data.duration_minutes,
                        calendar_id=template_data.calendar_id,
                        tags_json=json.dumps(template_data.tags),
                        usage_count=0,
                        created_at=now,
                        updated_at=now,
                        author=None  # Could be extracted from credentials
                    )

                    session.add(template_db)
                    await session.flush()  # Get the ID
                    await session.refresh(template_db)

                    return TemplateResponse(
                        id=template_db.id,
                        title=template_db.title,
                        description=template_db.description,
                        all_day=bool(template_db.all_day),
                        default_time=template_db.default_time,
                        duration_minutes=template_db.duration_minutes,
                        calendar_id=template_db.calendar_id,
                        tags=json.loads(template_db.tags_json) if template_db.tags_json else [],
                        usage_count=template_db.usage_count,
                        created_at=template_db.created_at,
                        updated_at=template_db.updated_at,
                        author=template_db.author
                    )

            except Exception as e:
                self.logger.error(f"Error creating template: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create template: {e}")

        @self.router.put("/templates/{template_id}", response_model=TemplateResponse)
        async def update_template(
            template_id: int,
            template_data: TemplateUpdate,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Update a template"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    template_db = await session.get(TemplateDB, template_id)
                    if not template_db:
                        raise HTTPException(status_code=404, detail="Template not found")

                    # Update fields
                    if template_data.title is not None:
                        template_db.title = template_data.title
                    if template_data.description is not None:
                        template_db.description = template_data.description
                    if template_data.all_day is not None:
                        template_db.all_day = int(template_data.all_day)
                    if template_data.default_time is not None:
                        template_db.default_time = template_data.default_time
                    if template_data.duration_minutes is not None:
                        template_db.duration_minutes = template_data.duration_minutes
                    if template_data.calendar_id is not None:
                        template_db.calendar_id = template_data.calendar_id
                    if template_data.tags is not None:
                        template_db.tags_json = json.dumps(template_data.tags)

                    template_db.updated_at = datetime.utcnow().isoformat()
                    await session.flush()
                    await session.refresh(template_db)

                    return TemplateResponse(
                        id=template_db.id,
                        title=template_db.title,
                        description=template_db.description,
                        all_day=bool(template_db.all_day),
                        default_time=template_db.default_time,
                        duration_minutes=template_db.duration_minutes,
                        calendar_id=template_db.calendar_id,
                        tags=json.loads(template_db.tags_json) if template_db.tags_json else [],
                        usage_count=template_db.usage_count,
                        created_at=template_db.created_at,
                        updated_at=template_db.updated_at,
                        author=template_db.author
                    )

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error updating template: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update template: {e}")

        @self.router.delete("/templates/{template_id}")
        async def delete_template(
            template_id: int,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Delete a template"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    template_db = await session.get(TemplateDB, template_id)
                    if not template_db:
                        raise HTTPException(status_code=404, detail="Template not found")

                    await session.delete(template_db)

                    return {"message": "Template deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error deleting template: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete template: {e}")

        @self.router.post("/templates/{template_id}/use")
        async def use_template(
            template_id: int,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Record template usage (atomic increment and usage tracking)"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Check template exists
                    template_db = await session.get(TemplateDB, template_id)
                    if not template_db:
                        raise HTTPException(status_code=404, detail="Template not found")

                    # Atomic increment
                    template_db.usage_count += 1

                    # Insert usage record
                    usage_db = TemplateUsageDB(
                        template_id=template_id,
                        used_at=datetime.utcnow().isoformat(),
                        actor=None  # Could be extracted from credentials
                    )
                    session.add(usage_db)

                    return {
                        "message": "Template usage recorded",
                        "template_id": template_id,
                        "new_usage_count": template_db.usage_count
                    }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error recording template usage: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to record template usage: {e}")

        # EVENT LINKS ROUTES (v2.2)

        @self.router.post("/event-links", response_model=EventLinkResponse)
        async def create_event_link(
            link_data: EventLinkCreate,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Create a link between two events"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Verify both events exist
                    source_query = select(ChronosEventDB).where(ChronosEventDB.id == link_data.source_event_id)
                    target_query = select(ChronosEventDB).where(ChronosEventDB.id == link_data.target_event_id)

                    source_result = await session.execute(source_query)
                    target_result = await session.execute(target_query)

                    if not source_result.scalar_one_or_none():
                        raise HTTPException(status_code=404, detail="Source event not found")
                    if not target_result.scalar_one_or_none():
                        raise HTTPException(status_code=404, detail="Target event not found")

                    # Create event link
                    event_link = EventLink(
                        source_event_id=link_data.source_event_id,
                        target_event_id=link_data.target_event_id,
                        link_type=link_data.link_type,
                        created_by="api_user"  # TODO: Get from auth context
                    )

                    link_db = event_link.to_db_model()
                    session.add(link_db)
                    await session.flush()

                    return EventLinkResponse(
                        id=link_db.id,
                        source_event_id=link_db.source_event_id,
                        target_event_id=link_db.target_event_id,
                        link_type=link_db.link_type,
                        created_at=link_db.created_at,
                        created_by=link_db.created_by
                    )

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error creating event link: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create event link: {e}")

        @self.router.get("/events/{event_id}/links", response_model=List[EventLinkResponse])
        async def get_event_links(
            event_id: str,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get all links for an event"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Get links where this event is either source or target
                    query = select(EventLinkDB).where(
                        or_(
                            EventLinkDB.source_event_id == event_id,
                            EventLinkDB.target_event_id == event_id
                        )
                    )
                    result = await session.execute(query)
                    links = result.scalars().all()

                    return [
                        EventLinkResponse(
                            id=link.id,
                            source_event_id=link.source_event_id,
                            target_event_id=link.target_event_id,
                            link_type=link.link_type,
                            created_at=link.created_at,
                            created_by=link.created_by
                        )
                        for link in links
                    ]

            except Exception as e:
                self.logger.error(f"Error getting event links: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get event links: {e}")

        @self.router.delete("/event-links/{link_id}")
        async def delete_event_link(
            link_id: int,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Delete an event link"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    query = select(EventLinkDB).where(EventLinkDB.id == link_id)
                    result = await session.execute(query)
                    link = result.scalar_one_or_none()

                    if not link:
                        raise HTTPException(status_code=404, detail="Event link not found")

                    await session.delete(link)

                return {"message": "Event link deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error deleting event link: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete event link: {e}")

        # AVAILABILITY ROUTES (v2.2)

        @self.router.post("/availability", response_model=List[AvailabilityResponse])
        async def check_availability(
            request: AvailabilityRequest,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Check availability for attendees in a time range"""
            self._verify_api_key(credentials)

            try:
                responses = []

                for attendee in request.attendees:
                    # Query events for this attendee in the time range
                    async with db_service.get_session() as session:
                        query = select(ChronosEventDB).where(
                            and_(
                                ChronosEventDB.start_time < request.end_time,
                                ChronosEventDB.end_time > request.start_time,
                                ChronosEventDB.attendees.like(f'%{attendee}%')  # JSON contains check
                            )
                        )
                        result = await session.execute(query)
                        conflicting_events = result.scalars().all()

                        # Create availability slots (simplified - just mark conflicts)
                        slots = []
                        current_time = request.start_time
                        slot_duration = timedelta(minutes=30)  # 30-minute slots

                        while current_time < request.end_time:
                            slot_end = min(current_time + slot_duration, request.end_time)

                            # Check for conflicts in this slot
                            conflicts = []
                            available = True

                            for event in conflicting_events:
                                if (event.start_time < slot_end and event.end_time > current_time):
                                    conflicts.append(event.title)
                                    available = False

                            slots.append(AvailabilitySlot(
                                start_time=current_time,
                                end_time=slot_end,
                                available=available,
                                conflicts=conflicts
                            ))

                            current_time = slot_end

                        responses.append(AvailabilityResponse(
                            attendee=attendee,
                            slots=slots
                        ))

                return responses

            except Exception as e:
                self.logger.error(f"Error checking availability: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to check availability: {e}")

        # WORKFLOW ROUTES (v2.2)

        @self.router.post("/workflows", response_model=WorkflowResponse)
        async def create_workflow(
            workflow_data: WorkflowCreate,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Create a new action workflow"""
            self._verify_api_key(credentials)

            try:
                workflow = ActionWorkflow(
                    trigger_command=workflow_data.trigger_command.upper(),
                    trigger_system=workflow_data.trigger_system,
                    follow_up_command=workflow_data.follow_up_command.upper(),
                    follow_up_system=workflow_data.follow_up_system,
                    follow_up_params=workflow_data.follow_up_params,
                    delay_seconds=workflow_data.delay_seconds,
                    enabled=workflow_data.enabled
                )

                async with db_service.get_session() as session:
                    workflow_db = workflow.to_db_model()
                    session.add(workflow_db)
                    await session.flush()

                    return WorkflowResponse(
                        id=workflow_db.id,
                        trigger_command=workflow_db.trigger_command,
                        trigger_system=workflow_db.trigger_system,
                        follow_up_command=workflow_db.follow_up_command,
                        follow_up_system=workflow_db.follow_up_system,
                        follow_up_params=workflow_db.follow_up_params,
                        delay_seconds=workflow_db.delay_seconds,
                        enabled=workflow_db.enabled,
                        created_at=workflow_db.created_at,
                        updated_at=workflow_db.updated_at
                    )

            except Exception as e:
                self.logger.error(f"Error creating workflow: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create workflow: {e}")

        @self.router.get("/workflows", response_model=List[WorkflowResponse])
        async def list_workflows(
            enabled_only: bool = False,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """List all workflows"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    query = select(ActionWorkflowDB)
                    if enabled_only:
                        query = query.where(ActionWorkflowDB.enabled == True)

                    result = await session.execute(query)
                    workflows = result.scalars().all()

                    return [
                        WorkflowResponse(
                            id=wf.id,
                            trigger_command=wf.trigger_command,
                            trigger_system=wf.trigger_system,
                            follow_up_command=wf.follow_up_command,
                            follow_up_system=wf.follow_up_system,
                            follow_up_params=wf.follow_up_params,
                            delay_seconds=wf.delay_seconds,
                            enabled=wf.enabled,
                            created_at=wf.created_at,
                            updated_at=wf.updated_at
                        )
                        for wf in workflows
                    ]

            except Exception as e:
                self.logger.error(f"Error listing workflows: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list workflows: {e}")

        @self.router.delete("/workflows/{workflow_id}")
        async def delete_workflow(
            workflow_id: int,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Delete a workflow"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    query = select(ActionWorkflowDB).where(ActionWorkflowDB.id == workflow_id)
                    result = await session.execute(query)
                    workflow = result.scalar_one_or_none()

                    if not workflow:
                        raise HTTPException(status_code=404, detail="Workflow not found")

                    await session.delete(workflow)

                return {"message": "Workflow deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error deleting workflow: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete workflow: {e}")

        # EXTERNAL COMMAND ROUTES

        @self.router.get("/commands/{system_id}")
        async def get_pending_commands(
            system_id: str,
            limit: int = Query(10, ge=1, le=100, description="Maximum number of commands to retrieve"),
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get pending external commands for a system (polling endpoint)"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Release commands stuck in PROCESSING for too long
                    stale_threshold = datetime.utcnow() - timedelta(minutes=5)
                    reset_stmt = (
                        update(ExternalCommandDB)
                        .where(
                            ExternalCommandDB.target_system == system_id,
                            ExternalCommandDB.status == CommandStatus.PROCESSING.value,
                            ExternalCommandDB.processed_at.isnot(None),
                            ExternalCommandDB.processed_at < stale_threshold
                        )
                        .values(
                            status=CommandStatus.PENDING.value,
                            processed_at=None
                        )
                    )
                    reset_result = await session.execute(reset_stmt)

                    if reset_result.rowcount:
                        self.logger.warning(
                            f"[API] Reset {reset_result.rowcount} stale commands for system {system_id}"
                        )

                    # Get pending commands for the specified system
                    stmt = select(ExternalCommandDB).where(
                        ExternalCommandDB.target_system == system_id,
                        ExternalCommandDB.status == CommandStatus.PENDING.value
                    ).order_by(ExternalCommandDB.created_at).limit(limit)

                    result = await session.execute(stmt)
                    commands = result.scalars().all()

                    # Mark commands as PROCESSING
                    command_list = []
                    for cmd in commands:
                        cmd.status = CommandStatus.PROCESSING.value
                        cmd.processed_at = datetime.utcnow()

                        command_list.append({
                            "id": cmd.id,
                            "command": cmd.command,
                            "parameters": cmd.parameters,
                            "created_at": cmd.created_at.isoformat(),
                            "processed_at": cmd.processed_at.isoformat()
                        })

                    await session.commit()

                    self.logger.info(f"[API] Retrieved {len(command_list)} commands for system {system_id}")

                    return {
                        "system_id": system_id,
                        "commands": command_list,
                        "count": len(command_list),
                        "retrieved_at": datetime.utcnow().isoformat()
                    }

            except Exception as e:
                self.logger.error(f"Error retrieving commands for {system_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to retrieve commands: {e}")

        @self.router.post("/commands/{command_id}/complete")
        async def complete_command(
            command_id: int,
            completion_data: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Mark a command as completed with result"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    command = await session.get(ExternalCommandDB, command_id)
                    if not command:
                        raise HTTPException(status_code=404, detail="Command not found")

                    # Update command status
                    command.status = CommandStatus.COMPLETED.value
                    command.completed_at = datetime.utcnow()
                    command.result = completion_data

                    await session.commit()

                    self.logger.info(f"[API] Command {command_id} marked as completed")

                    return {
                        "command_id": command_id,
                        "status": "completed",
                        "completed_at": command.completed_at.isoformat()
                    }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error completing command {command_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to complete command: {e}")

        @self.router.post("/commands/{command_id}/fail")
        async def fail_command(
            command_id: int,
            failure_data: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Mark a command as failed with error details"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    command = await session.get(ExternalCommandDB, command_id)
                    if not command:
                        raise HTTPException(status_code=404, detail="Command not found")

                    # Update command status
                    command.status = CommandStatus.FAILED.value
                    command.completed_at = datetime.utcnow()
                    command.error_message = failure_data.get("error", "Unknown error")

                    await session.commit()

                    self.logger.info(f"[API] Command {command_id} marked as failed")

                    return {
                        "command_id": command_id,
                        "status": "failed",
                        "error": command.error_message,
                        "failed_at": command.completed_at.isoformat()
                    }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error failing command {command_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to fail command: {e}")

        # EVENT DATA PORTABILITY ROUTES (Export/Import)

        @self.router.get("/events/{event_id}/export")
        async def export_event(
            event_id: str,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Export a single event with all related data to JSON (FR-1.1, FR-1.2, FR-1.3)"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Get the main event
                    event_stmt = select(ChronosEventDB).where(ChronosEventDB.id == event_id)
                    event_result = await session.execute(event_stmt)
                    event = event_result.scalar_one_or_none()

                    if not event:
                        raise HTTPException(status_code=404, detail="Event not found")

                    # Get related event links
                    links_stmt = select(EventLinkDB).where(
                        or_(
                            EventLinkDB.source_event_id == event_id,
                            EventLinkDB.target_event_id == event_id
                        )
                    )
                    links_result = await session.execute(links_stmt)
                    event_links = links_result.scalars().all()

                    # Create export format with all event data
                    export_data = {
                        "format_version": "1.0",
                        "export_timestamp": datetime.utcnow().isoformat(),
                        "events": [{
                            # Core event data
                            "id": event.id,
                            "title": event.title,
                            "description": event.description,
                            "start_time": event.start_time.isoformat() if event.start_time else None,
                            "end_time": event.end_time.isoformat() if event.end_time else None,
                            "start_utc": event.start_utc.isoformat() if event.start_utc else None,
                            "end_utc": event.end_utc.isoformat() if event.end_utc else None,
                            "all_day_date": event.all_day_date,

                            # Categorization
                            "priority": event.priority,
                            "event_type": event.event_type,
                            "status": event.status,

                            # Metadata
                            "calendar_id": event.calendar_id,
                            "attendees": event.attendees or [],
                            "location": event.location,
                            "tags": event.tags or [],

                            # Sub-tasks (FR-1.3)
                            "sub_tasks": event.sub_tasks or [],

                            # Duration fields
                            "estimated_duration": event.estimated_duration.total_seconds() if event.estimated_duration else None,
                            "actual_duration": event.actual_duration.total_seconds() if event.actual_duration else None,
                            "preparation_time": event.preparation_time.total_seconds() if event.preparation_time else None,
                            "buffer_time": event.buffer_time.total_seconds() if event.buffer_time else None,

                            # AI/Analytics
                            "productivity_score": event.productivity_score,
                            "completion_rate": event.completion_rate,
                            "stress_level": event.stress_level,

                            # Scheduling constraints
                            "min_duration": event.min_duration.total_seconds() if event.min_duration else None,
                            "max_duration": event.max_duration.total_seconds() if event.max_duration else None,
                            "flexible_timing": event.flexible_timing,
                            "requires_focus": event.requires_focus,

                            # Timestamps
                            "created_at": event.created_at.isoformat() if event.created_at else None,
                            "updated_at": event.updated_at.isoformat() if event.updated_at else None
                        }],

                        # Event links/relations (FR-1.3)
                        "event_links": [
                            {
                                "id": link.id,
                                "source_event_id": link.source_event_id,
                                "target_event_id": link.target_event_id,
                                "link_type": link.link_type,
                                "created_at": link.created_at.isoformat() if link.created_at else None,
                                "created_by": link.created_by
                            }
                            for link in event_links
                        ]
                    }

                    return export_data

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error exporting event {event_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to export event: {e}")

        @self.router.post("/events/import")
        async def import_events(
            import_data: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Import events from JSON with transactional processing (FR-2.1, FR-2.2, FR-2.4, FR-2.5, FR-2.6, FR-2.7)"""
            self._verify_api_key(credentials)

            try:
                # Validate import format (FR-2.7)
                if not isinstance(import_data, dict):
                    raise HTTPException(status_code=400, detail="Import data must be a JSON object")

                if "events" not in import_data:
                    raise HTTPException(status_code=400, detail="Import data must contain 'events' array")

                events_data = import_data["events"]
                if not isinstance(events_data, list):
                    raise HTTPException(status_code=400, detail="'events' must be an array")

                if len(events_data) == 0:
                    raise HTTPException(status_code=400, detail="No events to import")

                event_links_data = import_data.get("event_links", [])

                # Validate each event (FR-2.7)
                for i, event_data in enumerate(events_data):
                    if not isinstance(event_data, dict):
                        raise HTTPException(status_code=400, detail=f"Event {i} must be an object")

                    required_fields = ["title"]
                    for field in required_fields:
                        if field not in event_data:
                            raise HTTPException(status_code=400, detail=f"Event {i} missing required field: {field}")

                created_events = []
                created_links = []

                # Transactional processing (FR-2.4)
                async with db_service.get_session() as session:
                    try:
                        # Import events (FR-2.5 - always create new events)
                        old_to_new_id_mapping = {}

                        for event_data in events_data:
                            # Generate new ID to ensure we don't overwrite existing events
                            old_id = event_data.get("id")
                            new_id = str(uuid.uuid4())
                            old_to_new_id_mapping[old_id] = new_id

                            # Parse datetime fields
                            start_time = None
                            end_time = None
                            start_utc = None
                            end_utc = None

                            if event_data.get("start_time"):
                                start_time = datetime.fromisoformat(event_data["start_time"])
                            if event_data.get("end_time"):
                                end_time = datetime.fromisoformat(event_data["end_time"])
                            if event_data.get("start_utc"):
                                start_utc = datetime.fromisoformat(event_data["start_utc"])
                            if event_data.get("end_utc"):
                                end_utc = datetime.fromisoformat(event_data["end_utc"])

                            # Parse timedelta fields
                            estimated_duration = None
                            actual_duration = None
                            preparation_time = None
                            buffer_time = None
                            min_duration = None
                            max_duration = None

                            if event_data.get("estimated_duration") is not None:
                                estimated_duration = timedelta(seconds=event_data["estimated_duration"])
                            if event_data.get("actual_duration") is not None:
                                actual_duration = timedelta(seconds=event_data["actual_duration"])
                            if event_data.get("preparation_time") is not None:
                                preparation_time = timedelta(seconds=event_data["preparation_time"])
                            if event_data.get("buffer_time") is not None:
                                buffer_time = timedelta(seconds=event_data["buffer_time"])
                            if event_data.get("min_duration") is not None:
                                min_duration = timedelta(seconds=event_data["min_duration"])
                            if event_data.get("max_duration") is not None:
                                max_duration = timedelta(seconds=event_data["max_duration"])

                            # Create new event in database
                            new_event = ChronosEventDB(
                                id=new_id,
                                title=event_data["title"],
                                description=event_data.get("description", ""),
                                start_time=start_time,
                                end_time=end_time,
                                start_utc=start_utc,
                                end_utc=end_utc,
                                all_day_date=event_data.get("all_day_date"),
                                priority=event_data.get("priority", "MEDIUM"),
                                event_type=event_data.get("event_type", "TASK"),
                                status=event_data.get("status", "SCHEDULED"),
                                calendar_id=event_data.get("calendar_id", ""),
                                attendees=event_data.get("attendees", []),
                                location=event_data.get("location", ""),
                                tags=event_data.get("tags", []),
                                sub_tasks=event_data.get("sub_tasks", []),
                                estimated_duration=estimated_duration,
                                actual_duration=actual_duration,
                                preparation_time=preparation_time,
                                buffer_time=buffer_time,
                                productivity_score=event_data.get("productivity_score"),
                                completion_rate=event_data.get("completion_rate"),
                                stress_level=event_data.get("stress_level"),
                                min_duration=min_duration,
                                max_duration=max_duration,
                                flexible_timing=event_data.get("flexible_timing", True),
                                requires_focus=event_data.get("requires_focus", False),
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )

                            session.add(new_event)
                            created_events.append(new_event)

                        await session.flush()  # Ensure events are created before creating links

                        # Import event links with updated IDs (FR-2.6)
                        for link_data in event_links_data:
                            old_source_id = link_data.get("source_event_id")
                            old_target_id = link_data.get("target_event_id")

                            # Map old IDs to new IDs
                            new_source_id = old_to_new_id_mapping.get(old_source_id)
                            new_target_id = old_to_new_id_mapping.get(old_target_id)

                            # Only create link if both events were imported
                            if new_source_id and new_target_id:
                                new_link = EventLinkDB(
                                    source_event_id=new_source_id,
                                    target_event_id=new_target_id,
                                    link_type=link_data.get("link_type", "depends_on"),
                                    created_at=datetime.utcnow(),
                                    created_by="import"
                                )
                                session.add(new_link)
                                created_links.append(new_link)

                        await session.commit()

                        return {
                            "success": True,
                            "imported_events": len(created_events),
                            "imported_links": len(created_links),
                            "created_event_ids": [event.id for event in created_events],
                            "id_mappings": old_to_new_id_mapping,
                            "imported_at": datetime.utcnow().isoformat()
                        }

                    except Exception as e:
                        await session.rollback()
                        raise e

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error importing events: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to import events: {e}")

        # CALENDAR REPAIRER ROUTES

        @self.router.post("/calendar/repair")
        async def repair_calendar_events(
            calendar_id: Optional[str] = Query(None, description="Calendar ID to repair (default: primary)"),
            dry_run: bool = Query(False, description="Preview repairs without making changes"),
            force: bool = Query(False, description="Force repair even if already processed"),
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Trigger calendar repair for keyword-prefixed events"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'calendar_repairer'):
                    raise HTTPException(status_code=503, detail="Calendar repairer not available")

                calendar_repairer = self.scheduler.calendar_repairer
                target_calendar_id = calendar_id or 'primary'

                # Get events from calendar
                if hasattr(self.scheduler, 'calendar_client') and self.scheduler.calendar_client:
                    calendar_client = self.scheduler.calendar_client

                    # Fetch events that might need repair
                    events = await calendar_client.get_events(
                        calendar_id=target_calendar_id,
                        time_min=datetime.utcnow() - timedelta(days=30),  # Look back 30 days
                        time_max=datetime.utcnow() + timedelta(days=365)   # Look ahead 1 year
                    )

                    # Filter to keyword events only for efficiency
                    keyword_events = []
                    for event in events:
                        is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(event.get('summary', ''))
                        if is_keyword:
                            if force or calendar_repairer.needs_repair(event)[0]:
                                keyword_events.append(event)

                    if dry_run:
                        # Preview mode - don't actually patch
                        preview_results = []
                        for event in keyword_events:
                            event_title = event.get('summary', '')
                            _, keyword, rule_id = calendar_repairer.is_keyword_event(event_title)

                            if rule_id:
                                payload_text = event_title.split(':', 1)[1].strip()
                                payload = calendar_repairer.parse_payload(payload_text, event_title)
                                rule = calendar_repairer.rules[rule_id]
                                new_title = calendar_repairer.format_title(rule, payload)

                                preview_results.append({
                                    "event_id": event.get('id'),
                                    "original_title": event_title,
                                    "new_title": new_title,
                                    "rule_id": rule_id,
                                    "needs_review": payload.needs_review,
                                    "payload": {
                                        "name": payload.name,
                                        "date": payload.date_iso,
                                        "original_text": payload.original_text
                                    }
                                })

                        return {
                            "success": True,
                            "dry_run": True,
                            "calendar_id": target_calendar_id,
                            "total_events_found": len(events),
                            "keyword_events_found": len(keyword_events),
                            "previews": preview_results,
                            "timestamp": datetime.utcnow().isoformat()
                        }

                    else:
                        # Actually repair the events
                        results = await calendar_repairer.process_events(keyword_events, target_calendar_id)

                        # Summarize results
                        summary = {
                            "total_processed": len(results),
                            "successful": sum(1 for r in results if r.success),
                            "patched": sum(1 for r in results if r.patched),
                            "skipped": sum(1 for r in results if r.skipped),
                            "needs_review": sum(1 for r in results if r.needs_review),
                            "errors": sum(1 for r in results if not r.success)
                        }

                        # Include details for failed or review-needed events
                        details = []
                        for i, result in enumerate(results):
                            if not result.success or result.needs_review:
                                event = keyword_events[i] if i < len(keyword_events) else {}
                                details.append({
                                    "event_id": event.get('id'),
                                    "original_title": event.get('summary'),
                                    "rule_id": result.rule_id,
                                    "success": result.success,
                                    "needs_review": result.needs_review,
                                    "error": result.error,
                                    "new_title": result.new_title
                                })

                        return {
                            "success": True,
                            "dry_run": False,
                            "calendar_id": target_calendar_id,
                            "summary": summary,
                            "details": details,
                            "metrics": calendar_repairer.get_metrics(),
                            "timestamp": datetime.utcnow().isoformat()
                        }

                else:
                    raise HTTPException(status_code=503, detail="Calendar client not available")

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error repairing calendar events: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to repair calendar: {e}")

        @self.router.get("/calendar/repair/rules")
        async def get_repair_rules(
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get available calendar repair rules and their configurations"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'calendar_repairer'):
                    raise HTTPException(status_code=503, detail="Calendar repairer not available")

                calendar_repairer = self.scheduler.calendar_repairer

                # Convert rules to API-friendly format
                rules_info = []
                for rule_id, rule in calendar_repairer.rules.items():
                    rule_info = {
                        "id": rule.id,
                        "keywords": rule.keywords,
                        "title_template": rule.title_template,
                        "description": f"Repairs {'/'.join(rule.keywords)} prefixed events",
                        "all_day": rule.all_day,
                        "rrule": rule.rrule,
                        "warn_offset_days": rule.warn_offset_days,
                        "link_to_rule": rule.link_to_rule,
                        "enrichment_type": rule.enrich.get('event_type') if rule.enrich else None,
                        "enrichment_tags": rule.enrich.get('tags') if rule.enrich else []
                    }
                    rules_info.append(rule_info)

                return {
                    "success": True,
                    "rules": rules_info,
                    "reserved_prefixes": list(calendar_repairer.reserved_prefixes),
                    "parsing_config": {
                        "day_first": calendar_repairer.day_first,
                        "year_optional": calendar_repairer.year_optional,
                        "strict_when_ambiguous": calendar_repairer.strict_when_ambiguous,
                        "accept_separators": calendar_repairer.accept_separators
                    },
                    "enabled": calendar_repairer.enabled
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting repair rules: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get repair rules: {e}")

        @self.router.get("/calendar/repair/metrics")
        async def get_repair_metrics(
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get calendar repair metrics for monitoring"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'calendar_repairer'):
                    raise HTTPException(status_code=503, detail="Calendar repairer not available")

                calendar_repairer = self.scheduler.calendar_repairer
                metrics = calendar_repairer.get_metrics()

                return {
                    "success": True,
                    "metrics": metrics,
                    "timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting repair metrics: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get repair metrics: {e}")

        @self.router.post("/calendar/repair/test")
        async def test_repair_parsing(
            test_data: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Test calendar repair parsing without making any changes"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'calendar_repairer'):
                    raise HTTPException(status_code=503, detail="Calendar repairer not available")

                calendar_repairer = self.scheduler.calendar_repairer

                # Validate input
                if 'event_title' not in test_data:
                    raise HTTPException(status_code=400, detail="event_title is required")

                event_title = test_data['event_title']

                # Test parsing
                is_keyword, keyword, rule_id = calendar_repairer.is_keyword_event(event_title)

                result = {
                    "input": event_title,
                    "is_keyword_event": is_keyword,
                    "detected_keyword": keyword,
                    "rule_id": rule_id,
                    "reserved_prefix": keyword in calendar_repairer.reserved_prefixes if keyword else False
                }

                if is_keyword and rule_id:
                    # Parse the payload
                    payload_text = event_title.split(':', 1)[1].strip()
                    payload = calendar_repairer.parse_payload(payload_text, event_title)

                    # Format new title
                    rule = calendar_repairer.rules[rule_id]
                    new_title = calendar_repairer.format_title(rule, payload)

                    result.update({
                        "parsing_successful": not payload.needs_review,
                        "needs_review": payload.needs_review,
                        "parsed_payload": {
                            "name": payload.name,
                            "date": payload.date_iso,
                            "original_text": payload.original_text
                        },
                        "formatted_title": new_title,
                        "rule_info": {
                            "id": rule.id,
                            "template": rule.title_template,
                            "keywords": rule.keywords
                        }
                    })

                return {
                    "success": True,
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error testing repair parsing: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to test parsing: {e}")

        # ADMIN UI ROUTES

        @self.router.get("/admin", response_class=HTMLResponse)
        async def admin_dashboard(request: Request):
            """Admin dashboard"""
            stats = {
                "total_events": 0,
                "active_workflows": 0,
                "email_templates": 0,
                "integrations": 0
            }

            try:
                async with db_service.get_session() as session:
                    stats["total_events"] = await session.scalar(
                        select(func.count()).select_from(ChronosEventDB)
                    ) or 0

                    stats["active_workflows"] = await session.scalar(
                        select(func.count()).select_from(ActionWorkflowDB).where(ActionWorkflowDB.enabled.is_(True))
                    ) or 0

                    stats["email_templates"] = await session.scalar(
                        select(func.count()).select_from(EmailTemplateDB)
                    ) or 0

                    stats["integrations"] = await session.scalar(
                        select(func.count(func.distinct(ExternalCommandDB.target_system)))
                    ) or 0
            except Exception as exc:
                self.logger.warning(f"Failed to load admin stats: {exc}")

            return self.templates.TemplateResponse("admin/dashboard.html", {
                "request": request,
                "title": "Chronos Admin Dashboard",
                "active_page": "dashboard",
                "stats": stats
            })

        @self.router.get("/admin/system", response_class=HTMLResponse)
        async def system_info(request: Request):
            """System information page"""
            db_info = {
                "environment": self.scheduler.config.get('environment', 'Unknown') if self.scheduler and hasattr(self.scheduler, 'config') else 'Unknown',
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "uptime": 'n/a',
                "tables": [],
                "table_counts": {}
            }

            try:
                async with db_service.get_session() as session:
                    result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                    tables = [row[0] for row in result.fetchall()]
                    db_info["tables"] = tables

                    table_counts = {}
                    for table in tables:
                        if not table.startswith('sqlite_'):
                            count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                            table_counts[table] = count_result.scalar()
                    db_info["table_counts"] = table_counts

            except Exception as exc:
                db_info["error"] = str(exc)

            return self.templates.TemplateResponse("admin/system.html", {
                "request": request,
                "db_info": db_info,
                "title": "System Information",
                "active_page": "system"
            })

        # CALDAV BACKEND ROUTES

        @self.router.get("/caldav/backend/info")
        async def get_caldav_backend_info(
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get CalDAV backend information and status"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                backend_info = await source_manager.get_backend_info()

                return {
                    "success": True,
                    "backend_info": backend_info,
                    "timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting CalDAV backend info: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get backend info: {e}")

        @self.router.get("/caldav/calendars")
        async def list_caldav_calendars(
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """List all available CalDAV calendars"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                calendars = await source_manager.list_calendars()

                calendar_info = []
                for calendar in calendars:
                    calendar_info.append({
                        "id": calendar.id,
                        "alias": calendar.alias,
                        "url": calendar.url,
                        "read_only": calendar.read_only,
                        "timezone": calendar.timezone
                    })

                return {
                    "success": True,
                    "calendars": calendar_info,
                    "count": len(calendars),
                    "timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error listing CalDAV calendars: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list calendars: {e}")

        @self.router.post("/caldav/calendars/{calendar_id}/sync")
        async def sync_caldav_calendar(
            calendar_id: str,
            days_ahead: int = Query(7, description="Number of days ahead to sync"),
            force_refresh: bool = Query(False, description="Force full refresh instead of incremental sync"),
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Manually trigger sync for specific CalDAV calendar"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                calendar = await source_manager.get_calendar_by_id(calendar_id)

                if not calendar:
                    raise HTTPException(status_code=404, detail=f"Calendar {calendar_id} not found")

                adapter = source_manager.get_adapter()

                # Calculate time window
                since = datetime.utcnow()
                until = since + timedelta(days=days_ahead)

                # Fetch events from calendar
                event_result = await adapter.list_events(
                    calendar=calendar,
                    since=since,
                    until=until,
                    sync_token=None if force_refresh else "latest"
                )

                return {
                    "success": True,
                    "calendar_id": calendar_id,
                    "calendar_alias": calendar.alias,
                    "events_fetched": len(event_result.events),
                    "sync_token": event_result.sync_token,
                    "next_page_token": event_result.next_page_token,
                    "time_window": {
                        "since": since.isoformat(),
                        "until": until.isoformat()
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error syncing CalDAV calendar {calendar_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to sync calendar: {e}")

        @self.router.post("/caldav/calendars/{calendar_id}/events")
        async def create_caldav_event(
            calendar_id: str,
            event_data: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Create new event in CalDAV calendar"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                calendar = await source_manager.get_calendar_by_id(calendar_id)

                if not calendar:
                    raise HTTPException(status_code=404, detail=f"Calendar {calendar_id} not found")

                if calendar.read_only:
                    raise HTTPException(status_code=403, detail=f"Calendar {calendar.alias} is read-only")

                # Validate required fields
                if 'summary' not in event_data:
                    raise HTTPException(status_code=400, detail="Event summary is required")

                # Parse datetime fields
                start_time = None
                end_time = None
                if 'start_time' in event_data:
                    start_time = datetime.fromisoformat(event_data['start_time'])
                if 'end_time' in event_data:
                    end_time = datetime.fromisoformat(event_data['end_time'])

                # Normalize event data
                normalized_event = {
                    'summary': event_data['summary'],
                    'description': event_data.get('description', ''),
                    'start_time': start_time,
                    'end_time': end_time,
                    'all_day': event_data.get('all_day', False),
                    'timezone': event_data.get('timezone', calendar.timezone),
                    'rrule': event_data.get('rrule'),
                    'chronos_markers': event_data.get('chronos_markers', {})
                }

                # Create event via adapter
                adapter = source_manager.get_adapter()
                event_id = await adapter.create_event(calendar, normalized_event)

                return {
                    "success": True,
                    "event_id": event_id,
                    "calendar_id": calendar_id,
                    "calendar_alias": calendar.alias,
                    "created_at": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error creating CalDAV event in {calendar_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create event: {e}")

        @self.router.get("/caldav/calendars/{calendar_id}/events/{event_id}")
        async def get_caldav_event(
            calendar_id: str,
            event_id: str,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get specific event from CalDAV calendar"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                calendar = await source_manager.get_calendar_by_id(calendar_id)

                if not calendar:
                    raise HTTPException(status_code=404, detail=f"Calendar {calendar_id} not found")

                adapter = source_manager.get_adapter()
                event = await adapter.get_event(calendar, event_id)

                if not event:
                    raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

                return {
                    "success": True,
                    "event": event,
                    "calendar_id": calendar_id,
                    "calendar_alias": calendar.alias,
                    "timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting CalDAV event {event_id} from {calendar_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get event: {e}")

        @self.router.patch("/caldav/calendars/{calendar_id}/events/{event_id}")
        async def patch_caldav_event(
            calendar_id: str,
            event_id: str,
            patch_data: dict,
            if_match: Optional[str] = Header(None, description="ETag for conflict detection"),
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Patch existing event in CalDAV calendar"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                calendar = await source_manager.get_calendar_by_id(calendar_id)

                if not calendar:
                    raise HTTPException(status_code=404, detail=f"Calendar {calendar_id} not found")

                if calendar.read_only:
                    raise HTTPException(status_code=403, detail=f"Calendar {calendar.alias} is read-only")

                # Parse datetime fields in patch data
                if 'start_time' in patch_data and isinstance(patch_data['start_time'], str):
                    patch_data['start_time'] = datetime.fromisoformat(patch_data['start_time'])
                if 'end_time' in patch_data and isinstance(patch_data['end_time'], str):
                    patch_data['end_time'] = datetime.fromisoformat(patch_data['end_time'])

                # Apply patch via adapter
                adapter = source_manager.get_adapter()
                new_etag = await adapter.patch_event(calendar, event_id, patch_data, if_match)

                return {
                    "success": True,
                    "event_id": event_id,
                    "calendar_id": calendar_id,
                    "calendar_alias": calendar.alias,
                    "new_etag": new_etag,
                    "patched_at": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error patching CalDAV event {event_id} in {calendar_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to patch event: {e}")

        @self.router.delete("/caldav/calendars/{calendar_id}/events/{event_id}")
        async def delete_caldav_event(
            calendar_id: str,
            event_id: str,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Delete event from CalDAV calendar"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                calendar = await source_manager.get_calendar_by_id(calendar_id)

                if not calendar:
                    raise HTTPException(status_code=404, detail=f"Calendar {calendar_id} not found")

                if calendar.read_only:
                    raise HTTPException(status_code=403, detail=f"Calendar {calendar.alias} is read-only")

                adapter = source_manager.get_adapter()
                success = await adapter.delete_event(calendar, event_id)

                if success:
                    return {
                        "success": True,
                        "event_id": event_id,
                        "calendar_id": calendar_id,
                        "calendar_alias": calendar.alias,
                        "deleted_at": datetime.utcnow().isoformat()
                    }
                else:
                    raise HTTPException(status_code=500, detail="Failed to delete event")

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error deleting CalDAV event {event_id} from {calendar_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete event: {e}")

        @self.router.post("/caldav/backend/switch")
        async def switch_caldav_backend(
            switch_data: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Switch between CalDAV and Google Calendar backends"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                new_type = switch_data.get('backend_type')
                if new_type not in ['caldav', 'google']:
                    raise HTTPException(status_code=400, detail="backend_type must be 'caldav' or 'google'")

                new_config = switch_data.get('config')
                source_manager = self.scheduler.source_manager

                # Attempt backend switch
                success = await source_manager.switch_backend(new_type, new_config)

                if success:
                    # Get updated backend info
                    backend_info = await source_manager.get_backend_info()

                    return {
                        "success": True,
                        "switched_to": new_type,
                        "backend_info": backend_info,
                        "switched_at": datetime.utcnow().isoformat()
                    }
                else:
                    raise HTTPException(status_code=500, detail=f"Failed to switch to {new_type} backend")

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error switching CalDAV backend: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to switch backend: {e}")

        @self.router.post("/caldav/connection/test")
        async def test_caldav_connection(
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Test CalDAV backend connection"""
            self._verify_api_key(credentials)

            try:
                if not self.scheduler or not hasattr(self.scheduler, 'source_manager'):
                    raise HTTPException(status_code=503, detail="Calendar source manager not available")

                source_manager = self.scheduler.source_manager
                connection_valid = await source_manager.validate_connection()

                # Get additional connection details
                backend_info = await source_manager.get_backend_info()

                return {
                    "success": True,
                    "connection_valid": connection_valid,
                    "backend_type": backend_info.get('type'),
                    "calendars_available": len(backend_info.get('calendars', [])),
                    "test_timestamp": datetime.utcnow().isoformat()
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error testing CalDAV connection: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to test connection: {e}")

    def _verify_api_key(self, credentials: Optional[HTTPAuthorizationCredentials]):
        """Verify API key authentication"""
        if not credentials or credentials.credentials != self.api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key. Please ensure you're using the correct X-API-Key header.",
                headers={"WWW-Authenticate": "Bearer"}
            )


# Factory functions for backward compatibility

def create_api_routes(scheduler: ChronosScheduler, api_key: str) -> APIRouter:
    """Create unified API routes (replaces ChronosAPIRoutes)"""
    routes = ChronosUnifiedAPIRoutes(scheduler, api_key)
    return routes.router

def create_enhanced_routes(scheduler: ChronosScheduler, api_key: str) -> APIRouter:
    """Create enhanced routes (now part of unified routes)"""
    routes = ChronosUnifiedAPIRoutes(scheduler, api_key)
    return routes.router

def create_v22_router(api_key: str) -> APIRouter:
    """Create v2.2 routes (now part of unified routes)"""
    routes = ChronosUnifiedAPIRoutes(None, api_key)  # Scheduler may be None for v2.2 routes
    return routes.router

def create_admin_routes(email_service=None) -> APIRouter:
    """Create admin routes (now part of unified routes)"""
    routes = ChronosUnifiedAPIRoutes(None, "admin-key", email_service)
    return routes.router

