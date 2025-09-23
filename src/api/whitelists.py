"""
Whitelists API Router
Handles whitelist management and validation for admin interface
"""

import logging
from datetime import datetime
from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import and_, or_, func, select, update, delete
from sqlalchemy.orm import Session, selectinload

from src.core.database import db_service, get_db_session
from src.core.models import (
    WhitelistDB, WhitelistAccessLogDB,
    Whitelist, WhitelistAccessLog
)
from src.api.schemas import (
    WhitelistCreate, WhitelistUpdate, WhitelistResponse,
    WhitelistsListResponse, WhitelistCheckRequest, WhitelistCheckResponse,
    WhitelistAccessLogResponse, WhitelistStatsResponse
)
from src.api.dependencies import verify_api_key
from src.api.error_handling import handle_api_errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/whitelists", tags=["whitelists"])


@router.get("/stats", response_model=WhitelistStatsResponse)
async def get_whitelist_stats(
    authenticated: bool = Depends(verify_api_key)
):
    """Get whitelist statistics for dashboard"""
    try:
        async with db_service.get_session() as session:
            # Count whitelists
            total_result = await session.execute(
                select(func.count()).select_from(WhitelistDB)
            )
            total_whitelists = total_result.scalar()

            # Count active whitelists
            active_result = await session.execute(
                select(func.count()).select_from(WhitelistDB).where(
                    WhitelistDB.enabled == True
                )
            )
            active_whitelists = active_result.scalar()

            # Count total checks
            total_checks_result = await session.execute(
                select(func.count()).select_from(WhitelistAccessLogDB)
            )
            total_checks = total_checks_result.scalar()

            # Count allowed/denied checks
            allowed_result = await session.execute(
                select(func.count()).select_from(WhitelistAccessLogDB).where(
                    WhitelistAccessLogDB.result == 'allowed'
                )
            )
            allowed_checks = allowed_result.scalar()

            denied_checks = total_checks - allowed_checks
            success_rate = (allowed_checks / total_checks * 100) if total_checks > 0 else 0.0

            return WhitelistStatsResponse(
                total_whitelists=total_whitelists,
                active_whitelists=active_whitelists,
                total_checks=total_checks,
                allowed_checks=allowed_checks,
                denied_checks=denied_checks,
                success_rate=success_rate
            )

    except Exception as e:
        logger.error(f"Error getting whitelist stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get("/", response_model=WhitelistsListResponse)
async def list_whitelists(
    authenticated: bool = Depends(verify_api_key),
    q: Optional[str] = Query(None, description="Search query"),
    type: Optional[str] = Query(None, description="Filter by type"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page")
):
    """List whitelists with filtering and pagination"""
    try:
        async with db_service.get_session() as session:
            # Build query
            query = select(WhitelistDB)

            # Apply filters
            if q:
                query = query.where(
                    or_(
                        WhitelistDB.name.ilike(f"%{q}%"),
                        WhitelistDB.description.ilike(f"%{q}%")
                    )
                )

            if type:
                query = query.where(WhitelistDB.type == type)

            if enabled is not None:
                query = query.where(WhitelistDB.enabled == enabled)

            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            query = query.order_by(WhitelistDB.updated_at.desc())

            # Execute query
            result = await session.execute(query)
            db_whitelists = result.scalars().all()

            # Convert to response models
            whitelists = []
            for db_whitelist in db_whitelists:
                whitelists.append(WhitelistResponse(
                    id=db_whitelist.id,
                    name=db_whitelist.name,
                    description=db_whitelist.description,
                    type=db_whitelist.type,
                    entries=db_whitelist.entries or [],
                    enabled=db_whitelist.enabled,
                    usage_count=db_whitelist.usage_count,
                    last_used=db_whitelist.last_used,
                    created_at=db_whitelist.created_at,
                    updated_at=db_whitelist.updated_at
                ))

            return WhitelistsListResponse(
                total=total,
                page=page,
                page_size=page_size,
                whitelists=whitelists
            )

    except Exception as e:
        logger.error(f"Error listing whitelists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list whitelists: {str(e)}"
        )


@router.post("/", response_model=WhitelistResponse, status_code=status.HTTP_201_CREATED)
async def create_whitelist(
    whitelist_data: WhitelistCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new whitelist"""
    try:
        async with db_service.get_session() as session:
            # Check if whitelist with same name exists
            existing = await session.execute(
                select(WhitelistDB).where(WhitelistDB.name == whitelist_data.name)
            )
            if existing.scalar():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Whitelist '{whitelist_data.name}' already exists"
                )

            # Create whitelist
            whitelist = Whitelist(
                name=whitelist_data.name,
                description=whitelist_data.description,
                type=whitelist_data.type.value,
                entries=whitelist_data.entries,
                enabled=whitelist_data.enabled
            )

            db_whitelist = whitelist.to_db_model()
            session.add(db_whitelist)
            await session.commit()
            await session.refresh(db_whitelist)

            return WhitelistResponse(
                id=db_whitelist.id,
                name=db_whitelist.name,
                description=db_whitelist.description,
                type=db_whitelist.type,
                entries=db_whitelist.entries or [],
                enabled=db_whitelist.enabled,
                usage_count=db_whitelist.usage_count,
                last_used=db_whitelist.last_used,
                created_at=db_whitelist.created_at,
                updated_at=db_whitelist.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating whitelist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create whitelist: {str(e)}"
        )


@router.get("/{whitelist_id}", response_model=WhitelistResponse)
async def get_whitelist(
    whitelist_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Get a specific whitelist by ID"""
    try:
        async with db_service.get_session() as session:
            db_whitelist = await session.get(WhitelistDB, whitelist_id)
            if not db_whitelist:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Whitelist {whitelist_id} not found"
                )

            return WhitelistResponse(
                id=db_whitelist.id,
                name=db_whitelist.name,
                description=db_whitelist.description,
                type=db_whitelist.type,
                entries=db_whitelist.entries or [],
                enabled=db_whitelist.enabled,
                usage_count=db_whitelist.usage_count,
                last_used=db_whitelist.last_used,
                created_at=db_whitelist.created_at,
                updated_at=db_whitelist.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting whitelist {whitelist_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get whitelist: {str(e)}"
        )


@router.put("/{whitelist_id}", response_model=WhitelistResponse)
async def update_whitelist(
    whitelist_id: int,
    whitelist_data: WhitelistUpdate,
    authenticated: bool = Depends(verify_api_key)
):
    """Update an existing whitelist"""
    try:
        async with db_service.get_session() as session:
            db_whitelist = await session.get(WhitelistDB, whitelist_id)
            if not db_whitelist:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Whitelist {whitelist_id} not found"
                )

            # Check name uniqueness if name is being changed
            if (whitelist_data.name and
                whitelist_data.name != db_whitelist.name):
                existing = await session.execute(
                    select(WhitelistDB).where(
                        and_(
                            WhitelistDB.name == whitelist_data.name,
                            WhitelistDB.id != whitelist_id
                        )
                    )
                )
                if existing.scalar():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Whitelist '{whitelist_data.name}' already exists"
                    )

            # Update fields
            if whitelist_data.name is not None:
                db_whitelist.name = whitelist_data.name
            if whitelist_data.description is not None:
                db_whitelist.description = whitelist_data.description
            if whitelist_data.type is not None:
                db_whitelist.type = whitelist_data.type.value
            if whitelist_data.entries is not None:
                db_whitelist.entries = whitelist_data.entries
            if whitelist_data.enabled is not None:
                db_whitelist.enabled = whitelist_data.enabled

            db_whitelist.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(db_whitelist)

            return WhitelistResponse(
                id=db_whitelist.id,
                name=db_whitelist.name,
                description=db_whitelist.description,
                type=db_whitelist.type,
                entries=db_whitelist.entries or [],
                enabled=db_whitelist.enabled,
                usage_count=db_whitelist.usage_count,
                last_used=db_whitelist.last_used,
                created_at=db_whitelist.created_at,
                updated_at=db_whitelist.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating whitelist {whitelist_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update whitelist: {str(e)}"
        )


@router.delete("/{whitelist_id}")
async def delete_whitelist(
    whitelist_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete a whitelist"""
    try:
        async with db_service.get_session() as session:
            db_whitelist = await session.get(WhitelistDB, whitelist_id)
            if not db_whitelist:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Whitelist {whitelist_id} not found"
                )

            await session.delete(db_whitelist)
            await session.commit()

            return {"success": True, "message": f"Whitelist {whitelist_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting whitelist {whitelist_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete whitelist: {str(e)}"
        )


@router.post("/{whitelist_id}/toggle")
async def toggle_whitelist(
    whitelist_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Toggle whitelist enabled status"""
    try:
        async with db_service.get_session() as session:
            db_whitelist = await session.get(WhitelistDB, whitelist_id)
            if not db_whitelist:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Whitelist {whitelist_id} not found"
                )

            db_whitelist.enabled = not db_whitelist.enabled
            db_whitelist.updated_at = datetime.utcnow()
            await session.commit()

            status_text = "aktiviert" if db_whitelist.enabled else "deaktiviert"
            return {"success": True, "message": f"Whitelist {whitelist_id} {status_text}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling whitelist {whitelist_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle whitelist: {str(e)}"
        )


@router.post("/check", response_model=WhitelistCheckResponse)
async def check_whitelist(
    request: WhitelistCheckRequest,
    client_request: Request,
    authenticated: bool = Depends(verify_api_key)
):
    """Check if a value is allowed by a whitelist"""
    try:
        async with db_service.get_session() as session:
            # Find whitelist
            db_whitelist = None
            if request.whitelist_id:
                db_whitelist = await session.get(WhitelistDB, request.whitelist_id)
            elif request.whitelist_name:
                result = await session.execute(
                    select(WhitelistDB).where(WhitelistDB.name == request.whitelist_name)
                )
                db_whitelist = result.scalar()

            if not db_whitelist:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Whitelist not found"
                )

            # Convert to domain model and check
            whitelist = Whitelist(
                id=db_whitelist.id,
                name=db_whitelist.name,
                type=db_whitelist.type,
                entries=db_whitelist.entries or [],
                enabled=db_whitelist.enabled
            )

            allowed = whitelist.is_allowed(request.value)
            result = "allowed" if allowed else "denied"

            # Log the access
            source_ip = request.source_ip or client_request.client.host
            user_agent = request.user_agent or client_request.headers.get("user-agent")

            access_log = WhitelistAccessLog(
                whitelist_id=db_whitelist.id,
                requested_value=request.value,
                result=result,
                source_ip=source_ip,
                user_agent=user_agent,
                additional_data=request.additional_data
            )

            db_log = access_log.to_db_model()
            session.add(db_log)

            # Update whitelist usage stats
            db_whitelist.usage_count += 1
            db_whitelist.last_used = datetime.utcnow()

            await session.commit()

            return WhitelistCheckResponse(
                allowed=allowed,
                whitelist_id=db_whitelist.id,
                whitelist_name=db_whitelist.name,
                requested_value=request.value,
                result=result,
                message=f"Access {result} for value '{request.value}'"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking whitelist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check whitelist: {str(e)}"
        )


@router.get("/{whitelist_id}/logs", response_model=List[WhitelistAccessLogResponse])
async def get_whitelist_logs(
    whitelist_id: int,
    authenticated: bool = Depends(verify_api_key),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return")
):
    """Get access logs for a whitelist"""
    try:
        async with db_service.get_session() as session:
            # Verify whitelist exists
            db_whitelist = await session.get(WhitelistDB, whitelist_id)
            if not db_whitelist:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Whitelist {whitelist_id} not found"
                )

            # Get logs
            query = select(WhitelistAccessLogDB).where(
                WhitelistAccessLogDB.whitelist_id == whitelist_id
            ).order_by(WhitelistAccessLogDB.accessed_at.desc()).limit(limit)

            result = await session.execute(query)
            db_logs = result.scalars().all()

            logs = []
            for db_log in db_logs:
                logs.append(WhitelistAccessLogResponse(
                    id=db_log.id,
                    whitelist_id=db_log.whitelist_id,
                    requested_value=db_log.requested_value,
                    result=db_log.result,
                    source_ip=db_log.source_ip,
                    user_agent=db_log.user_agent,
                    additional_data=db_log.additional_data,
                    accessed_at=db_log.accessed_at
                ))

            return logs

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting whitelist logs for {whitelist_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get whitelist logs: {str(e)}"
        )