"""
API Routes für Universal n8n Webhook Integration
Benutzerfreundliche REST API für Webhook Management
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Body, Query, Path
from pydantic import BaseModel, Field, validator

from src.integrations.universal_n8n_service import (
    UniversalN8NService, WebhookConfiguration, FieldMapping, TriggerType
)
from src.integrations.n8n_config_manager import N8NConfigManager


class FieldMappingRequest(BaseModel):
    """Request Model für Field Mapping"""

    webhook_field: str = Field(..., description="Ziel-Feldname im n8n Webhook")
    source_type: str = Field(..., description="Datenquelle: event, system, static, calculated, additional")
    source_field: Optional[str] = Field(None, description="Quell-Feldname (für event/system/additional)")
    static_value: Optional[Any] = Field(None, description="Statischer Wert (für static)")
    calculation: Optional[str] = Field(None, description="Berechnungsformel (für calculated)")
    data_type: str = Field("string", description="Datentyp: string, number, boolean, datetime, array")
    default_value: Optional[Any] = Field(None, description="Default-Wert bei leerer Quelle")
    format_string: Optional[str] = Field(None, description="Format-String für datetime/number")
    condition: Optional[str] = Field(None, description="Bedingung wann Feld gesetzt wird")

    @validator('source_type')
    def validate_source_type(cls, v):
        valid_types = ['event', 'system', 'static', 'calculated', 'additional']
        if v not in valid_types:
            raise ValueError(f'source_type must be one of: {valid_types}')
        return v

    @validator('data_type')
    def validate_data_type(cls, v):
        valid_types = ['string', 'number', 'boolean', 'datetime', 'array']
        if v not in valid_types:
            raise ValueError(f'data_type must be one of: {valid_types}')
        return v


class WebhookConfigRequest(BaseModel):
    """Request Model für Webhook Konfiguration"""

    name: str = Field(..., description="Name/Beschreibung der Konfiguration")
    webhook_url: str = Field(..., description="n8n Webhook URL")
    triggers: List[str] = Field(..., description="Liste der Trigger Types")
    http_method: str = Field("POST", description="HTTP Method")
    headers: Dict[str, str] = Field(default_factory=lambda: {"Content-Type": "application/json"})
    field_mappings: List[FieldMappingRequest] = Field(default_factory=list)
    enabled: bool = Field(True, description="Aktiviert/Deaktiviert")
    max_retries: int = Field(3, description="Maximale Retry-Versuche")
    retry_delay: int = Field(5, description="Retry-Delay in Sekunden")
    timeout: int = Field(30, description="Request-Timeout in Sekunden")
    execution_condition: Optional[str] = Field(None, description="Bedingung für Webhook-Ausführung")

    @validator('triggers')
    def validate_triggers(cls, v):
        valid_triggers = [t.value for t in TriggerType]
        for trigger in v:
            if trigger not in valid_triggers:
                raise ValueError(f'Invalid trigger type: {trigger}. Valid types: {valid_triggers}')
        return v


class WebhookConfigResponse(BaseModel):
    """Response Model für Webhook Konfiguration"""

    config_id: str
    name: str
    webhook_url: str
    triggers: List[str]
    http_method: str
    enabled: bool
    field_mappings_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class N8NWebhookAPI:
    """REST API für n8n Webhook Management"""

    def __init__(self):
        self.router = APIRouter(prefix="/n8n", tags=["n8n Webhooks"])
        self.logger = logging.getLogger(__name__)

        # Services
        self.n8n_service = UniversalN8NService()
        self.config_manager = N8NConfigManager()

        # Lade bestehende Konfigurationen
        self._load_existing_configs()

        # Register routes
        self._register_routes()

    def _load_existing_configs(self):
        """Lade bestehende Konfigurationen beim Start"""
        try:
            configs = self.config_manager.load_all_webhook_configs()
            for config in configs:
                self.n8n_service.register_webhook_config(config)

            self.logger.info(f"🔄 Loaded {len(configs)} webhook configurations")
        except Exception as e:
            self.logger.error(f"Failed to load webhook configs: {e}")

    def _register_routes(self):
        """Registriere alle API Routes"""

        @self.router.get("/webhooks", response_model=List[WebhookConfigResponse])
        async def list_webhook_configs():
            """Liste alle Webhook Konfigurationen"""
            try:
                configs = self.n8n_service.list_webhook_configs()
                return [
                    WebhookConfigResponse(
                        config_id=config.config_id,
                        name=config.name,
                        webhook_url=config.webhook_url,
                        triggers=[t.value for t in config.triggers],
                        http_method=config.http_method,
                        enabled=config.enabled,
                        field_mappings_count=len(config.field_mappings)
                    )
                    for config in configs
                ]
            except Exception as e:
                self.logger.error(f"Failed to list webhook configs: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/webhooks", response_model=WebhookConfigResponse)
        async def create_webhook_config(config_request: WebhookConfigRequest):
            """Erstelle neue Webhook Konfiguration"""
            try:
                # Generate unique config ID
                config_id = f"webhook_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # Convert request to internal models
                field_mappings = [
                    FieldMapping(
                        webhook_field=fm.webhook_field,
                        source_type=fm.source_type,
                        source_field=fm.source_field,
                        static_value=fm.static_value,
                        calculation=fm.calculation,
                        data_type=fm.data_type,
                        default_value=fm.default_value,
                        format_string=fm.format_string,
                        condition=fm.condition
                    )
                    for fm in config_request.field_mappings
                ]

                triggers = [TriggerType(t) for t in config_request.triggers]

                config = WebhookConfiguration(
                    config_id=config_id,
                    name=config_request.name,
                    webhook_url=config_request.webhook_url,
                    triggers=triggers,
                    http_method=config_request.http_method,
                    headers=config_request.headers,
                    field_mappings=field_mappings,
                    enabled=config_request.enabled,
                    max_retries=config_request.max_retries,
                    retry_delay=config_request.retry_delay,
                    timeout=config_request.timeout,
                    execution_condition=config_request.execution_condition
                )

                # Save configuration
                if not self.config_manager.save_webhook_config(config):
                    raise HTTPException(status_code=500, detail="Failed to save configuration")

                # Register in service
                self.n8n_service.register_webhook_config(config)

                return WebhookConfigResponse(
                    config_id=config.config_id,
                    name=config.name,
                    webhook_url=config.webhook_url,
                    triggers=[t.value for t in config.triggers],
                    http_method=config.http_method,
                    enabled=config.enabled,
                    field_mappings_count=len(config.field_mappings),
                    created_at=datetime.now().isoformat()
                )

            except Exception as e:
                self.logger.error(f"Failed to create webhook config: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/webhooks/{config_id}")
        async def get_webhook_config(config_id: str = Path(...)):
            """Hole spezifische Webhook Konfiguration"""
            try:
                config = self.n8n_service.get_webhook_config(config_id)
                if not config:
                    raise HTTPException(status_code=404, detail="Configuration not found")

                return {
                    "config_id": config.config_id,
                    "name": config.name,
                    "webhook_url": config.webhook_url,
                    "triggers": [t.value for t in config.triggers],
                    "http_method": config.http_method,
                    "headers": config.headers,
                    "enabled": config.enabled,
                    "max_retries": config.max_retries,
                    "retry_delay": config.retry_delay,
                    "timeout": config.timeout,
                    "execution_condition": config.execution_condition,
                    "field_mappings": [
                        {
                            "webhook_field": fm.webhook_field,
                            "source_type": fm.source_type,
                            "source_field": fm.source_field,
                            "static_value": fm.static_value,
                            "calculation": fm.calculation,
                            "data_type": fm.data_type,
                            "default_value": fm.default_value,
                            "format_string": fm.format_string,
                            "condition": fm.condition
                        }
                        for fm in config.field_mappings
                    ]
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Failed to get webhook config: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.put("/webhooks/{config_id}")
        async def update_webhook_config(
            config_id: str = Path(...),
            config_request: WebhookConfigRequest = Body(...)
        ):
            """Update Webhook Konfiguration"""
            try:
                # Check if config exists
                existing_config = self.n8n_service.get_webhook_config(config_id)
                if not existing_config:
                    raise HTTPException(status_code=404, detail="Configuration not found")

                # Convert request to internal models
                field_mappings = [
                    FieldMapping(
                        webhook_field=fm.webhook_field,
                        source_type=fm.source_type,
                        source_field=fm.source_field,
                        static_value=fm.static_value,
                        calculation=fm.calculation,
                        data_type=fm.data_type,
                        default_value=fm.default_value,
                        format_string=fm.format_string,
                        condition=fm.condition
                    )
                    for fm in config_request.field_mappings
                ]

                triggers = [TriggerType(t) for t in config_request.triggers]

                updated_config = WebhookConfiguration(
                    config_id=config_id,
                    name=config_request.name,
                    webhook_url=config_request.webhook_url,
                    triggers=triggers,
                    http_method=config_request.http_method,
                    headers=config_request.headers,
                    field_mappings=field_mappings,
                    enabled=config_request.enabled,
                    max_retries=config_request.max_retries,
                    retry_delay=config_request.retry_delay,
                    timeout=config_request.timeout,
                    execution_condition=config_request.execution_condition
                )

                # Save configuration
                if not self.config_manager.save_webhook_config(updated_config):
                    raise HTTPException(status_code=500, detail="Failed to save configuration")

                # Update in service
                self.n8n_service.register_webhook_config(updated_config)

                return {"message": "Configuration updated successfully"}

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Failed to update webhook config: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.delete("/webhooks/{config_id}")
        async def delete_webhook_config(config_id: str = Path(...)):
            """Lösche Webhook Konfiguration"""
            try:
                # Check if config exists
                existing_config = self.n8n_service.get_webhook_config(config_id)
                if not existing_config:
                    raise HTTPException(status_code=404, detail="Configuration not found")

                # Delete from storage
                if not self.config_manager.delete_webhook_config(config_id):
                    raise HTTPException(status_code=500, detail="Failed to delete configuration")

                # Remove from service
                self.n8n_service.remove_webhook_config(config_id)

                return {"message": "Configuration deleted successfully"}

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Failed to delete webhook config: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/webhooks/{config_id}/test")
        async def test_webhook_config(config_id: str = Path(...)):
            """Teste Webhook Konfiguration"""
            try:
                result = await self.n8n_service.test_webhook_config(config_id)

                if not result.get("success", False):
                    return {
                        "test_successful": False,
                        "error": result.get("error", "Unknown error"),
                        "config_id": config_id
                    }

                return {
                    "test_successful": True,
                    "config_id": result["config_id"],
                    "config_name": result["config_name"],
                    "test_payload": result["test_payload"],
                    "webhook_response": result["webhook_result"]
                }

            except Exception as e:
                self.logger.error(f"Failed to test webhook config: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.post("/trigger")
        async def trigger_webhooks(
            trigger_type: str = Query(..., description="Trigger Type"),
            event_id: Optional[str] = Query(None, description="Event ID (optional)"),
            additional_data: Optional[Dict[str, Any]] = Body(None)
        ):
            """Triggere Webhooks manuell"""
            try:
                # Validate trigger type
                try:
                    trigger_enum = TriggerType(trigger_type)
                except ValueError:
                    valid_triggers = [t.value for t in TriggerType]
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid trigger type. Valid types: {valid_triggers}"
                    )

                # Load event if provided
                event = None
                if event_id:
                    # Here you would load the actual event from database
                    # For now, we'll use None and rely on additional_data
                    pass

                # Trigger webhooks
                result = await self.n8n_service.trigger_webhooks(
                    trigger_type=trigger_enum,
                    event=event,
                    additional_data=additional_data
                )

                return {
                    "trigger_type": trigger_type,
                    "triggered": result["triggered"],
                    "successful": result["successful"],
                    "failed": result["failed"],
                    "results": result["results"]
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Failed to trigger webhooks: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.router.get("/triggers")
        async def list_trigger_types():
            """Liste alle verfügbaren Trigger Types"""
            return {
                "trigger_types": [
                    {
                        "value": t.value,
                        "name": t.name,
                        "description": self._get_trigger_description(t)
                    }
                    for t in TriggerType
                ]
            }

        @self.router.get("/field-sources")
        async def list_field_sources():
            """Liste alle verfügbaren Field Sources"""
            return {
                "event_fields": [
                    "id", "title", "description", "location", "start_time", "end_time",
                    "priority", "status", "attendees", "tags", "duration_minutes",
                    "is_urgent", "is_today"
                ],
                "system_fields": [
                    "version", "environment", "instance_id"
                ],
                "source_types": [
                    {
                        "value": "event",
                        "description": "Daten aus dem Event-Objekt"
                    },
                    {
                        "value": "system",
                        "description": "System-Informationen"
                    },
                    {
                        "value": "static",
                        "description": "Statische Werte"
                    },
                    {
                        "value": "calculated",
                        "description": "Berechnete Werte via Python Expression"
                    },
                    {
                        "value": "additional",
                        "description": "Zusätzliche Context-Daten"
                    }
                ],
                "data_types": [
                    "string", "number", "boolean", "datetime", "array"
                ]
            }

    def _get_trigger_description(self, trigger: TriggerType) -> str:
        """Hole Beschreibung für Trigger Type"""
        descriptions = {
            TriggerType.EVENT_CREATED: "Event wurde erstellt",
            TriggerType.EVENT_UPDATED: "Event wurde aktualisiert",
            TriggerType.EVENT_CANCELLED: "Event wurde abgesagt",
            TriggerType.EVENT_COMPLETED: "Event wurde abgeschlossen",
            TriggerType.EVENT_REMINDER: "Event-Erinnerung",
            TriggerType.CONFLICT_DETECTED: "Konflikt erkannt",
            TriggerType.OPTIMIZATION_SUGGESTED: "Optimierung vorgeschlagen",
            TriggerType.DAILY_SUMMARY: "Tägliche Zusammenfassung",
            TriggerType.CUSTOM: "Benutzerdefiniert"
        }
        return descriptions.get(trigger, "Keine Beschreibung verfügbar")


# Global API instance
n8n_webhook_api = N8NWebhookAPI()