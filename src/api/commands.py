"""
Commands API Router
Handles command queue operations for external system integration
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy import select, update
from pydantic import BaseModel

from src.core.database import db_service
from src.core.models import ExternalCommandDB, CommandStatus
from src.api.dependencies import verify_api_key
from src.api.error_handling import handle_api_errors
from src.api.standard_schemas import (
    CommandListResponse, CommandOperationResponse, CommandStatusResponse
)
from src.api.deprecation import deprecate_parameter, DeprecationLevel

router = APIRouter()
logger = logging.getLogger(__name__)


# Command-specific schemas - Local override of standard schema
class CommandResponseLocal(BaseModel):
    id: str
    system_id: str
    command_type: str
    payload: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class CommandCompletionRequest(BaseModel):
    result: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class CommandFailureRequest(BaseModel):
    error_message: str
    error_code: Optional[str] = None
    retry: bool = False
    metadata: Optional[Dict[str, Any]] = None


@router.get("/{system_id}", response_model=Dict[str, Any])
@deprecate_parameter(
    "limit",
    level=DeprecationLevel.WARNING,
    message="Parameter 'limit' is deprecated. Use page-based pagination instead.",
    alternative="Use page and page_size parameters",
    removal_date="2024-06-01"
)
async def get_pending_commands(
    system_id: str,
    authenticated: bool = Depends(verify_api_key),
    limit: int = 10
):
    """Poll commands for a target system and reset stale PROCESSING items"""
    try:
        async with db_service.get_session() as session:
            # First, reset stale PROCESSING commands (older than 10 minutes)
            stale_threshold = datetime.utcnow() - timedelta(minutes=10)

            stale_update = (
                update(ExternalCommandDB)
                .where(
                    (ExternalCommandDB.system_id == system_id) &
                    (ExternalCommandDB.status == CommandStatus.PROCESSING) &
                    (ExternalCommandDB.updated_at < stale_threshold)
                )
                .values(
                    status=CommandStatus.PENDING,
                    updated_at=datetime.utcnow()
                )
            )
            await session.execute(stale_update)

            # Get pending commands for the system
            query = (
                select(ExternalCommandDB)
                .where(
                    (ExternalCommandDB.system_id == system_id) &
                    (ExternalCommandDB.status == CommandStatus.PENDING)
                )
                .order_by(ExternalCommandDB.created_at)
                .limit(limit)
            )

            result = await session.execute(query)
            commands_db = result.scalars().all()

            # Mark retrieved commands as PROCESSING
            if commands_db:
                command_ids = [cmd.id for cmd in commands_db]

                processing_update = (
                    update(ExternalCommandDB)
                    .where(ExternalCommandDB.id.in_(command_ids))
                    .values(
                        status=CommandStatus.PROCESSING,
                        updated_at=datetime.utcnow()
                    )
                )
                await session.execute(processing_update)
                await session.commit()

            # Convert to response format
            commands = [
                CommandResponseLocal(
                    id=cmd.id,
                    system_id=cmd.system_id,
                    command_type=cmd.command_type,
                    payload=cmd.payload,
                    status=CommandStatus.PROCESSING.value,  # They're now processing
                    created_at=cmd.created_at,
                    updated_at=datetime.utcnow()
                )
                for cmd in commands_db
            ]

            return {
                "commands": commands,
                "count": len(commands),
                "system_id": system_id,
                "retrieved_at": datetime.utcnow()
            }

    except Exception as e:
        logger.error(f"Error retrieving commands for system {system_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve commands: {str(e)}"
        )


@router.post("/{command_id}/complete", response_model=CommandOperationResponse)
async def complete_command(
    command_id: str,
    completion_data: CommandCompletionRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """Mark a command as completed"""
    try:
        async with db_service.get_session() as session:
            # Find the command
            query = select(ExternalCommandDB).where(ExternalCommandDB.id == command_id)
            result = await session.execute(query)
            command_db = result.scalar_one_or_none()

            if not command_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Command {command_id} not found"
                )

            # Verify command is in PROCESSING state
            if command_db.status != CommandStatus.PROCESSING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Command {command_id} is not in PROCESSING state (current: {command_db.status.value})"
                )

            # Update command status
            command_db.status = CommandStatus.COMPLETED
            command_db.updated_at = datetime.utcnow()
            command_db.completed_at = datetime.utcnow()

            # Store completion result if provided
            if completion_data.result:
                if not command_db.metadata:
                    command_db.metadata = {}
                command_db.metadata["completion_result"] = completion_data.result

            # Store additional metadata if provided
            if completion_data.metadata:
                if not command_db.metadata:
                    command_db.metadata = {}
                command_db.metadata.update(completion_data.metadata)

            await session.commit()

            logger.info(f"Command {command_id} marked as completed")

            return CommandOperationResponse(
                success=True,
                message=f"Command {command_id} completed successfully",
                command_id=command_id,
                new_status="COMPLETED"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing command {command_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete command: {str(e)}"
        )


@router.post("/{command_id}/fail", response_model=CommandOperationResponse)
async def fail_command(
    command_id: str,
    failure_data: CommandFailureRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """Report command failure with error details"""
    try:
        async with db_service.get_session() as session:
            # Find the command
            query = select(ExternalCommandDB).where(ExternalCommandDB.id == command_id)
            result = await session.execute(query)
            command_db = result.scalar_one_or_none()

            if not command_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Command {command_id} not found"
                )

            # Verify command is in PROCESSING state
            if command_db.status != CommandStatus.PROCESSING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Command {command_id} is not in PROCESSING state (current: {command_db.status.value})"
                )

            # Determine new status based on retry flag
            if failure_data.retry:
                command_db.status = CommandStatus.PENDING
                logger.info(f"Command {command_id} failed but will be retried")
            else:
                command_db.status = CommandStatus.FAILED
                logger.warning(f"Command {command_id} failed permanently")

            command_db.updated_at = datetime.utcnow()

            # Store error information
            if not command_db.metadata:
                command_db.metadata = {}

            command_db.metadata["error"] = {
                "message": failure_data.error_message,
                "code": failure_data.error_code,
                "timestamp": datetime.utcnow().isoformat(),
                "retry_requested": failure_data.retry
            }

            # Store additional metadata if provided
            if failure_data.metadata:
                command_db.metadata.update(failure_data.metadata)

            # Increment retry count if retrying
            if failure_data.retry:
                if "retry_count" not in command_db.metadata:
                    command_db.metadata["retry_count"] = 0
                command_db.metadata["retry_count"] += 1

            await session.commit()

            return CommandOperationResponse(
                success=True,
                message=f"Command {command_id} failure recorded",
                command_id=command_id,
                new_status=command_db.status.value
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error failing command {command_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record command failure: {str(e)}"
        )


@router.get("/{system_id}/status", response_model=Dict[str, Any])
async def get_command_status(
    system_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Get command queue status for a specific system"""
    try:
        async with db_service.get_session() as session:
            # Count commands by status
            from sqlalchemy import func

            query = (
                select(
                    ExternalCommandDB.status,
                    func.count(ExternalCommandDB.id).label('count')
                )
                .where(ExternalCommandDB.system_id == system_id)
                .group_by(ExternalCommandDB.status)
            )

            result = await session.execute(query)
            status_counts = {row.status.value: row.count for row in result}

            # Get oldest pending command timestamp
            oldest_pending_query = (
                select(func.min(ExternalCommandDB.created_at))
                .where(
                    (ExternalCommandDB.system_id == system_id) &
                    (ExternalCommandDB.status == CommandStatus.PENDING)
                )
            )
            oldest_pending_result = await session.execute(oldest_pending_query)
            oldest_pending = oldest_pending_result.scalar()

            return {
                "system_id": system_id,
                "status_counts": status_counts,
                "oldest_pending": oldest_pending,
                "total_commands": sum(status_counts.values()),
                "checked_at": datetime.utcnow()
            }

    except Exception as e:
        logger.error(f"Error getting command status for system {system_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get command status: {str(e)}"
        )


@router.delete("/{command_id}", response_model=CommandOperationResponse)
async def delete_command(
    command_id: str,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete a command from the queue (admin operation)"""
    try:
        async with db_service.get_session() as session:
            # Find the command
            query = select(ExternalCommandDB).where(ExternalCommandDB.id == command_id)
            result = await session.execute(query)
            command_db = result.scalar_one_or_none()

            if not command_db:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Command {command_id} not found"
                )

            # Delete the command
            await session.delete(command_db)
            await session.commit()

            logger.info(f"Command {command_id} deleted by admin")

            return CommandOperationResponse(
                success=True,
                message=f"Command {command_id} deleted successfully",
                command_id=command_id
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting command {command_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete command: {str(e)}"
        )