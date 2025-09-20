"""
Universal n8n Webhook Service für CRONOS
Flexible Integration für beliebige n8n Workflows mit konfigurierbaren Payloads
"""

import logging
import aiohttp
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import re
import asyncio
from datetime import timedelta

from src.core.models import ChronosEvent, Priority, EventStatus


class TriggerType(Enum):
    """Event Trigger Types für n8n Webhooks"""
    EVENT_CREATED = "event_created"
    EVENT_UPDATED = "event_updated"
    EVENT_CANCELLED = "event_cancelled"
    EVENT_COMPLETED = "event_completed"
    EVENT_REMINDER = "event_reminder"
    CONFLICT_DETECTED = "conflict_detected"
    OPTIMIZATION_SUGGESTED = "optimization_suggested"
    DAILY_SUMMARY = "daily_summary"
    CUSTOM = "custom"


@dataclass
class FieldMapping:
    """Mapping Definition für Event-Felder zu n8n Webhook Feldern"""

    # n8n Webhook Feld Name
    webhook_field: str

    # Quelle der Daten (event, system, static, calculated)
    source_type: str

    # Quell-Feld Name (bei source_type = 'event' oder 'system')
    source_field: Optional[str] = None

    # Statischer Wert (bei source_type = 'static')
    static_value: Optional[Any] = None

    # Berechnungsformel (bei source_type = 'calculated')
    calculation: Optional[str] = None

    # Datentyp Transformation
    data_type: str = "string"  # string, number, boolean, datetime, array

    # Default Wert falls Quelle leer
    default_value: Optional[Any] = None

    # Formatierung (für datetime, number etc.)
    format_string: Optional[str] = None

    # Bedingung wann Feld gesetzt wird
    condition: Optional[str] = None


@dataclass
class WebhookConfiguration:
    """Konfiguration für einen n8n Webhook"""

    # Eindeutige ID für die Konfiguration
    config_id: str

    # Name/Beschreibung
    name: str

    # n8n Webhook URL
    webhook_url: str

    # Trigger Types die diese Konfiguration verwenden
    triggers: List[TriggerType]

    # HTTP Method (POST, PUT, PATCH)
    http_method: str = "POST"

    # Headers für den Request
    headers: Dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})

    # Field Mappings
    field_mappings: List[FieldMapping] = field(default_factory=list)

    # Aktiviert/Deaktiviert
    enabled: bool = True

    # Retry Konfiguration
    max_retries: int = 3
    retry_delay: int = 5

    # Timeout in Sekunden
    timeout: int = 30

    # Bedingung wann Webhook ausgeführt wird
    execution_condition: Optional[str] = None


