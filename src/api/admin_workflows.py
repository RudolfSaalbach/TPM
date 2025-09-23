"""
Admin Workflows API Router
Handles general workflow management for admin interface
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import and_, or_, func, select, update, delete
from sqlalchemy.orm import Session, selectinload

from src.core.database import db_service, get_db_session
from src.core.models import WorkflowDB, WorkflowExecutionDB, Workflow, WorkflowExecution
from src.api.schemas import (
    AdminWorkflowCreate, AdminWorkflowUpdate, AdminWorkflowResponse,
    AdminWorkflowsListResponse, AdminWorkflowExecutionResponse
)
from src.api.dependencies import verify_api_key
from src.api.error_handling import handle_api_errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/workflows", tags=["admin-workflows"])


@router.get("/", response_model=AdminWorkflowsListResponse)
async def list_workflows(
    authenticated: bool = Depends(verify_api_key),
    q: Optional[str] = Query(None, description="Search query"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page")
):
    """List all admin workflows with filtering and pagination"""
    try:
        async with db_service.get_session() as session:
            # Build query
            query = select(WorkflowDB)

            # Apply filters
            if q:
                query = query.where(
                    or_(
                        WorkflowDB.name.ilike(f"%{q}%"),
                        WorkflowDB.description.ilike(f"%{q}%")
                    )
                )

            if status:
                query = query.where(WorkflowDB.status == status)

            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            query = query.order_by(WorkflowDB.updated_at.desc())

            # Execute query
            result = await session.execute(query)
            db_workflows = result.scalars().all()

            # Convert to response models
            workflows = []
            for db_workflow in db_workflows:
                workflows.append(AdminWorkflowResponse(
                    id=db_workflow.id,
                    name=db_workflow.name,
                    description=db_workflow.description,
                    status=db_workflow.status,
                    triggers=db_workflow.triggers or [],
                    actions=db_workflow.actions or [],
                    execution_count=db_workflow.execution_count,
                    last_execution=db_workflow.last_execution,
                    success_rate=db_workflow.success_rate,
                    avg_runtime=db_workflow.avg_runtime,
                    created_at=db_workflow.created_at,
                    updated_at=db_workflow.updated_at
                ))

            return AdminWorkflowsListResponse(
                total=total,
                page=page,
                page_size=page_size,
                workflows=workflows
            )

    except Exception as e:
        logger.error(f"Error listing workflows: {e}")
        raise HTTPException(
            status_code=http_http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list workflows: {str(e)}"
        )


@router.post("/", response_model=AdminWorkflowResponse, status_code=http_status.HTTP_201_CREATED)
async def create_workflow(
    workflow_data: AdminWorkflowCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new admin workflow"""
    try:
        async with db_service.get_session() as session:
            # Convert to domain model
            workflow = Workflow(
                name=workflow_data.name,
                description=workflow_data.description,
                status=workflow_data.status,
                triggers=[trigger.dict() for trigger in workflow_data.triggers],
                actions=[action.dict() for action in workflow_data.actions]
            )

            # Save to database
            db_workflow = workflow.to_db_model()
            session.add(db_workflow)
            await session.commit()
            await session.refresh(db_workflow)

            return AdminWorkflowResponse(
                id=db_workflow.id,
                name=db_workflow.name,
                description=db_workflow.description,
                status=db_workflow.status,
                triggers=db_workflow.triggers or [],
                actions=db_workflow.actions or [],
                execution_count=db_workflow.execution_count,
                last_execution=db_workflow.last_execution,
                success_rate=db_workflow.success_rate,
                avg_runtime=db_workflow.avg_runtime,
                created_at=db_workflow.created_at,
                updated_at=db_workflow.updated_at
            )

    except Exception as e:
        logger.error(f"Error creating workflow: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create workflow: {str(e)}"
        )


