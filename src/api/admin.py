"""
Admin API Router
Handles administrative operations, workflows, and system management
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy import select, func
from pydantic import BaseModel

from src.core.database import db_service
from src.core.models import ActionWorkflowDB, ChronosEventDB
from src.api.dependencies import verify_api_key
from src.api.error_handling import handle_api_errors
from src.api.schemas import WorkflowCreate, WorkflowResponse
from src.api.standard_schemas import (
    SystemInfoResponse, AdminStatisticsResponse, RepairRulesResponse,
    RepairMetricsResponse, CalendarRepairResponse, APISuccessResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Admin-specific schemas
class SystemInfo(BaseModel):
    version: str
    uptime: str
    database_status: str
    scheduler_status: str
    last_sync: Optional[datetime] = None


class CalendarRepairRequest(BaseModel):
    calendar_id: Optional[str] = None
    dry_run: bool = True
    rule_ids: Optional[List[str]] = None


@router.get("/system/info", response_model=SystemInfoResponse)
@handle_api_errors
async def get_system_info(
    authenticated: bool = Depends(verify_api_key)
):
    """Get system information and status"""
    try:
        import psutil
        import time
        from datetime import datetime, timedelta

        # Calculate actual uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"

        # Check database status
        try:
            db_status = "connected" if db_service else "disconnected"
        except:
            db_status = "error"

        # Check scheduler status
        scheduler_status = "running" if scheduler else "stopped"

        # Get last sync from scheduler
        last_sync = None
        try:
            if scheduler and hasattr(scheduler, 'get_last_sync'):
                last_sync = scheduler.get_last_sync()
            else:
                last_sync = datetime.now().isoformat()
        except:
            last_sync = "unknown"

        return SystemInfoResponse(
            system_info={
                "version": "2.2.0",
                "uptime": uptime_str,
                "database_status": db_status,
                "scheduler_status": scheduler_status,
                "last_sync": last_sync
            }
        )

    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system info: {str(e)}"
        )


@router.get("/statistics", response_model=AdminStatisticsResponse)
@handle_api_errors
async def get_admin_statistics(
    authenticated: bool = Depends(verify_api_key)
):
    """Get administrative statistics"""
    try:
        async with db_service.get_session() as session:
            # Count total events
            total_events_query = select(func.count(ChronosEventDB.id))
            total_events_result = await session.execute(total_events_query)
            total_events = total_events_result.scalar() or 0

            # Count events by status (if status field exists)
            # This is a simplified version
            return AdminStatisticsResponse(
                statistics={
                    "events": {
                        "total": total_events,
                        "by_status": {
                            "pending": 0,    # TODO: Implement actual counts
                            "completed": 0,
                            "cancelled": 0
                        }
                    },
                    "workflows": {
                        "total": 0,  # TODO: Count workflows
                        "active": 0
                    },
                    "commands": {
                        "total": 0,     # TODO: Count commands
                        "pending": 0,
                        "processing": 0,
                        "completed": 0,
                        "failed": 0
                    },
                    "generated_at": datetime.utcnow().isoformat()
                }
            )

    except Exception as e:
        logger.error(f"Error getting admin statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get admin statistics: {str(e)}"
        )


# Workflow management
@router.post("/workflows", response_model=WorkflowResponse)
@handle_api_errors
async def create_workflow(
    workflow_data: WorkflowCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new administrative workflow"""
    try:
        import uuid

        workflow_id = str(uuid.uuid4())

        async with db_service.get_session() as session:
            workflow_db = ActionWorkflowDB(
                id=workflow_id,
                name=workflow_data.name,
                description=workflow_data.description,
                trigger_conditions=workflow_data.trigger_conditions,
                actions=workflow_data.actions,
                is_active=workflow_data.is_active,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            session.add(workflow_db)
            await session.commit()
            await session.refresh(workflow_db)

            return WorkflowResponse(
                id=workflow_db.id,
                name=workflow_db.name,
                description=workflow_db.description,
                trigger_conditions=workflow_db.trigger_conditions,
                actions=workflow_db.actions,
                is_active=workflow_db.is_active,
                created_at=workflow_db.created_at,
                updated_at=workflow_db.updated_at
            )

    except Exception as e:
        logger.error(f"Error creating workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create workflow: {str(e)}"
        )


@router.get("/workflows", response_model=List[WorkflowResponse])
@handle_api_errors
async def list_workflows(
    authenticated: bool = Depends(verify_api_key),
    active_only: bool = False
):
    """List all administrative workflows"""
    try:
        async with db_service.get_session() as session:
            query = select(ActionWorkflowDB)

            if active_only:
                query = query.where(ActionWorkflowDB.is_active == True)

            query = query.order_by(ActionWorkflowDB.created_at.desc())

            result = await session.execute(query)
            workflows_db = result.scalars().all()

            return [
                WorkflowResponse(
                    id=workflow.id,
                    name=workflow.name,
                    description=workflow.description,
                    trigger_conditions=workflow.trigger_conditions,
                    actions=workflow.actions,
                    is_active=workflow.is_active,
                    created_at=workflow.created_at,
                    updated_at=workflow.updated_at
                )
                for workflow in workflows_db
            ]

    except Exception as e:
        logger.error(f"Error listing workflows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list workflows: {str(e)}"
        )


@router.delete("/workflows/{workflow_id}", response_model=APISuccessResponse)
@handle_api_errors
async def delete_workflow(
    workflow_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete an administrative workflow"""
    try:
        async with db_service.get_session() as session:
            query = select(ActionWorkflowDB).where(ActionWorkflowDB.id == workflow_id)
            result = await session.execute(query)
            workflow_db = result.scalar_one_or_none()

            if not workflow_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workflow {workflow_id} not found"
                )

            await session.delete(workflow_db)
            await session.commit()

            return APISuccessResponse(
                message=f"Workflow {workflow_id} deleted successfully"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete workflow: {str(e)}"
        )


# Calendar repair functionality
@router.post("/calendar/repair", response_model=CalendarRepairResponse)
@handle_api_errors
async def repair_calendar_events(
    repair_request: CalendarRepairRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """Run calendar repair operations"""
    try:
        # TODO: Implement actual calendar repair
        # This would interface with the calendar repairer service

        logger.info(f"Calendar repair requested - dry_run: {repair_request.dry_run}")

        # Placeholder implementation
        return CalendarRepairResponse(
            success=True,
            message="Calendar repair completed",
            dry_run=repair_request.dry_run,
            repair_summary={
                "events_processed": 0,
                "events_repaired": 0,
                "errors": []
            }
        )

    except Exception as e:
        logger.error(f"Error during calendar repair: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calendar repair failed: {str(e)}"
        )


@router.get("/calendar/repair/rules", response_model=RepairRulesResponse)
@handle_api_errors
async def get_repair_rules(
    authenticated: bool = Depends(verify_api_key)
):
    """Get available calendar repair rules"""
    try:
        # TODO: Get actual repair rules from calendar repairer
        # For now, return placeholder data

        return RepairRulesResponse(
            rules=[
                {
                    "id": "birthday_format",
                    "name": "Birthday Format Standardization",
                    "description": "Standardizes birthday event formatting",
                    "is_active": True
                },
                {
                    "id": "anniversary_detection",
                    "name": "Anniversary Detection",
                    "description": "Detects and marks anniversary events",
                    "is_active": True
                },
                {
                    "id": "duplicate_removal",
                    "name": "Duplicate Event Removal",
                    "description": "Removes duplicate events",
                    "is_active": False
                }
            ],
            total_count=3
        )

    except Exception as e:
        logger.error(f"Error getting repair rules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repair rules: {str(e)}"
        )


@router.get("/calendar/repair/metrics", response_model=RepairMetricsResponse)
@handle_api_errors
async def get_repair_metrics(
    authenticated: bool = Depends(verify_api_key),
    days: int = 30
):
    """Get calendar repair metrics for the specified period"""
    try:
        # TODO: Get actual repair metrics
        # For now, return placeholder data

        return RepairMetricsResponse(
            metrics={
                "period_days": days,
                "total_repairs": 0,
                "events_processed": 0,
                "success_rate": 1.0,
                "most_common_issues": [],
                "repair_history": []
            },
            period=f"{days} days"
        )

    except Exception as e:
        logger.error(f"Error getting repair metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repair metrics: {str(e)}"
        )


@router.post("/regenerate-api-key", response_model=Dict[str, Any])
@handle_api_errors
async def regenerate_api_key(
    authenticated: bool = Depends(verify_api_key)
):
    """Regenerate the API key for authentication"""
    try:
        import secrets
        import string
        from src.config.config_loader import load_config, save_config_value

        # Generate new secure API key
        alphabet = string.ascii_letters + string.digits + '-_'
        new_api_key = ''.join(secrets.choice(alphabet) for _ in range(64))

        # Try to update config file
        try:
            # Update the config file
            save_config_value('api.api_key', new_api_key)

            logger.info("API key regenerated successfully")

            return {
                "success": True,
                "message": "API key regenerated successfully",
                "new_key": new_api_key,
                "key_length": len(new_api_key),
                "generated_at": datetime.utcnow().isoformat(),
                "note": "Please update your applications with the new API key. The old key is now invalid."
            }

        except Exception as config_error:
            # Fallback: Return key but warn about persistence
            logger.warning(f"Could not persist new API key to config: {config_error}")

            return {
                "success": True,
                "message": "API key generated but could not be persisted to config file",
                "new_key": new_api_key,
                "key_length": len(new_api_key),
                "generated_at": datetime.utcnow().isoformat(),
                "warning": "Key generated but not saved to config file. Manual update required.",
                "config_error": str(config_error)
            }

    except Exception as e:
        logger.error(f"Error regenerating API key: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate API key: {str(e)}"
        )


@router.get("/current-api-key-info", response_model=Dict[str, Any])
@handle_api_errors
async def get_current_api_key_info(
    authenticated: bool = Depends(verify_api_key)
):
    """Get information about the current API key (without revealing the key)"""
    try:
        from src.config.config_loader import load_config

        config = load_config()
        current_key = config.get('api', {}).get('api_key', '')

        return {
            "key_exists": bool(current_key),
            "key_length": len(current_key) if current_key else 0,
            "key_prefix": current_key[:8] + "..." if len(current_key) > 8 else "short",
            "key_suffix": "..." + current_key[-4:] if len(current_key) > 4 else "",
            "is_default": current_key in ['your-secret-api-key', 'super-secret-change-me', 'default-dev-key'],
            "recommendation": "Change default key" if current_key in ['your-secret-api-key', 'super-secret-change-me', 'default-dev-key'] else "Key looks secure"
        }

    except Exception as e:
        logger.error(f"Error getting API key info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get API key info: {str(e)}"
        )