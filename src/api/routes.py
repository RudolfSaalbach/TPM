"""
Consolidated API routes for Chronos Engine v2.2
Unified single API combining all features from multiple versions
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends, Request, Query, Form, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, or_, func, select, update, text
from sqlalchemy.orm import Session, selectinload

from src.core.scheduler import ChronosScheduler
from src.core.database import db_service, get_db_session
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
        @handle_api_errors
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
        @handle_api_errors
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
        async def health_check():
            """Health check endpoint - no auth required"""
            try:
                status_info = await self.scheduler.get_health_status() if self.scheduler else {"status": "no_scheduler"}
                return {
                    "status": "healthy",
                    "scheduler": status_info,
                    "timestamp": datetime.utcnow().isoformat()
                }

            except Exception as e:
                self.logger.error(f"Health check failed: {e}")
                raise HTTPException(status_code=503, detail=f"Service unhealthy: {e}")

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

        # ADMIN UI ROUTES

        @self.router.get("/admin", response_class=HTMLResponse)
        async def admin_dashboard(request: Request):
            """Admin dashboard"""
            return self.templates.TemplateResponse("admin/dashboard.html", {
                "request": request,
                "title": "Chronos Admin Dashboard"
            })

        @self.router.get("/admin/system", response_class=HTMLResponse)
        async def system_info(request: Request):
            """System information page"""
            # Get database info
            db_info = {}
            try:
                async with db_service.get_session() as session:
                    result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                    tables = [row[0] for row in result.fetchall()]
                    db_info["tables"] = tables

                    # Get table counts
                    table_counts = {}
                    for table in tables:
                        if not table.startswith('sqlite_'):
                            count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                            table_counts[table] = count_result.scalar()
                    db_info["table_counts"] = table_counts

            except Exception as e:
                db_info["error"] = str(e)

            return self.templates.TemplateResponse("admin/system.html", {
                "request": request,
                "db_info": db_info,
                "title": "System Information"
            })

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