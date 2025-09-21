"""
Events API Router
Handles events, templates, and event-links endpoints
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import and_, or_, func, select, update
from sqlalchemy.orm import Session, selectinload

from src.core.scheduler import ChronosScheduler
from src.core.database import db_service, get_db_session
from src.core.models import (
    ChronosEvent, Priority, EventType, EventStatus,
    ChronosEventDB, TemplateDB, TemplateUsageDB,
    EventLinkDB, Template, TemplateUsage, EventLink
)
from src.api.schemas import (
    EventCreate, EventUpdate, EventResponse,
    EventsListResponse, EventDirection,
    TemplateCreate, TemplateUpdate, TemplateResponse,
    TemplatesListResponse, TemplateUsageResponse,
    EventLinkCreate, EventLinkResponse
)
from src.api.dependencies import verify_api_key, get_scheduler
from src.api.error_handling import handle_api_errors

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
@handle_api_errors
async def create_event(
    event_data: EventCreate,
    authenticated: bool = Depends(verify_api_key),
    scheduler: ChronosScheduler = Depends(get_scheduler)
):
    """Create a new event with transactional consistency"""
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
        created_event = await scheduler.create_event(chronos_event)

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

    except Exception as e:
        logger.error(f"Error creating event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}"
        )


@router.get("/events", response_model=EventsListResponse)
@handle_api_errors
async def get_events_advanced(
    authenticated: bool = Depends(verify_api_key),
    anchor: str = Query(default_factory=lambda: datetime.utcnow().strftime('%Y-%m-%d'),
                       description="Anchor date in YYYY-MM-DD format"),
    direction: EventDirection = Query(EventDirection.FUTURE, description="Direction from anchor"),
    days: int = Query(7, ge=1, le=365, description="Number of days to retrieve"),
    calendar: Optional[str] = Query(None, description="Filter by calendar ID"),
    q: Optional[str] = Query(None, description="Full-text search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page")
):
    """Advanced event listing with filtering, search, and pagination"""
    try:
        # Parse anchor date
        anchor_date = datetime.strptime(anchor, '%Y-%m-%d').date()

        # Calculate date range
        if direction == EventDirection.FUTURE:
            start_date = anchor_date
            end_date = anchor_date + timedelta(days=days)
        elif direction == EventDirection.PAST:
            end_date = anchor_date
            start_date = anchor_date - timedelta(days=days)
        else:  # ALL
            start_date = anchor_date - timedelta(days=days//2)
            end_date = anchor_date + timedelta(days=days//2)

        async with db_service.get_session() as session:
            # Build query
            query = select(ChronosEventDB)

            # Date range filter
            query = query.where(
                and_(
                    ChronosEventDB.start_time >= start_date,
                    ChronosEventDB.start_time <= end_date
                )
            )

            # Calendar filter
            if calendar:
                query = query.where(ChronosEventDB.calendar_id == calendar)

            # Full-text search
            if q:
                search_term = f"%{q}%"
                query = query.where(
                    or_(
                        ChronosEventDB.title.ilike(search_term),
                        ChronosEventDB.description.ilike(search_term),
                        ChronosEventDB.location.ilike(search_term)
                    )
                )

            # Pagination
            total_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(total_query)
            total_count = total_result.scalar()

            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

            # Order by start_time
            query = query.order_by(ChronosEventDB.start_time)

            # Execute query
            result = await session.execute(query)
            events_db = result.scalars().all()

            # Convert to response format
            events = [
                EventResponse(
                    id=event.id,
                    title=event.title,
                    description=event.description,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    priority=event.priority.name if event.priority else "MEDIUM",
                    event_type=event.event_type.name if event.event_type else "TASK",
                    status=event.status.name if event.status else "PENDING",
                    tags=event.tags or [],
                    attendees=event.attendees or [],
                    location=event.location,
                    calendar_id=event.calendar_id,
                    created_at=event.created_at,
                    updated_at=event.updated_at
                )
                for event in events_db
            ]

            return EventsListResponse(
                events=events,
                total_count=total_count,
                page=page,
                page_size=page_size,
                filters={
                    "anchor": anchor,
                    "direction": direction.value,
                    "days": days,
                    "calendar": calendar,
                    "q": q
                }
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error retrieving events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve events: {str(e)}"
        )


@router.put("/events/{event_id}", response_model=EventResponse)
@handle_api_errors
async def update_event(
    event_id: str,
    event_data: EventUpdate,
    authenticated: bool = Depends(verify_api_key),
    scheduler: ChronosScheduler = Depends(get_scheduler)
):
    """Update an existing event"""
    try:
        async with db_service.get_session() as session:
            # Find existing event
            query = select(ChronosEventDB).where(ChronosEventDB.id == event_id)
            result = await session.execute(query)
            event_db = result.scalar_one_or_none()

            if not event_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Event {event_id} not found"
                )

            # Update fields
            update_data = event_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                if hasattr(event_db, field):
                    setattr(event_db, field, value)

            event_db.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(event_db)

            return EventResponse(
                id=event_db.id,
                title=event_db.title,
                description=event_db.description,
                start_time=event_db.start_time,
                end_time=event_db.end_time,
                priority=event_db.priority.name if event_db.priority else "MEDIUM",
                event_type=event_db.event_type.name if event_db.event_type else "TASK",
                status=event_db.status.name if event_db.status else "PENDING",
                tags=event_db.tags or [],
                attendees=event_db.attendees or [],
                location=event_db.location,
                calendar_id=event_db.calendar_id,
                created_at=event_db.created_at,
                updated_at=event_db.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating event {event_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update event: {str(e)}"
        )


# Templates endpoints
@router.get("/templates", response_model=TemplatesListResponse)
@handle_api_errors
async def get_templates(
    authenticated: bool = Depends(verify_api_key),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    q: Optional[str] = Query(None, description="Search query")
):
    """Get paginated list of templates with optional filtering"""
    try:
        async with db_service.get_session() as session:
            # Build query
            query = select(TemplateDB).options(selectinload(TemplateDB.usage))

            # Category filter
            if category:
                query = query.where(TemplateDB.category == category)

            # Search filter
            if q:
                search_term = f"%{q}%"
                query = query.where(
                    or_(
                        TemplateDB.name.ilike(search_term),
                        TemplateDB.description.ilike(search_term)
                    )
                )

            # Count total
            total_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(total_query)
            total_count = total_result.scalar()

            # Pagination
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            query = query.order_by(TemplateDB.ranking.desc(), TemplateDB.name)

            # Execute
            result = await session.execute(query)
            templates_db = result.scalars().all()

            # Convert to response
            templates = []
            for template in templates_db:
                templates.append(TemplateResponse(
                    id=template.id,
                    name=template.name,
                    description=template.description,
                    category=template.category,
                    template_data=template.template_data,
                    default_duration_minutes=template.default_duration_minutes,
                    default_priority=template.default_priority.name if template.default_priority else "MEDIUM",
                    default_time=template.default_time,
                    ranking=template.ranking,
                    is_active=template.is_active,
                    usage_count=len(template.usage) if template.usage else 0,
                    created_at=template.created_at,
                    updated_at=template.updated_at
                ))

            return TemplatesListResponse(
                templates=templates,
                total_count=total_count,
                page=page,
                page_size=page_size
            )

    except Exception as e:
        logger.error(f"Error retrieving templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve templates: {str(e)}"
        )


@router.post("/templates", response_model=TemplateResponse)
@handle_api_errors
async def create_template(
    template_data: TemplateCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new template"""
    try:
        template_id = str(uuid.uuid4())

        async with db_service.get_session() as session:
            template_db = TemplateDB(
                id=template_id,
                name=template_data.name,
                description=template_data.description,
                category=template_data.category,
                template_data=template_data.template_data,
                default_duration_minutes=template_data.default_duration_minutes,
                default_priority=Priority[template_data.default_priority] if template_data.default_priority else Priority.MEDIUM,
                default_time=template_data.default_time,
                ranking=template_data.ranking,
                is_active=template_data.is_active,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            session.add(template_db)
            await session.commit()
            await session.refresh(template_db)

            return TemplateResponse(
                id=template_db.id,
                name=template_db.name,
                description=template_db.description,
                category=template_db.category,
                template_data=template_db.template_data,
                default_duration_minutes=template_db.default_duration_minutes,
                default_priority=template_db.default_priority.name,
                default_time=template_db.default_time,
                ranking=template_db.ranking,
                is_active=template_db.is_active,
                usage_count=0,
                created_at=template_db.created_at,
                updated_at=template_db.updated_at
            )

    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )


