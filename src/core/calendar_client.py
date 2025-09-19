"""Simplified Google Calendar client for testing and offline development.

The original implementation attempted to talk to the real Google Calendar
API.  For the unit tests in this kata we only need a deterministic in-memory
behaviour that mimics the parts of the API we use.  This module therefore
provides a lightweight client that stores events in memory and exposes the
minimal surface used by the tests.
"""

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.mock_calendar import MockCalendarService, MockCredentials


class GoogleCalendarClient:
    """Mockable Google Calendar client backed by an in-memory store."""

    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.logger = logging.getLogger(__name__)

        # Reuse the existing mock calendar service to generate realistic data
        mock_service = MockCalendarService(MockCredentials({}))
        self._initial_events = deepcopy(mock_service.events_db)
        self._events: List[Dict[str, Any]] = deepcopy(self._initial_events)

        self._authenticated = False

    async def authenticate(self) -> bool:
        """Pretend to authenticate with Google Calendar."""
        self._authenticated = True
        self.logger.debug("Mock Google Calendar authentication successful")
        return True

    async def _ensure_authenticated(self) -> None:
        if not self._authenticated:
            await self.authenticate()

    def reset_mock_events(self) -> None:
        """Reset the in-memory events to the initial sample data."""
        self._events = deepcopy(self._initial_events)

    def get_mock_event_count(self) -> int:
        """Return the number of mock events currently stored."""
        return len(self._events)

    def _parse_event_start(self, event: Dict[str, Any]) -> Optional[datetime]:
        start_info = event.get('start') or {}
        dt_str = start_info.get('dateTime') or start_info.get('date')
        if not dt_str:
            return None

        # Normalise to aware UTC datetimes for comparison
        if 'T' in dt_str:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return datetime.fromisoformat(dt_str)  # All-day events

    async def fetch_events(
        self,
        calendar_id: str = 'primary',
        days_ahead: int = 7,
        max_results: int = 250
    ) -> List[Dict[str, Any]]:
        """Return events from the in-memory store with optional filtering."""

        await self._ensure_authenticated()

        if days_ahead is not None:
            window_start = datetime.utcnow()
            window_end = window_start + timedelta(days=days_ahead)

            def within_window(event: Dict[str, Any]) -> bool:
                start_time = self._parse_event_start(event)
                if not start_time:
                    return True
                # `start_time` may be aware if it includes timezone information.
                if start_time.tzinfo is not None:
                    start_time = start_time.astimezone(tz=None).replace(tzinfo=None)
                return window_start <= start_time <= window_end

            filtered = [event for event in self._events if within_window(event)]
        else:
            filtered = list(self._events)

        return deepcopy(filtered[:max_results])

    async def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new event to the in-memory store."""

        await self._ensure_authenticated()

        event = deepcopy(event_data)
        event.setdefault('summary', 'New Event')
        event.setdefault('description', '')
        event.setdefault('start', {})
        event.setdefault('end', {})
        event['id'] = event.get('id') or f"mock_{uuid.uuid4().hex}"
        event['created'] = datetime.utcnow().isoformat() + 'Z'
        event['updated'] = event['created']

        self._events.append(event)
        self.logger.debug("Created mock calendar event %s", event['id'])
        return deepcopy(event)

    async def update_event(
        self,
        event_id: str,
        event_data: Dict[str, Any],
        calendar_id: str = 'primary'
    ) -> Dict[str, Any]:
        """Update an existing event in the mock store."""

        await self._ensure_authenticated()

        for stored_event in self._events:
            if stored_event['id'] == event_id:
                stored_event.update(deepcopy(event_data))
                stored_event['id'] = event_id  # Ensure ID is preserved
                stored_event['updated'] = datetime.utcnow().isoformat() + 'Z'
                self.logger.debug("Updated mock calendar event %s", event_id)
                return deepcopy(stored_event)

        raise KeyError(f"Event {event_id} not found")

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = 'primary'
    ) -> bool:
        """Remove an event from the mock store."""

        await self._ensure_authenticated()

        for index, stored_event in enumerate(self._events):
            if stored_event['id'] == event_id:
                del self._events[index]
                self.logger.debug("Deleted mock calendar event %s", event_id)
                return True

        # Deleting a non-existent event is treated as success in the tests
        return True

    async def get_calendar_list(self) -> List[Dict[str, Any]]:
        """Return a static list of mock calendars."""

        await self._ensure_authenticated()
        return [{'id': 'primary', 'summary': 'Mock Calendar'}]

    async def health_check(self) -> Dict[str, Any]:
        """Return a simple health-check payload."""

        await self._ensure_authenticated()
        return {
            'status': 'healthy',
            'auth_mode': 'mock',
            'credentials_file_exists': self.credentials_file.exists(),
            'token_file_exists': self.token_file.exists(),
            'events_cached': len(self._events)
        }
