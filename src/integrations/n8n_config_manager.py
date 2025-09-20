"""
Manager für n8n Webhook Konfigurationen
Laden/Speichern von Konfigurationen
"""

import json
import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from .universal_n8n_service import WebhookConfiguration, FieldMapping, TriggerType


class N8NConfigManager:
    """Manager für n8n Webhook Konfigurationen"""

    def __init__(self, config_dir: str = "./config/n8n_webhooks"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def save_webhook_config(self, config: WebhookConfiguration) -> bool:
        """Speichere Webhook Konfiguration als JSON"""

        try:
            config_file = self.config_dir / f"{config.config_id}.json"

            # Convert to dict
            config_dict = {
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

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)

            self.logger.info(f"💾 Saved webhook config: {config.name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save webhook config: {e}")
            return False

    def load_webhook_config(self, config_id: str) -> Optional[WebhookConfiguration]:
        """Lade Webhook Konfiguration"""

        try:
            config_file = self.config_dir / f"{config_id}.json"

            if not config_file.exists():
                return None

            with open(config_file, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)

            # Convert back to objects
            field_mappings = [
                FieldMapping(
                    webhook_field=fm["webhook_field"],
                    source_type=fm["source_type"],
                    source_field=fm.get("source_field"),
                    static_value=fm.get("static_value"),
                    calculation=fm.get("calculation"),
                    data_type=fm.get("data_type", "string"),
                    default_value=fm.get("default_value"),
                    format_string=fm.get("format_string"),
                    condition=fm.get("condition")
                )
                for fm in config_dict.get("field_mappings", [])
            ]

            triggers = [TriggerType(t) for t in config_dict.get("triggers", [])]

            config = WebhookConfiguration(
                config_id=config_dict["config_id"],
                name=config_dict["name"],
                webhook_url=config_dict["webhook_url"],
                triggers=triggers,
                http_method=config_dict.get("http_method", "POST"),
                headers=config_dict.get("headers", {"Content-Type": "application/json"}),
                field_mappings=field_mappings,
                enabled=config_dict.get("enabled", True),
                max_retries=config_dict.get("max_retries", 3),
                retry_delay=config_dict.get("retry_delay", 5),
                timeout=config_dict.get("timeout", 30),
                execution_condition=config_dict.get("execution_condition")
            )

            return config

        except Exception as e:
            self.logger.error(f"Failed to load webhook config {config_id}: {e}")
            return None

    def load_all_webhook_configs(self) -> List[WebhookConfiguration]:
        """Lade alle Webhook Konfigurationen"""

        configs = []

        for config_file in self.config_dir.glob("*.json"):
            config_id = config_file.stem
            config = self.load_webhook_config(config_id)

            if config:
                configs.append(config)

        self.logger.info(f"📋 Loaded {len(configs)} webhook configurations")
        return configs

    def delete_webhook_config(self, config_id: str) -> bool:
        """Lösche Webhook Konfiguration"""

        try:
            config_file = self.config_dir / f"{config_id}.json"

            if config_file.exists():
                config_file.unlink()
                self.logger.info(f"🗑️ Deleted webhook config: {config_id}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to delete webhook config {config_id}: {e}")
            return False