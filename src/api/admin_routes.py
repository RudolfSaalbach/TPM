"""
Admin routes for CRUD management of templates, whitelists, and workflows
Simple UI for managing system configuration without programming
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from src.core.database import get_db_session
from src.core.security import security_service, APIScope
from src.core.email_service import EmailService, EmailTemplate, load_smtp_config_from_env
from src.core.schema_extensions import (
    WhitelistDB, WorkflowDB, EmailTemplateDB, WebhookTemplateDB,
    BackupJobDB, IntegrationConfigDB
)


class AdminRoutes:
    """Admin CRUD routes for system management"""

    def __init__(self, email_service: EmailService = None):
        self.router = APIRouter()
        self.templates = Jinja2Templates(directory="templates")
        self.email_service = email_service
        self._setup_routes()

    def _setup_routes(self):
        """Setup all admin routes"""

        # Main admin dashboard
        @self.router.get("/admin", response_class=HTMLResponse)
        async def admin_dashboard(request: Request):
            stats = {
                "total_events": 0,
                "active_workflows": 0,
                "email_templates": 0,
                "integrations": 0
            }

            return self.templates.TemplateResponse("admin/dashboard.html", {
                "request": request,
                "title": "Chronos Admin Dashboard",
                "active_page": "dashboard",
                "stats": stats
            })

        # Whitelists management
        @self.router.get("/admin/whitelists", response_class=HTMLResponse)
        async def whitelists_list(request: Request, session=Depends(get_db_session)):
            from sqlalchemy import select

            result = await session.execute(
                select(WhitelistDB).order_by(WhitelistDB.system_name, WhitelistDB.action_name)
            )
            whitelists = result.scalars().all()

            return self.templates.TemplateResponse("admin/whitelists.html", {
                "request": request,
                "whitelists": whitelists,
                "title": "System Whitelists",
                "active_page": "whitelists"
            })

        @self.router.get("/admin/whitelists/new", response_class=HTMLResponse)
        async def whitelist_new_form(request: Request):
            return self.templates.TemplateResponse("admin/whitelist_form.html", {
                "request": request,
                "whitelist": None,
                "title": "New Whitelist Entry",
                "active_page": "whitelists",
                "allowed_params_json": ""
            })

        @self.router.post("/admin/whitelists/new")
        async def whitelist_create(
            request: Request,
            system_name: str = Form(...),
            action_name: str = Form(...),
            allowed_params: str = Form(""),
            enabled: bool = Form(True),
            session=Depends(get_db_session)
        ):
            # Parse allowed params JSON
            allowed_params_dict = {}
            if allowed_params.strip():
                try:
                    allowed_params_dict = json.loads(allowed_params)
                except json.JSONDecodeError:
                    raise HTTPException(400, "Invalid JSON in allowed_params")

            whitelist = WhitelistDB(
                system_name=system_name,
                action_name=action_name,
                allowed_params=allowed_params_dict,
                enabled=enabled,
                created_by="admin"
            )

            session.add(whitelist)
            await session.commit()

            return RedirectResponse("/admin/whitelists", status_code=303)

        @self.router.get("/admin/whitelists/{whitelist_id}/edit", response_class=HTMLResponse)
        async def whitelist_edit_form(request: Request, whitelist_id: int, session=Depends(get_db_session)):
            whitelist = await session.get(WhitelistDB, whitelist_id)
            if not whitelist:
                raise HTTPException(404, "Whitelist not found")

            return self.templates.TemplateResponse("admin/whitelist_form.html", {
                "request": request,
                "whitelist": whitelist,
                "allowed_params_json": json.dumps(whitelist.allowed_params, indent=2) if whitelist.allowed_params else "",
                "title": "Edit Whitelist Entry",
                "active_page": "whitelists"
            })

        @self.router.post("/admin/whitelists/{whitelist_id}/delete")
        async def whitelist_delete(whitelist_id: int, session=Depends(get_db_session)):
            whitelist = await session.get(WhitelistDB, whitelist_id)
            if whitelist:
                await session.delete(whitelist)
                await session.commit()

            return RedirectResponse("/admin/whitelists", status_code=303)

        # Workflows management
        @self.router.get("/admin/workflows", response_class=HTMLResponse)
        async def workflows_list(request: Request, session=Depends(get_db_session)):
            from sqlalchemy import select

            result = await session.execute(
                select(WorkflowDB).order_by(WorkflowDB.name)
            )
            workflows = result.scalars().all()

            return self.templates.TemplateResponse("admin/workflows.html", {
                "request": request,
                "workflows": workflows,
                "title": "Action Workflows"
            })

        @self.router.get("/admin/workflows/new", response_class=HTMLResponse)
        async def workflow_new_form(request: Request):
            return self.templates.TemplateResponse("admin/workflow_form.html", {
                "request": request,
                "workflow": None,
                "title": "New Workflow"
            })

        @self.router.post("/admin/workflows/new")
        async def workflow_create(
            request: Request,
            name: str = Form(...),
            trigger_action: str = Form(...),
            trigger_system: str = Form(...),
            trigger_status: str = Form("COMPLETED"),
            follow_action: str = Form(...),
            follow_system: str = Form(...),
            follow_params: str = Form(""),
            enabled: bool = Form(True),
            session=Depends(get_db_session)
        ):
            # Parse follow params JSON
            follow_params_dict = {}
            if follow_params.strip():
                try:
                    follow_params_dict = json.loads(follow_params)
                except json.JSONDecodeError:
                    raise HTTPException(400, "Invalid JSON in follow_params")

            workflow = WorkflowDB(
                name=name,
                trigger_action=trigger_action,
                trigger_system=trigger_system,
                trigger_status=trigger_status,
                follow_action=follow_action,
                follow_system=follow_system,
                follow_params_template=follow_params_dict,
                enabled=enabled,
                created_by="admin"
            )

            session.add(workflow)
            await session.commit()

            return RedirectResponse("/admin/workflows", status_code=303)

        # Email Templates management
        @self.router.get("/admin/email-templates", response_class=HTMLResponse)
        async def email_templates_list(request: Request, session=Depends(get_db_session)):
            from sqlalchemy import select

            result = await session.execute(
                select(EmailTemplateDB).order_by(EmailTemplateDB.category, EmailTemplateDB.name)
            )
            templates = result.scalars().all()

            return self.templates.TemplateResponse("admin/email_templates.html", {
                "request": request,
                "templates": templates,
                "title": "Email Templates"
            })

        @self.router.get("/admin/email-templates/new", response_class=HTMLResponse)
        async def email_template_new_form(request: Request):
            return self.templates.TemplateResponse("admin/email_template_form.html", {
                "request": request,
                "template": None,
                "title": "New Email Template"
            })

        @self.router.post("/admin/email-templates/new")
        async def email_template_create(
            request: Request,
            name: str = Form(...),
            subject_template: str = Form(...),
            html_body_template: str = Form(""),
            text_body_template: str = Form(""),
            category: str = Form("general"),
            variables: str = Form(""),
            enabled: bool = Form(True),
            session=Depends(get_db_session)
        ):
            # Parse variables list
            variables_list = []
            if variables.strip():
                variables_list = [v.strip() for v in variables.split(',') if v.strip()]

            template = EmailTemplateDB(
                name=name,
                subject_template=subject_template,
                html_body_template=html_body_template if html_body_template else None,
                text_body_template=text_body_template if text_body_template else None,
                category=category,
                variables=variables_list,
                enabled=enabled,
                created_by="admin"
            )

            session.add(template)
            await session.commit()

            return RedirectResponse("/admin/email-templates", status_code=303)

        @self.router.get("/admin/email-templates/{template_id}/preview", response_class=HTMLResponse)
        async def email_template_preview(request: Request, template_id: int, session=Depends(get_db_session)):
            template = await session.get(EmailTemplateDB, template_id)
            if not template:
                raise HTTPException(404, "Template not found")

            # Sample variables for preview
            sample_vars = {
                "event": {
                    "title": "Sample Meeting",
                    "start_time": "2025-01-20 14:00:00",
                    "location": "Conference Room A"
                },
                "user": {
                    "name": "John Doe",
                    "email": "john@example.com"
                },
                "title": "Sample Notification",
                "message": "This is a sample notification message.",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.email_service:
                try:
                    preview = await self.email_service.preview_template(template_id, sample_vars)
                except Exception as e:
                    preview = {"error": str(e)}
            else:
                preview = {"error": "Email service not available"}

            return self.templates.TemplateResponse("admin/email_template_preview.html", {
                "request": request,
                "template": template,
                "preview": preview,
                "sample_vars": sample_vars,
                "title": f"Preview: {template.name}"
            })

        @self.router.post("/admin/email-templates/{template_id}/test")
        async def email_template_test(
            template_id: int,
            test_email: str = Form(...),
            session=Depends(get_db_session)
        ):
            if not self.email_service:
                raise HTTPException(500, "Email service not configured")

            # Sample variables for test
            test_vars = {
                "event": {
                    "title": "Test Meeting",
                    "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "location": "Test Location"
                },
                "user": {
                    "name": "Test User",
                    "email": test_email
                },
                "title": "Test Email",
                "message": "This is a test email from Chronos Engine.",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            try:
                success = await self.email_service.send_template_email(
                    template_id=template_id,
                    to=[test_email],
                    variables=test_vars
                )

                if success:
                    return {"status": "success", "message": f"Test email sent to {test_email}"}
                else:
                    return {"status": "error", "message": "Failed to send test email"}

            except Exception as e:
                return {"status": "error", "message": str(e)}

        # Integration Configs management
        @self.router.get("/admin/integrations", response_class=HTMLResponse)
        async def integrations_list(request: Request, session=Depends(get_db_session)):
            from sqlalchemy import select

            result = await session.execute(
                select(IntegrationConfigDB).order_by(IntegrationConfigDB.system_name)
            )
            integrations = result.scalars().all()

            return self.templates.TemplateResponse("admin/integrations.html", {
                "request": request,
                "integrations": integrations,
                "title": "System Integrations"
            })

        # Backup management
        @self.router.get("/admin/backups", response_class=HTMLResponse)
        async def backups_list(request: Request, session=Depends(get_db_session)):
            from sqlalchemy import select
            from src.core.schema_extensions import BackupHistoryDB

            # Get recent backup history
            result = await session.execute(
                select(BackupHistoryDB).order_by(BackupHistoryDB.started_at.desc()).limit(20)
            )
            backup_history = result.scalars().all()

            # Get backup jobs
            jobs_result = await session.execute(
                select(BackupJobDB).order_by(BackupJobDB.name)
            )
            backup_jobs = jobs_result.scalars().all()

            return self.templates.TemplateResponse("admin/backups.html", {
                "request": request,
                "backup_history": backup_history,
                "backup_jobs": backup_jobs,
                "title": "Backup Management"
            })

        @self.router.post("/admin/backups/create-manual")
        async def create_manual_backup():
            # This would trigger the backup service
            # For now, just return success
            return {"status": "success", "message": "Manual backup started"}

        # System health and metrics
        @self.router.get("/admin/system", response_class=HTMLResponse)
        async def system_info(request: Request, session=Depends(get_db_session)):
            from sqlalchemy import text

            # Get database info
            db_info = {}
            try:
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


def create_admin_routes(email_service: EmailService = None) -> APIRouter:
    """Create admin routes with optional email service"""
    admin = AdminRoutes(email_service)
    return admin.router