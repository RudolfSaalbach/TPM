"""
Integration adapters for Chronos Engine
Provides unified access to external system integrations
"""

from typing import Dict, Optional, Any
from src.integrations.telegram_adapter import TelegramAdapter, create_telegram_adapter
from src.integrations.n8n_adapter import N8nAdapter, create_n8n_adapter
from src.integrations.universal_n8n_service import (
    UniversalN8NService,
    WebhookConfiguration,
    FieldMapping,
    TriggerType
)
from src.integrations.n8n_config_manager import N8NConfigManager


class IntegrationManager:
    """Manager for all system integrations"""

    def __init__(self, db_session_factory=None, outbox_service=None):
        self.db_session_factory = db_session_factory
        self.outbox_service = outbox_service
        self.adapters: Dict[str, Any] = {}

    async def initialize(self):
        """Initialize all configured integrations"""
        try:
            # Initialize Telegram adapter
            telegram_adapter = await create_telegram_adapter(
                self.db_session_factory, self.outbox_service
            )
            if telegram_adapter:
                self.adapters['telegram'] = telegram_adapter
                print("✅ Telegram integration initialized")

            # Initialize n8n adapter
            n8n_adapter = await create_n8n_adapter(
                self.db_session_factory, self.outbox_service
            )
            if n8n_adapter:
                self.adapters['n8n'] = n8n_adapter
                print("✅ n8n integration initialized")

            # Initialize Universal n8n service
            universal_n8n = UniversalN8NService()
            config_manager = N8NConfigManager()

            # Load existing webhook configurations
            configs = config_manager.load_all_webhook_configs()
            for config in configs:
                universal_n8n.register_webhook_config(config)

            self.adapters['universal_n8n'] = universal_n8n
            self.adapters['n8n_config_manager'] = config_manager
            print(f"✅ Universal n8n service initialized with {len(configs)} webhook configs")

            print(f"🔗 Initialized {len(self.adapters)} integrations")

        except Exception as e:
            print(f"❌ Error initializing integrations: {e}")

    def get_adapter(self, name: str) -> Optional[Any]:
        """Get integration adapter by name"""
        return self.adapters.get(name.lower())

    async def test_all_connections(self) -> Dict[str, bool]:
        """Test connections to all integrations"""
        results = {}

        for name, adapter in self.adapters.items():
            try:
                if hasattr(adapter, 'test_connection'):
                    results[name] = await adapter.test_connection()
                else:
                    results[name] = True  # Assume working if no test method
            except Exception as e:
                print(f"Connection test failed for {name}: {e}")
                results[name] = False

        return results

    async def shutdown(self):
        """Shutdown all integrations"""
        for name, adapter in self.adapters.items():
            try:
                if hasattr(adapter, 'shutdown'):
                    await adapter.shutdown()
            except Exception as e:
                print(f"Error shutting down {name}: {e}")

        self.adapters.clear()


# Global integration manager instance
integration_manager = IntegrationManager()


__all__ = [
    'TelegramAdapter',
    'N8nAdapter',
    'IntegrationManager',
    'integration_manager',
    'create_telegram_adapter',
    'create_n8n_adapter',
    'UniversalN8NService',
    'WebhookConfiguration',
    'FieldMapping',
    'TriggerType',
    'N8NConfigManager'
]