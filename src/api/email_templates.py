"""
Email Templates API Router
Handles email template and category management for admin interface
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import and_, or_, func, select, update, delete
from sqlalchemy.orm import Session, selectinload

from src.core.database import db_service, get_db_session
from src.core.models import (
    EmailTemplateDB, EmailTemplateCategoryDB, SentEmailDB,
    EmailTemplate, EmailTemplateCategory
)
from src.api.schemas import (
    EmailTemplateCreate, EmailTemplateUpdate, EmailTemplateResponse,
    EmailTemplatesListResponse, EmailTemplateCategoryCreate,
    EmailTemplateCategoryUpdate, EmailTemplateCategoryResponse,
    EmailTemplateCategoriesListResponse, EmailTemplateStatsResponse
)
from src.api.dependencies import verify_api_key
from src.api.error_handling import handle_api_errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/email-templates", tags=["email-templates"])


@router.get("/stats", response_model=EmailTemplateStatsResponse)
async def get_email_template_stats(
    authenticated: bool = Depends(verify_api_key)
):
    """Get email template statistics for dashboard"""
    try:
        async with db_service.get_session() as session:
            # Count templates
            total_templates_result = await session.execute(
                select(func.count()).select_from(EmailTemplateDB)
            )
            total_templates = total_templates_result.scalar()

            # Count active templates
            active_templates_result = await session.execute(
                select(func.count()).select_from(EmailTemplateDB).where(
                    EmailTemplateDB.is_active == True
                )
            )
            active_templates = active_templates_result.scalar()

            # Count categories
            total_categories_result = await session.execute(
                select(func.count()).select_from(EmailTemplateCategoryDB)
            )
            total_categories = total_categories_result.scalar()

            # Count sent emails
            total_sent_result = await session.execute(
                select(func.count()).select_from(SentEmailDB)
            )
            total_sent = total_sent_result.scalar()

            # Calculate average rates
            avg_rates_result = await session.execute(
                select(
                    func.avg(EmailTemplateDB.open_rate),
                    func.avg(EmailTemplateDB.click_rate)
                ).select_from(EmailTemplateDB).where(
                    EmailTemplateDB.usage_count > 0
                )
            )
            avg_rates = avg_rates_result.first()
            avg_open_rate = avg_rates[0] if avg_rates[0] else 0.0
            avg_click_rate = avg_rates[1] if avg_rates[1] else 0.0

            return EmailTemplateStatsResponse(
                total_templates=total_templates,
                active_templates=active_templates,
                total_categories=total_categories,
                total_sent=total_sent,
                avg_open_rate=avg_open_rate,
                avg_click_rate=avg_click_rate
            )

    except Exception as e:
        logger.error(f"Error getting email template stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


# Categories endpoints
@router.get("/categories", response_model=EmailTemplateCategoriesListResponse)
async def list_categories(
    authenticated: bool = Depends(verify_api_key)
):
    """List all email template categories"""
    try:
        async with db_service.get_session() as session:
            # Get categories with template counts
            query = select(
                EmailTemplateCategoryDB,
                func.count(EmailTemplateDB.id).label('template_count')
            ).outerjoin(EmailTemplateDB).group_by(EmailTemplateCategoryDB.id)

            result = await session.execute(query)
            categories_data = result.all()

            categories = []
            for category_db, template_count in categories_data:
                categories.append(EmailTemplateCategoryResponse(
                    id=category_db.id,
                    name=category_db.name,
                    description=category_db.description,
                    icon=category_db.icon,
                    template_count=template_count,
                    created_at=category_db.created_at,
                    updated_at=category_db.updated_at
                ))

            return EmailTemplateCategoriesListResponse(
                total=len(categories),
                categories=categories
            )

    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list categories: {str(e)}"
        )


@router.post("/categories", response_model=EmailTemplateCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: EmailTemplateCategoryCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new email template category"""
    try:
        async with db_service.get_session() as session:
            # Check if category with same name exists
            existing = await session.execute(
                select(EmailTemplateCategoryDB).where(
                    EmailTemplateCategoryDB.name == category_data.name
                )
            )
            if existing.scalar():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category '{category_data.name}' already exists"
                )

            # Create category
            category = EmailTemplateCategory(
                name=category_data.name,
                description=category_data.description,
                icon=category_data.icon
            )

            db_category = category.to_db_model()
            session.add(db_category)
            await session.commit()
            await session.refresh(db_category)

            return EmailTemplateCategoryResponse(
                id=db_category.id,
                name=db_category.name,
                description=db_category.description,
                icon=db_category.icon,
                template_count=0,
                created_at=db_category.created_at,
                updated_at=db_category.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating category: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create category: {str(e)}"
        )


