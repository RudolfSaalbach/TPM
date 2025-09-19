"""
n8n integration adapter for Chronos Engine
Handles outbound webhooks to n8n workflows and inbound callbacks
"""

import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import time

import httpx

from src.core.outbox import OutboxService, outbox_registry
from src.core.security import security_service
from src.core.schema_extensions import IntegrationConfigDB, WebhookTemplateDB


@dataclass
class N8nConfig:
    """n8n integration configuration"""
    webhook_base_url: str
    webhook_secret: Optional[str] = None
    default_timeout: int = 30
    retry_count: int = 3
    verify_ssl: bool = True


@dataclass
class WebhookTemplate:
    """Webhook payload template"""
    id: Optional[int] = None
    name: str = ""
    target_system: str = "N8N"
    payload_template: str = ""
    headers_template: Dict[str, str] = None
    variables: List[str] = None

    @classmethod
    def from_db(cls, db_template: WebhookTemplateDB) -> 'WebhookTemplate':
        """Create from database model"""
        return cls(
            id=db_template.id,
            name=db_template.name,
            target_system=db_template.target_system,
            payload_template=db_template.payload_template,
            headers_template=db_template.headers_template or {},
            variables=db_template.variables or []
        )


class N8nAdapter:
    """n8n integration adapter"""

    def __init__(self, config: N8nConfig, outbox_service: OutboxService,
                 db_session_factory=None):
        self.config = config
        self.outbox_service = outbox_service
        self.db_session_factory = db_session_factory

        # Register outbox handler
        outbox_registry.register_handler('N8N', self._handle_outbox_entry)

    async def send_webhook(self, workflow_name: str, payload: Dict[str, Any],
                          template_id: Optional[int] = None,
                          custom_headers: Dict[str, str] = None) -> bool:
        """Send webhook to n8n workflow"""
        try:
            # Get webhook template if specified
            if template_id:
                template = await self._get_webhook_template(template_id)
                if template:
                    payload = await self._apply_template(template, payload)
                    custom_headers = {**(custom_headers or {}), **template.headers_template}

            # Build webhook URL
            webhook_url = f"{self.config.webhook_base_url}/{workflow_name}"

            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Chronos-Engine/2.1",
                **(custom_headers or {})
            }

            # Add signature if secret is configured
            if self.config.webhook_secret:
                timestamp = int(time.time())
                payload_str = json.dumps(payload, sort_keys=True)
                signature = self._generate_signature(payload_str, timestamp)

                headers["X-Chronos-Signature"] = signature
                headers["X-Chronos-Timestamp"] = str(timestamp)

            # Send webhook
            async with httpx.AsyncClient(verify=self.config.verify_ssl) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.default_timeout
                )

                # Check response
                if response.status_code == 200:
                    return True
                else:
                    print(f"n8n webhook failed: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"n8n webhook error: {e}")
            return False

    def _generate_signature(self, payload: str, timestamp: int) -> str:
        """Generate HMAC signature for webhook"""
        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            self.config.webhook_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    async def handle_callback(self, workflow_name: str, payload: Dict[str, Any],
                            signature: Optional[str] = None,
                            timestamp: Optional[str] = None) -> Dict[str, Any]:
        """Handle callback from n8n workflow"""
        # Verify signature if provided
        if signature and timestamp and self.config.webhook_secret:
            if not self._verify_callback_signature(payload, signature, timestamp):
                raise ValueError("Invalid callback signature")

        # Process callback based on workflow
        return await self._process_callback(workflow_name, payload)

    def _verify_callback_signature(self, payload: Dict[str, Any],
                                  signature: str, timestamp: str) -> bool:
        """Verify callback signature"""
        try:
            ts = int(timestamp)
            # Check timestamp (prevent replay attacks)
            current_time = int(time.time())
            if abs(current_time - ts) > 300:  # 5 minutes
                return False

            payload_str = json.dumps(payload, sort_keys=True)
            expected_signature = self._generate_signature(payload_str, ts)

            return hmac.compare_digest(signature, expected_signature)

        except Exception:
            return False

    async def _process_callback(self, workflow_name: str,
                               payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process callback from n8n workflow"""
        result = {"status": "processed", "workflow": workflow_name}

        try:
            # Handle different callback types
            callback_type = payload.get("type", "unknown")

            if callback_type == "action_completed":
                await self._handle_action_completed(payload)
                result["action"] = "action_completed"

            elif callback_type == "notification":
                await self._handle_notification_callback(payload)
                result["action"] = "notification_sent"

            elif callback_type == "data_update":
                await self._handle_data_update(payload)
                result["action"] = "data_updated"

            else:
                print(f"Unknown callback type: {callback_type}")
                result["action"] = "unknown_type"

        except Exception as e:
            print(f"Callback processing error: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        return result

    async def _handle_action_completed(self, payload: Dict[str, Any]):
        """Handle action completion callback"""
        action_id = payload.get("action_id")
        status = payload.get("status", "completed")
        result_data = payload.get("result", {})
        error_message = payload.get("error")

        if not action_id:
            return

        # Update action status in database
        if self.db_session_factory:
            from sqlalchemy import select
            from src.core.schema_extensions import CommandExecutionDB

            async with self.db_session_factory() as session:
                result = await session.execute(
                    select(CommandExecutionDB).where(
                        CommandExecutionDB.idempotency_key == action_id
                    )
                )
                command = result.scalar_one_or_none()

                if command:
                    command.status = status
                    command.result_data = result_data
                    command.error_message = error_message
                    command.completed_at = datetime.now()
                    await session.commit()

    async def _handle_notification_callback(self, payload: Dict[str, Any]):
        """Handle notification callback"""
        # This could trigger additional notifications or updates
        pass

    async def _handle_data_update(self, payload: Dict[str, Any]):
        """Handle data update callback"""
        # This could update events or other data based on external changes
        pass

    async def _get_webhook_template(self, template_id: int) -> Optional[WebhookTemplate]:
        """Get webhook template from database"""
        if not self.db_session_factory:
            return None

        try:
            from sqlalchemy import select

            async with self.db_session_factory() as session:
                result = await session.execute(
                    select(WebhookTemplateDB).where(
                        WebhookTemplateDB.id == template_id,
                        WebhookTemplateDB.enabled == True
                    )
                )
                db_template = result.scalar_one_or_none()

                if db_template:
                    return WebhookTemplate.from_db(db_template)

        except Exception as e:
            print(f"Error getting webhook template: {e}")

        return None

    async def _apply_template(self, template: WebhookTemplate,
                             variables: Dict[str, Any]) -> Dict[str, Any]:
        """Apply template to create webhook payload"""
        try:
            # Simple variable substitution in JSON template
            template_str = template.payload_template

            # Replace variables
            for key, value in variables.items():
                placeholder = f"{{{{{key}}}}}"
                template_str = template_str.replace(placeholder, json.dumps(value) if not isinstance(value, str) else value)

            # Parse as JSON
            return json.loads(template_str)

        except Exception as e:
            print(f"Template application error: {e}")
            return variables

    async def _handle_outbox_entry(self, entry) -> bool:
        """Handle outbound webhooks via outbox"""
        try:
            payload = entry.payload

            if entry.event_type == "action_request":
                # Send action request to n8n
                workflow_name = payload.get("workflow", "chronos-actions")
                return await self.send_webhook(workflow_name, payload)

            elif entry.event_type == "event_notification":
                # Send event notification
                workflow_name = payload.get("workflow", "chronos-notifications")
                return await self.send_webhook(workflow_name, payload)

            elif entry.event_type == "data_sync":
                # Send data synchronization
                workflow_name = payload.get("workflow", "chronos-sync")
                return await self.send_webhook(workflow_name, payload)

            else:
                # Generic webhook
                workflow_name = payload.get("workflow", "chronos-generic")
                return await self.send_webhook(workflow_name, payload)

        except Exception as e:
            print(f"n8n outbox handler error: {e}")
            return False

    # Template management methods

    async def create_webhook_template(self, template: WebhookTemplate) -> int:
        """Create webhook template"""
        if not self.db_session_factory:
            return 0

        try:
            db_template = WebhookTemplateDB(
                name=template.name,
                target_system=template.target_system,
                payload_template=template.payload_template,
                headers_template=template.headers_template,
                variables=template.variables,
                enabled=True,
                created_by="system"
            )

            async with self.db_session_factory() as session:
                session.add(db_template)
                await session.commit()
                await session.refresh(db_template)
                return db_template.id

        except Exception as e:
            print(f"Error creating webhook template: {e}")
            return 0

    async def get_webhook_templates(self) -> List[WebhookTemplate]:
        """Get all webhook templates"""
        if not self.db_session_factory:
            return []

        try:
            from sqlalchemy import select

            async with self.db_session_factory() as session:
                result = await session.execute(
                    select(WebhookTemplateDB).where(
                        WebhookTemplateDB.target_system == "N8N",
                        WebhookTemplateDB.enabled == True
                    ).order_by(WebhookTemplateDB.name)
                )
                db_templates = result.scalars().all()

                return [WebhookTemplate.from_db(template) for template in db_templates]

        except Exception as e:
            print(f"Error getting webhook templates: {e}")
            return []

    async def test_connection(self) -> bool:
        """Test connection to n8n"""
        try:
            # Send a simple ping to test connectivity
            test_payload = {
                "type": "ping",
                "timestamp": datetime.now().isoformat(),
                "source": "chronos-engine"
            }

            return await self.send_webhook("test", test_payload)

        except Exception:
            return False


async def create_n8n_adapter(db_session_factory=None,
                           outbox_service=None) -> Optional[N8nAdapter]:
    """Create n8n adapter from database configuration"""
    if not db_session_factory:
        return None

    try:
        from sqlalchemy import select

        async with db_session_factory() as session:
            result = await session.execute(
                select(IntegrationConfigDB).where(
                    IntegrationConfigDB.system_name == "N8N",
                    IntegrationConfigDB.enabled == True
                )
            )
            config_db = result.scalar_one_or_none()

            if not config_db:
                return None

            config_data = config_db.config_data
            n8n_config = N8nConfig(
                webhook_base_url=config_data.get("webhook_base_url", ""),
                webhook_secret=config_data.get("webhook_secret"),
                default_timeout=config_data.get("default_timeout", 30),
                retry_count=config_data.get("retry_count", 3),
                verify_ssl=config_data.get("verify_ssl", True)
            )

            if not n8n_config.webhook_base_url:
                return None

            return N8nAdapter(n8n_config, outbox_service, db_session_factory)

    except Exception as e:
        print(f"Failed to create n8n adapter: {e}")
        return None


# Default webhook templates
DEFAULT_N8N_TEMPLATES = [
    {
        "name": "Action Request",
        "payload_template": """
        {
            "type": "action_request",
            "action_id": "{{action_id}}",
            "command": "{{command}}",
            "target_system": "{{target_system}}",
            "parameters": {{parameters}},
            "event": {{event}},
            "timestamp": "{{timestamp}}",
            "source": "chronos-engine"
        }
        """,
        "variables": ["action_id", "command", "target_system", "parameters", "event", "timestamp"]
    },
    {
        "name": "Event Notification",
        "payload_template": """
        {
            "type": "event_notification",
            "event": {{event}},
            "notification_type": "{{notification_type}}",
            "recipients": {{recipients}},
            "timestamp": "{{timestamp}}",
            "source": "chronos-engine"
        }
        """,
        "variables": ["event", "notification_type", "recipients", "timestamp"]
    },
    {
        "name": "Data Sync",
        "payload_template": """
        {
            "type": "data_sync",
            "entity_type": "{{entity_type}}",
            "entity_id": "{{entity_id}}",
            "operation": "{{operation}}",
            "data": {{data}},
            "timestamp": "{{timestamp}}",
            "source": "chronos-engine"
        }
        """,
        "variables": ["entity_type", "entity_id", "operation", "data", "timestamp"]
    }
]