"""
v2.2 Feature API Routes for Chronos Engine
Event links, sub-tasks, availability checking, and workflow management
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from src.core.database import db_service, get_db_session
from src.core.models import (
    EventLinkDB, ActionWorkflowDB, ExternalCommandDB, ChronosEventDB,
    EventLink, ActionWorkflow, SubTask
)
from src.api.schemas import (
    EventLinkCreate, EventLinkResponse,
    AvailabilityRequest, AvailabilityResponse, AvailabilitySlot,
    WorkflowCreate, WorkflowResponse,
    SubTaskSchema, EventUpdate
)


class ChronosV22APIRoutes:
    """v2.2 API routes for enhanced features"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)
        self.router = APIRouter(prefix="/api/v2.2")
        self.security = HTTPBearer(auto_error=False)

        # Register routes
        self._register_routes()

    def _verify_api_key(self, credentials: HTTPAuthorizationCredentials):
        """Verify API key"""
        if not credentials or credentials.credentials != self.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    def _register_routes(self):
        """Register all v2.2 API routes"""

        # Event Links Routes
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

        # Availability Routes
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

        # Workflow Routes
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

        # Command API for external polling
        @self.router.get("/commands/{system_id}")
        async def get_pending_commands(
            system_id: str,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Get pending commands for a system and mark them as processing"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    # Get pending commands for this system
                    query = select(ExternalCommandDB).where(
                        and_(
                            ExternalCommandDB.target_system == system_id,
                            ExternalCommandDB.status == "pending"
                        )
                    ).order_by(ExternalCommandDB.created_at)

                    result = await session.execute(query)
                    commands = result.scalars().all()

                    # Mark commands as processing
                    command_responses = []
                    for cmd in commands:
                        cmd.status = "processing"
                        cmd.processed_at = datetime.utcnow()

                        command_responses.append({
                            "id": cmd.id,
                            "command": cmd.command,
                            "parameters": cmd.parameters,
                            "created_at": cmd.created_at.isoformat(),
                            "status": cmd.status
                        })

                    await session.commit()

                    return {
                        "system_id": system_id,
                        "commands": command_responses,
                        "count": len(command_responses)
                    }

            except Exception as e:
                self.logger.error(f"Error getting pending commands: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get pending commands: {e}")

        @self.router.post("/commands/{command_id}/complete")
        async def complete_command(
            command_id: int,
            result: Dict[str, Any],
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """Mark a command as completed with results"""
            self._verify_api_key(credentials)

            try:
                async with db_service.get_session() as session:
                    query = select(ExternalCommandDB).where(ExternalCommandDB.id == command_id)
                    result_db = await session.execute(query)
                    command = result_db.scalar_one_or_none()

                    if not command:
                        raise HTTPException(status_code=404, detail="Command not found")

                    # Update command status
                    command.status = "completed"
                    command.completed_at = datetime.utcnow()
                    command.result = result

                    await session.commit()

                return {"message": "Command marked as completed", "command_id": command_id}

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error completing command: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to complete command: {e}")


def create_v22_router(api_key: str) -> APIRouter:
    """Create and return the v2.2 API router"""
    routes = ChronosV22APIRoutes(api_key)
    return routes.router