# Templates endpoints
@router.get("/", response_model=EmailTemplatesListResponse)
async def list_templates(
    authenticated: bool = Depends(verify_api_key),
    q: Optional[str] = Query(None, description="Search query"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page")
):
    """List email templates with filtering and pagination"""
    try:
        async with db_service.get_session() as session:
            # Build query with joins
            query = select(EmailTemplateDB).outerjoin(EmailTemplateCategoryDB)

            # Apply filters
            if q:
                query = query.where(
                    or_(
                        EmailTemplateDB.name.ilike(f"%{q}%"),
                        EmailTemplateDB.description.ilike(f"%{q}%"),
                        EmailTemplateDB.subject.ilike(f"%{q}%")
                    )
                )

            if category_id is not None:
                query = query.where(EmailTemplateDB.category_id == category_id)

            if is_active is not None:
                query = query.where(EmailTemplateDB.is_active == is_active)

            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            query = query.order_by(EmailTemplateDB.updated_at.desc())

            # Execute query
            result = await session.execute(query)
            db_templates = result.scalars().all()

            # Get category info for each template
            templates = []
            for db_template in db_templates:
                category_name = None
                category_icon = None
                if db_template.category_id:
                    category = await session.get(EmailTemplateCategoryDB, db_template.category_id)
                    if category:
                        category_name = category.name
                        category_icon = category.icon

                templates.append(EmailTemplateResponse(
                    id=db_template.id,
                    name=db_template.name,
                    description=db_template.description,
                    subject=db_template.subject,
                    html_content=db_template.html_content,
                    text_content=db_template.text_content,
                    category_id=db_template.category_id,
                    category_name=category_name,
                    category_icon=category_icon,
                    is_active=db_template.is_active,
                    usage_count=db_template.usage_count,
                    open_rate=db_template.open_rate,
                    click_rate=db_template.click_rate,
                    variables=db_template.variables,
                    created_at=db_template.created_at,
                    updated_at=db_template.updated_at
                ))

            return EmailTemplatesListResponse(
                total=total,
                page=page,
                page_size=page_size,
                templates=templates
            )

    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}"
        )


