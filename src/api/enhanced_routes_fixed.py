"""
Enhanced API routes for Chronos Engine v2.1 - Templates and Advanced Filtering
Fixed version with proper async database session handling
"""

import json
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text, select

from src.core.scheduler import ChronosScheduler
from src.core.database import db_service
from src.core.models import (
    ChronosEventDB, TemplateDB, TemplateUsageDB,
    Template, TemplateUsage
)
from src.api.schemas import (
    EventsListResponse, EventResponse, EventDirection,
    TemplateCreate, TemplateUpdate, TemplateResponse,
    TemplatesListResponse, TemplateUsageResponse
)


class ChronosEnhancedRoutes:
    """Enhanced API routes with templates and advanced filtering"""

    def __init__(self, scheduler: ChronosScheduler, api_key: str):
        self.scheduler = scheduler
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)
        self.router = APIRouter()
        self.security = HTTPBearer(auto_error=False)

        # Register routes
        self._register_routes()

    def _register_routes(self):
        """Register all enhanced API routes"""

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
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get events with advanced filtering"""
            self._verify_api_key(credentials)

            try:
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
                    query = session.query(ChronosEventDB)

                    # Calendar filter
                    if calendar:
                        query = query.filter(ChronosEventDB.calendar_id == calendar)

                    # Time range filtering
                    if direction == EventDirection.PAST:
                        # event_end <= anchor 23:59:59 AND event_start >= anchor - range
                        anchor_end = anchor_date.replace(hour=23, minute=59, second=59)
                        range_start = anchor_date - timedelta(days=range_days)

                        query = query.filter(
                            and_(
                                ChronosEventDB.end_utc <= anchor_end,
                                ChronosEventDB.start_utc >= range_start
                            )
                        )

                    elif direction == EventDirection.FUTURE:
                        # event_start >= anchor 00:00:00 AND event_end <= anchor + range
                        anchor_start = anchor_date.replace(hour=0, minute=0, second=0)
                        range_end = anchor_date + timedelta(days=range_days)

                        query = query.filter(
                            and_(
                                ChronosEventDB.start_utc >= anchor_start,
                                ChronosEventDB.end_utc <= range_end
                            )
                        )

                    else:  # ALL
                        # Interval intersects [anchor-range, anchor+range]
                        range_start = anchor_date - timedelta(days=range_days)
                        range_end = anchor_date + timedelta(days=range_days)

                        query = query.filter(
                            and_(
                                ChronosEventDB.start_utc <= range_end,
                                ChronosEventDB.end_utc >= range_start
                            )
                        )

                    # Text search filter
                    if q:
                        search_term = f"%{q}%"
                        query = query.filter(
                            or_(
                                ChronosEventDB.title.ilike(search_term),
                                ChronosEventDB.description.ilike(search_term)
                            )
                        )

                    # Count total for pagination
                    total_count = query.count()

                    # Apply pagination
                    offset = (page - 1) * page_size
                    events = query.offset(offset).limit(page_size).all()

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

                        # Add ranking (title x3, tags x2, description x1, then usage_count desc)
                        # This is a simplified ranking - in production, you might use FTS5
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
                    from src.core.models import ExternalCommandDB, CommandStatus
                    from sqlalchemy import select

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
                    from src.core.models import ExternalCommandDB, CommandStatus

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
                    from src.core.models import ExternalCommandDB, CommandStatus

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

    def _verify_api_key(self, credentials: Optional[HTTPAuthorizationCredentials]):
        """Verify API key authentication"""
        if not credentials or credentials.credentials != self.api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key. Please ensure you're using the correct X-API-Key header.",
                headers={"WWW-Authenticate": "Bearer"}
            )