class UniversalN8NService:
    """Universal n8n Webhook Service mit konfigurierbaren Field Mappings"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None

        # Webhook Konfigurationen (normalerweise aus DB geladen)
        self.webhook_configs: Dict[str, WebhookConfiguration] = {}

        # Event Context für Berechnungen
        self.event_context: Dict[str, Any] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Async HTTP Session für n8n API"""
        if not self.session:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        return self.session

    def register_webhook_config(self, config: WebhookConfiguration):
        """Registriere eine neue Webhook Konfiguration"""
        self.webhook_configs[config.config_id] = config
        self.logger.info(f"📝 Registered webhook config: {config.name} ({config.config_id})")

    def remove_webhook_config(self, config_id: str):
        """Entferne Webhook Konfiguration"""
        if config_id in self.webhook_configs:
            config = self.webhook_configs.pop(config_id)
            self.logger.info(f"🗑️ Removed webhook config: {config.name}")

    def get_webhook_config(self, config_id: str) -> Optional[WebhookConfiguration]:
        """Hole Webhook Konfiguration"""
        return self.webhook_configs.get(config_id)

    def list_webhook_configs(self, trigger_type: Optional[TriggerType] = None) -> List[WebhookConfiguration]:
        """Liste alle Webhook Konfigurationen"""
        configs = list(self.webhook_configs.values())

        if trigger_type:
            configs = [c for c in configs if trigger_type in c.triggers]

        return [c for c in configs if c.enabled]

    async def trigger_webhooks(
        self,
        trigger_type: TriggerType,
        event: Optional[ChronosEvent] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Triggere alle relevanten Webhooks für einen Event Type"""

        # Relevante Konfigurations finden
        relevant_configs = self.list_webhook_configs(trigger_type)

        if not relevant_configs:
            self.logger.debug(f"No webhook configs found for trigger: {trigger_type.value}")
            return {"triggered": 0, "results": []}

        self.logger.info(f"🚀 Triggering {len(relevant_configs)} webhooks for: {trigger_type.value}")

        # Event Context vorbereiten
        await self._prepare_event_context(event, additional_data)

        results = []

        for config in relevant_configs:
            try:
                # Execution Condition prüfen
                if not await self._check_execution_condition(config, event):
                    self.logger.debug(f"Skipping webhook {config.name} - condition not met")
                    continue

                # Payload generieren
                payload = await self._build_payload(config, event, additional_data)

                # Webhook ausführen
                result = await self._execute_webhook(config, payload)
                results.append({
                    "config_id": config.config_id,
                    "config_name": config.name,
                    "success": result["success"],
                    "response": result.get("response"),
                    "error": result.get("error")
                })

            except Exception as e:
                self.logger.error(f"Failed to execute webhook {config.name}: {e}")
                results.append({
                    "config_id": config.config_id,
                    "config_name": config.name,
                    "success": False,
                    "error": str(e)
                })

        successful_triggers = sum(1 for r in results if r["success"])

        return {
            "triggered": len(results),
            "successful": successful_triggers,
            "failed": len(results) - successful_triggers,
            "results": results
        }

    async def _prepare_event_context(
        self,
        event: Optional[ChronosEvent],
        additional_data: Optional[Dict[str, Any]]
    ):
        """Bereite Event Context für Field Mappings vor"""

        self.event_context = {
            "timestamp": datetime.utcnow(),
            "system": {
                "version": "2.1.0",
                "environment": "production",  # Aus Config
                "instance_id": "chronos-main"
            }
        }

        if event:
            self.event_context["event"] = {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "location": event.location,
                "start_time": event.start_time,
                "end_time": event.end_time,
                "priority": event.priority.value if event.priority else None,
                "status": event.status.value if event.status else None,
                "attendees": event.attendees or [],
                "tags": event.tags or [],
                "duration_minutes": int((event.end_time - event.start_time).total_seconds() / 60) if event.end_time and event.start_time else 0,
                "is_urgent": event.priority == Priority.URGENT if event.priority else False,
                "is_today": event.start_time.date() == datetime.now().date() if event.start_time else False
            }

        if additional_data:
            self.event_context["additional"] = additional_data

    async def _check_execution_condition(
        self,
        config: WebhookConfiguration,
        event: Optional[ChronosEvent]
    ) -> bool:
        """Prüfe ob Execution Condition erfüllt ist"""

        if not config.execution_condition:
            return True

        try:
            # Sichere Evaluation der Bedingung
            return await self._evaluate_condition(config.execution_condition)
        except Exception as e:
            self.logger.error(f"Failed to evaluate execution condition: {e}")
            return False

    async def _build_payload(
        self,
        config: WebhookConfiguration,
        event: Optional[ChronosEvent],
        additional_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Baue Webhook Payload basierend auf Field Mappings"""

        payload = {}

        for mapping in config.field_mappings:
            try:
                # Condition prüfen
                if mapping.condition and not await self._evaluate_condition(mapping.condition):
                    continue

                # Wert ermitteln
                value = await self._get_field_value(mapping)

                # Datentyp Transformation
                value = await self._transform_data_type(value, mapping)

                # In Payload setzen (unterstützt nested fields wie "user.email")
                await self._set_nested_field(payload, mapping.webhook_field, value)

            except Exception as e:
                self.logger.error(f"Failed to map field {mapping.webhook_field}: {e}")
                # Default Wert setzen falls verfügbar
                if mapping.default_value is not None:
                    await self._set_nested_field(payload, mapping.webhook_field, mapping.default_value)

        return payload

    async def _get_field_value(self, mapping: FieldMapping) -> Any:
        """Ermittle Wert für Field Mapping"""

        if mapping.source_type == "static":
            return mapping.static_value

        elif mapping.source_type == "event":
            if not mapping.source_field:
                return None
            return self._get_nested_value(self.event_context.get("event", {}), mapping.source_field)

        elif mapping.source_type == "system":
            if not mapping.source_field:
                return None
            return self._get_nested_value(self.event_context.get("system", {}), mapping.source_field)

        elif mapping.source_type == "additional":
            if not mapping.source_field:
                return None
            return self._get_nested_value(self.event_context.get("additional", {}), mapping.source_field)

        elif mapping.source_type == "calculated":
            return await self._calculate_value(mapping.calculation)

        return mapping.default_value

    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Hole Wert aus nested Dict (z.B. 'user.profile.email')"""

        keys = field_path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None

        return value

    async def _set_nested_field(self, data: Dict[str, Any], field_path: str, value: Any):
        """Setze Wert in nested Dict"""

        keys = field_path.split(".")
        current = data

        # Navigiere zu parent dict
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Setze final value
        current[keys[-1]] = value

    async def _calculate_value(self, calculation: Optional[str]) -> Any:
        """Berechne Wert basierend auf Formel"""

        if not calculation:
            return None

        try:
            # Sichere Berechnung mit begrenztem Context
            safe_context = {
                "event": self.event_context.get("event", {}),
                "system": self.event_context.get("system", {}),
                "additional": self.event_context.get("additional", {}),
                "datetime": datetime,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool
            }

            # Evaluiere Formel
            result = eval(calculation, {"__builtins__": {}}, safe_context)
            return result

        except Exception as e:
            self.logger.error(f"Failed to calculate value: {calculation} - {e}")
            return None

    async def _evaluate_condition(self, condition: str) -> bool:
        """Evaluiere Bedingung"""

        try:
            safe_context = {
                "event": self.event_context.get("event", {}),
                "system": self.event_context.get("system", {}),
                "additional": self.event_context.get("additional", {}),
                "datetime": datetime
            }

            result = eval(condition, {"__builtins__": {}}, safe_context)
            return bool(result)

        except Exception as e:
            self.logger.error(f"Failed to evaluate condition: {condition} - {e}")
            return False

    async def _transform_data_type(self, value: Any, mapping: FieldMapping) -> Any:
        """Transformiere Datentyp"""

        if value is None:
            return mapping.default_value

        try:
            if mapping.data_type == "string":
                if mapping.format_string and isinstance(value, datetime):
                    return value.strftime(mapping.format_string)
                return str(value)

            elif mapping.data_type == "number":
                if isinstance(value, str):
                    return float(value) if "." in value else int(value)
                return float(value) if isinstance(value, (int, float)) else 0

            elif mapping.data_type == "boolean":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value)

            elif mapping.data_type == "datetime":
                if isinstance(value, datetime):
                    format_str = mapping.format_string or "%Y-%m-%dT%H:%M:%SZ"
                    return value.strftime(format_str)
                return str(value)

            elif mapping.data_type == "array":
                if isinstance(value, (list, tuple)):
                    return list(value)
                elif isinstance(value, str):
                    # Split by comma
                    return [item.strip() for item in value.split(",")]
                return [value]

            return value

        except Exception as e:
            self.logger.error(f"Failed to transform data type: {e}")
            return mapping.default_value

    async def _execute_webhook(
        self,
        config: WebhookConfiguration,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Führe Webhook Request aus mit Retry Logic"""

        session = await self._get_session()

        for attempt in range(config.max_retries + 1):
            try:
                self.logger.debug(f"🔄 Executing webhook {config.name} (attempt {attempt + 1})")

                async with session.request(
                    method=config.http_method,
                    url=config.webhook_url,
                    json=payload,
                    headers=config.headers,
                    timeout=aiohttp.ClientTimeout(total=config.timeout)
                ) as response:

                    response_text = await response.text()

                    if response.status >= 200 and response.status < 300:
                        self.logger.info(f"✅ Webhook {config.name} successful: {response.status}")

                        # Parse response if JSON
                        try:
                            response_data = json.loads(response_text)
                        except:
                            response_data = response_text

                        return {
                            "success": True,
                            "status_code": response.status,
                            "response": response_data
                        }
                    else:
                        error_msg = f"HTTP {response.status}: {response_text}"
                        self.logger.warning(f"⚠️ Webhook {config.name} failed: {error_msg}")

                        if attempt < config.max_retries:
                            await asyncio.sleep(config.retry_delay)
                            continue
                        else:
                            return {
                                "success": False,
                                "status_code": response.status,
                                "error": error_msg
                            }

            except asyncio.TimeoutError:
                error_msg = f"Timeout after {config.timeout}s"
                self.logger.warning(f"⏰ Webhook {config.name} timeout: {error_msg}")

                if attempt < config.max_retries:
                    await asyncio.sleep(config.retry_delay)
                    continue
                else:
                    return {"success": False, "error": error_msg}

            except Exception as e:
                error_msg = str(e)
                self.logger.error(f"❌ Webhook {config.name} error: {error_msg}")

                if attempt < config.max_retries:
                    await asyncio.sleep(config.retry_delay)
                    continue
                else:
                    return {"success": False, "error": error_msg}

        return {"success": False, "error": "Max retries exceeded"}

    async def test_webhook_config(self, config_id: str) -> Dict[str, Any]:
        """Teste Webhook Konfiguration mit Mock Data"""

        config = self.get_webhook_config(config_id)
        if not config:
            return {"success": False, "error": "Configuration not found"}

        # Mock Event für Test
        mock_event = ChronosEvent(
            id="test-event-123",
            title="Test Event",
            description="This is a test event for webhook validation",
            location="Test Location",
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=1),
            priority=Priority.MEDIUM,
            status=EventStatus.SCHEDULED,
            attendees=["test@example.com"],
            tags=["test", "webhook"]
        )

        # Test Data vorbereiten
        await self._prepare_event_context(mock_event, {"test": True})

        # Payload bauen
        payload = await self._build_payload(config, mock_event, {"test": True})

        # Test Request ausführen
        result = await self._execute_webhook(config, payload)

        return {
            "config_id": config_id,
            "config_name": config.name,
            "test_payload": payload,
            "webhook_result": result
        }

    async def close(self):
        """Cleanup HTTP Session"""
        if self.session:
            await self.session.close()