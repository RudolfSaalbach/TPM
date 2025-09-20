"""
Calendar Source Manager
Manages different calendar backends (CalDAV/Radicale and Google Calendar)
through unified SourceAdapter interface
"""

from typing import Dict, Any, Optional, List
import logging

from .source_adapter import SourceAdapter, CalendarRef, AdapterCapabilities
from .caldav_adapter import CalDAVAdapter
from .google_adapter import GoogleAdapter


class CalendarSourceManager:
    """
    Manages calendar source adapters and provides unified access

    Automatically selects the appropriate adapter based on configuration
    and provides seamless switching between backends.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Determine source type from config
        calendar_source_config = config.get('calendar_source', {})
        self.source_type = calendar_source_config.get('type', 'caldav')  # Default to CalDAV

        # Initialize the appropriate adapter
        self.adapter = self._create_adapter()

        # Cache for calendars and capabilities
        self._calendars_cache = None
        self._capabilities_cache = None

    def _create_adapter(self) -> SourceAdapter:
        """Create the appropriate adapter based on configuration"""
        if self.source_type == 'caldav':
            self.logger.info("Initializing CalDAV/Radicale adapter")
            return CalDAVAdapter(self.config)
        elif self.source_type == 'google':
            self.logger.info("Initializing Google Calendar adapter")
            return GoogleAdapter(self.config)
        else:
            raise ValueError(f"Unknown calendar source type: {self.source_type}")

    async def get_capabilities(self) -> AdapterCapabilities:
        """Get capabilities of the current adapter"""
        if self._capabilities_cache is None:
            self._capabilities_cache = await self.adapter.capabilities()
        return self._capabilities_cache

    async def list_calendars(self) -> List[CalendarRef]:
        """List all available calendars"""
        if self._calendars_cache is None:
            self._calendars_cache = await self.adapter.list_calendars()
        return self._calendars_cache

    async def get_calendar_by_id(self, calendar_id: str) -> Optional[CalendarRef]:
        """Get specific calendar by ID"""
        calendars = await self.list_calendars()
        for calendar in calendars:
            if calendar.id == calendar_id:
                return calendar
        return None

    async def get_calendar_by_alias(self, alias: str) -> Optional[CalendarRef]:
        """Get specific calendar by alias"""
        calendars = await self.list_calendars()
        for calendar in calendars:
            if calendar.alias == alias:
                return calendar
        return None

    def get_adapter(self) -> SourceAdapter:
        """Get the underlying adapter for direct access"""
        return self.adapter

    async def validate_connection(self) -> bool:
        """Validate connection to the calendar backend"""
        try:
            return await self.adapter.validate_connection()
        except Exception as e:
            self.logger.error(f"Connection validation failed: {e}")
            return False

    async def switch_backend(self, new_type: str, new_config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Switch to a different backend

        Args:
            new_type: 'caldav' or 'google'
            new_config: Optional new configuration (uses existing if None)

        Returns:
            True if switch was successful
        """
        try:
            # Close existing adapter if it supports cleanup
            if hasattr(self.adapter, 'close'):
                await self.adapter.close()

            # Update configuration
            if new_config:
                self.config.update(new_config)

            # Update source type and create new adapter
            self.source_type = new_type
            self.config['calendar_source']['type'] = new_type

            self.adapter = self._create_adapter()

            # Clear caches
            self._calendars_cache = None
            self._capabilities_cache = None

            # Validate new connection
            if await self.validate_connection():
                self.logger.info(f"Successfully switched to {new_type} backend")
                return True
            else:
                self.logger.error(f"Failed to validate connection after switching to {new_type}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to switch backend to {new_type}: {e}")
            return False

    async def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current backend"""
        capabilities = await self.get_capabilities()
        calendars = await self.list_calendars()

        return {
            'type': self.source_type,
            'capabilities': {
                'name': capabilities.name,
                'can_write': capabilities.can_write,
                'supports_sync_token': capabilities.supports_sync_token,
                'timezone': capabilities.timezone
            },
            'calendars': [
                {
                    'id': cal.id,
                    'alias': cal.alias,
                    'read_only': cal.read_only,
                    'timezone': cal.timezone
                }
                for cal in calendars
            ],
            'connection_valid': await self.validate_connection()
        }

    async def close(self):
        """Clean up resources"""
        if hasattr(self.adapter, 'close'):
            await self.adapter.close()


class BackendSwitchError(Exception):
    """Raised when backend switching fails"""
    pass


def create_source_manager(config: Dict[str, Any]) -> CalendarSourceManager:
    """Factory function to create calendar source manager"""
    return CalendarSourceManager(config)