@router.put("/templates/{template_id}", response_model=TemplateResponse)
@handle_api_errors
async def update_template(
    template_id: str,
    template_data: TemplateUpdate,
    authenticated: bool = Depends(verify_api_key)
):
    """Update an existing template"""
    try:
        async with db_service.get_session() as session:
            # Find existing template
            query = select(TemplateDB).where(TemplateDB.id == template_id)
            result = await session.execute(query)
            template_db = result.scalar_one_or_none()

            if not template_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            # Update fields
            update_data = template_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                if field == "default_priority" and value:
                    template_db.default_priority = Priority[value]
                elif hasattr(template_db, field):
                    setattr(template_db, field, value)

            template_db.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(template_db)

            return TemplateResponse(
                id=template_db.id,
                name=template_db.name,
                description=template_db.description,
                category=template_db.category,
                template_data=template_db.template_data,
                default_duration_minutes=template_db.default_duration_minutes,
                default_priority=template_db.default_priority.name,
                default_time=template_db.default_time,
                ranking=template_db.ranking,
                is_active=template_db.is_active,
                usage_count=0,  # TODO: Calculate from usage table
                created_at=template_db.created_at,
                updated_at=template_db.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update template: {str(e)}"
        )


@router.delete("/templates/{template_id}")
@handle_api_errors
async def delete_template(
    template_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete a template"""
    try:
        async with db_service.get_session() as session:
            # Find and delete template
            query = select(TemplateDB).where(TemplateDB.id == template_id)
            result = await session.execute(query)
            template_db = result.scalar_one_or_none()

            if not template_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            await session.delete(template_db)
            await session.commit()

            return {"message": f"Template {template_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete template: {str(e)}"
        )


@router.post("/templates/{template_id}/use")
@handle_api_errors
async def use_template(
    template_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Record template usage for analytics"""
    try:
        usage_id = str(uuid.uuid4())

        async with db_service.get_session() as session:
            # Verify template exists
            template_query = select(TemplateDB).where(TemplateDB.id == template_id)
            template_result = await session.execute(template_query)
            template_db = template_result.scalar_one_or_none()

            if not template_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            # Record usage
            usage_db = TemplateUsageDB(
                id=usage_id,
                template_id=template_id,
                used_at=datetime.utcnow(),
                context={}  # Could be extended with usage context
            )

            session.add(usage_db)
            await session.commit()

            return TemplateUsageResponse(
                id=usage_id,
                template_id=template_id,
                used_at=usage_db.used_at,
                context=usage_db.context
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording template usage for {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record template usage: {str(e)}"
        )


# Event Links endpoints
@router.post("/event-links", response_model=EventLinkResponse)
@handle_api_errors
async def create_event_link(
    link_data: EventLinkCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new event link"""
    try:
        link_id = str(uuid.uuid4())

        async with db_service.get_session() as session:
            link_db = EventLinkDB(
                id=link_id,
                source_event_id=link_data.source_event_id,
                target_event_id=link_data.target_event_id,
                link_type=link_data.link_type,
                metadata=link_data.metadata or {},
                created_at=datetime.utcnow()
            )

            session.add(link_db)
            await session.commit()
            await session.refresh(link_db)

            return EventLinkResponse(
                id=link_db.id,
                source_event_id=link_db.source_event_id,
                target_event_id=link_db.target_event_id,
                link_type=link_db.link_type,
                metadata=link_db.metadata,
                created_at=link_db.created_at
            )

    except Exception as e:
        logger.error(f"Error creating event link: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event link: {str(e)}"
        )


@router.get("/events/{event_id}/links", response_model=List[EventLinkResponse])
@handle_api_errors
async def get_event_links(
    event_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Get all links for a specific event"""
    try:
        async with db_service.get_session() as session:
            # Find links where this event is either source or target
            query = select(EventLinkDB).where(
                or_(
                    EventLinkDB.source_event_id == event_id,
                    EventLinkDB.target_event_id == event_id
                )
            )

            result = await session.execute(query)
            links_db = result.scalars().all()

            return [
                EventLinkResponse(
                    id=link.id,
                    source_event_id=link.source_event_id,
                    target_event_id=link.target_event_id,
                    link_type=link.link_type,
                    metadata=link.metadata,
                    created_at=link.created_at
                )
                for link in links_db
            ]

    except Exception as e:
        logger.error(f"Error retrieving event links for {event_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve event links: {str(e)}"
        )


@router.delete("/event-links/{link_id}")
@handle_api_errors
async def delete_event_link(
    link_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete an event link"""
    try:
        async with db_service.get_session() as session:
            # Find and delete link
            query = select(EventLinkDB).where(EventLinkDB.id == link_id)
            result = await session.execute(query)
            link_db = result.scalar_one_or_none()

            if not link_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Event link {link_id} not found"
                )

            await session.delete(link_db)
            await session.commit()

            return {"message": f"Event link {link_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting event link {link_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete event link: {str(e)}"
        )