@router.post("/", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: EmailTemplateCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create a new email template"""
    try:
        async with db_service.get_session() as session:
            # Verify category exists if provided
            if template_data.category_id:
                category = await session.get(EmailTemplateCategoryDB, template_data.category_id)
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Category {template_data.category_id} not found"
                    )

            # Create template
            template = EmailTemplate(
                name=template_data.name,
                description=template_data.description,
                subject=template_data.subject,
                html_content=template_data.html_content,
                text_content=template_data.text_content,
                category_id=template_data.category_id,
                is_active=template_data.is_active,
                variables=template_data.variables
            )

            db_template = template.to_db_model()
            session.add(db_template)
            await session.commit()
            await session.refresh(db_template)

            # Get category info
            category_name = None
            category_icon = None
            if db_template.category_id:
                category = await session.get(EmailTemplateCategoryDB, db_template.category_id)
                if category:
                    category_name = category.name
                    category_icon = category.icon

            return EmailTemplateResponse(
                id=db_template.id,
                name=db_template.name,
                description=db_template.description,
                subject=db_template.subject,
                html_content=db_template.html_content,
                text_content=db_template.text_content,
                category_id=db_template.category_id,
                category_name=category_name,
                category_icon=category_icon,
                is_active=db_template.is_active,
                usage_count=db_template.usage_count,
                open_rate=db_template.open_rate,
                click_rate=db_template.click_rate,
                variables=db_template.variables,
                created_at=db_template.created_at,
                updated_at=db_template.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_template(
    template_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Get a specific email template"""
    try:
        async with db_service.get_session() as session:
            db_template = await session.get(EmailTemplateDB, template_id)
            if not db_template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            # Get category info
            category_name = None
            category_icon = None
            if db_template.category_id:
                category = await session.get(EmailTemplateCategoryDB, db_template.category_id)
                if category:
                    category_name = category.name
                    category_icon = category.icon

            return EmailTemplateResponse(
                id=db_template.id,
                name=db_template.name,
                description=db_template.description,
                subject=db_template.subject,
                html_content=db_template.html_content,
                text_content=db_template.text_content,
                category_id=db_template.category_id,
                category_name=category_name,
                category_icon=category_icon,
                is_active=db_template.is_active,
                usage_count=db_template.usage_count,
                open_rate=db_template.open_rate,
                click_rate=db_template.click_rate,
                variables=db_template.variables,
                created_at=db_template.created_at,
                updated_at=db_template.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template: {str(e)}"
        )


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: int,
    template_data: EmailTemplateUpdate,
    authenticated: bool = Depends(verify_api_key)
):
    """Update an email template"""
    try:
        async with db_service.get_session() as session:
            db_template = await session.get(EmailTemplateDB, template_id)
            if not db_template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            # Update fields
            if template_data.name is not None:
                db_template.name = template_data.name
            if template_data.description is not None:
                db_template.description = template_data.description
            if template_data.subject is not None:
                db_template.subject = template_data.subject
            if template_data.html_content is not None:
                db_template.html_content = template_data.html_content
            if template_data.text_content is not None:
                db_template.text_content = template_data.text_content
            if template_data.category_id is not None:
                # Verify category exists
                if template_data.category_id:
                    category = await session.get(EmailTemplateCategoryDB, template_data.category_id)
                    if not category:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Category {template_data.category_id} not found"
                        )
                db_template.category_id = template_data.category_id
            if template_data.is_active is not None:
                db_template.is_active = template_data.is_active
            if template_data.variables is not None:
                db_template.variables = template_data.variables

            db_template.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(db_template)

            # Get category info
            category_name = None
            category_icon = None
            if db_template.category_id:
                category = await session.get(EmailTemplateCategoryDB, db_template.category_id)
                if category:
                    category_name = category.name
                    category_icon = category.icon

            return EmailTemplateResponse(
                id=db_template.id,
                name=db_template.name,
                description=db_template.description,
                subject=db_template.subject,
                html_content=db_template.html_content,
                text_content=db_template.text_content,
                category_id=db_template.category_id,
                category_name=category_name,
                category_icon=category_icon,
                is_active=db_template.is_active,
                usage_count=db_template.usage_count,
                open_rate=db_template.open_rate,
                click_rate=db_template.click_rate,
                variables=db_template.variables,
                created_at=db_template.created_at,
                updated_at=db_template.updated_at
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update template: {str(e)}"
        )


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete an email template"""
    try:
        async with db_service.get_session() as session:
            db_template = await session.get(EmailTemplateDB, template_id)
            if not db_template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            await session.delete(db_template)
            await session.commit()

            return {"success": True, "message": f"Template {template_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete template: {str(e)}"
        )


@router.post("/{template_id}/toggle")
async def toggle_template(
    template_id: int,
    authenticated: bool = Depends(verify_api_key)
):
    """Toggle template active status"""
    try:
        async with db_service.get_session() as session:
            db_template = await session.get(EmailTemplateDB, template_id)
            if not db_template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template {template_id} not found"
                )

            db_template.is_active = not db_template.is_active
            db_template.updated_at = datetime.utcnow()
            await session.commit()

            status_text = "aktiviert" if db_template.is_active else "deaktiviert"
            return {"success": True, "message": f"Template {template_id} {status_text}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling template {template_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle template: {str(e)}"
        )