@router.get("/{workflow_id}", response_model=AdminWorkflowResponse)
async def get_workflow(
    workflow_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Get a specific workflow by ID"""
    try:
        async with db_service.get_session() as session:
            db_workflow = await session.get(WorkflowDB, workflow_id)
            if not db_workflow:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            return AdminWorkflowResponse(
                id=db_workflow.id,
                name=db_workflow.name,
                description=db_workflow.description,
                status=db_workflow.status,
                triggers=db_workflow.triggers or [],
                actions=db_workflow.actions or [],
                execution_count=db_workflow.execution_count,
                last_execution=db_workflow.last_execution,
                success_rate=db_workflow.success_rate,
                avg_runtime=db_workflow.avg_runtime,
                created_at=db_workflow.created_at,
                updated_at=db_workflow.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get workflow: {str(e)}"
        )


@router.put("/{workflow_id}", response_model=AdminWorkflowResponse)
async def update_workflow(
    workflow_id: int,
    workflow_data: AdminWorkflowUpdate,
    authenticated: bool = Depends(verify_api_key)
):
    """Update an existing workflow"""
    try:
        async with db_service.get_session() as session:
            db_workflow = await session.get(WorkflowDB, workflow_id)
            if not db_workflow:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            # Update fields
            if workflow_data.name is not None:
                db_workflow.name = workflow_data.name
            if workflow_data.description is not None:
                db_workflow.description = workflow_data.description
            if workflow_data.status is not None:
                db_workflow.status = workflow_data.status
            if workflow_data.triggers is not None:
                db_workflow.triggers = [trigger.dict() for trigger in workflow_data.triggers]
            if workflow_data.actions is not None:
                db_workflow.actions = [action.dict() for action in workflow_data.actions]

            db_workflow.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(db_workflow)

            return AdminWorkflowResponse(
                id=db_workflow.id,
                name=db_workflow.name,
                description=db_workflow.description,
                status=db_workflow.status,
                triggers=db_workflow.triggers or [],
                actions=db_workflow.actions or [],
                execution_count=db_workflow.execution_count,
                last_execution=db_workflow.last_execution,
                success_rate=db_workflow.success_rate,
                avg_runtime=db_workflow.avg_runtime,
                created_at=db_workflow.created_at,
                updated_at=db_workflow.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update workflow: {str(e)}"
        )


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete a workflow"""
    try:
        async with db_service.get_session() as session:
            db_workflow = await session.get(WorkflowDB, workflow_id)
            if not db_workflow:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            await session.delete(db_workflow)
            await session.commit()

            return {"success": True, "message": f"Workflow {workflow_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete workflow: {str(e)}"
        )


@router.post("/{workflow_id}/pause")
async def pause_workflow(
    workflow_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Pause a workflow"""
    try:
        async with db_service.get_session() as session:
            db_workflow = await session.get(WorkflowDB, workflow_id)
            if not db_workflow:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            db_workflow.status = "paused"
            db_workflow.updated_at = datetime.utcnow()
            await session.commit()

            return {"success": True, "message": f"Workflow {workflow_id} paused"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause workflow: {str(e)}"
        )


@router.post("/{workflow_id}/resume")
async def resume_workflow(
    workflow_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Resume a paused workflow"""
    try:
        async with db_service.get_session() as session:
            db_workflow = await session.get(WorkflowDB, workflow_id)
            if not db_workflow:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            db_workflow.status = "active"
            db_workflow.updated_at = datetime.utcnow()
            await session.commit()

            return {"success": True, "message": f"Workflow {workflow_id} resumed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume workflow: {str(e)}"
        )


@router.get("/{workflow_id}/executions", response_model=List[AdminWorkflowExecutionResponse])
async def get_workflow_executions(
    workflow_id: int,
    authenticated: bool = Depends(verify_api_key),
    limit: int = Query(50, ge=1, le=500, description="Number of executions to return")
):
    """Get recent executions for a workflow"""
    try:
        async with db_service.get_session() as session:
            # Verify workflow exists
            db_workflow = await session.get(WorkflowDB, workflow_id)
            if not db_workflow:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            # Get recent executions
            query = select(WorkflowExecutionDB).where(
                WorkflowExecutionDB.workflow_id == workflow_id
            ).order_by(WorkflowExecutionDB.executed_at.desc()).limit(limit)

            result = await session.execute(query)
            db_executions = result.scalars().all()

            executions = []
            for db_execution in db_executions:
                executions.append(AdminWorkflowExecutionResponse(
                    id=db_execution.id,
                    workflow_id=db_execution.workflow_id,
                    status=db_execution.status,
                    runtime_seconds=db_execution.runtime_seconds,
                    error_message=db_execution.error_message,
                    result_data=db_execution.result_data,
                    executed_at=db_execution.executed_at
                ))

            return executions

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow executions for {workflow_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get workflow executions: {str(e)}"
        )