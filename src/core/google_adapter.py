"""
Google Calendar Adapter implementing SourceAdapter interface
Refactored from existing GoogleCalendarClient to use unified interface
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json

from .source_adapter import (
    SourceAdapter, CalendarRef, AdapterCapabilities, EventListResult,
    ConflictError, PermissionError, ValidationError
)
from .calendar_client import GoogleCalendarClient


class GoogleAdapter(SourceAdapter):
    """
    Google Calendar adapter implementing SourceAdapter interface

    Wraps the existing GoogleCalendarClient to provide unified access
    alongside CalDAV backends.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.google_config = config.get('google', {})
        self.enabled = self.google_config.get('enabled', False)

        # Initialize underlying Google Calendar client
        self.client = None
        if self.enabled:
            credentials_file = self.google_config.get('credentials_file', 'config/credentials.json')
            token_file = self.google_config.get('token_file', 'config/token.json')
            self.client = GoogleCalendarClient(credentials_file, token_file)

        # Build calendar references from config
        self.calendars = []
        calendar_ids = self.google_config.get('calendar_ids', ['primary'])

        for cal_id in calendar_ids:
            if isinstance(cal_id, str):
                # Simple string calendar ID
                self.calendars.append(CalendarRef(
                    id=cal_id,
                    alias=cal_id.title() if cal_id != 'primary' else 'Primary',
                    url=cal_id,  # For Google, URL is the calendar ID
                    read_only=False,
                    timezone=self.google_config.get('timezone', 'UTC')
                ))
            elif isinstance(cal_id, dict):
                # Detailed calendar configuration
                self.calendars.append(CalendarRef(
                    id=cal_id['id'],
                    alias=cal_id.get('alias', cal_id['id']),
                    url=cal_id['id'],
                    read_only=cal_id.get('read_only', False),
                    timezone=cal_id.get('timezone', 'UTC')
                ))

    async def capabilities(self) -> AdapterCapabilities:
        """Get Google Calendar adapter capabilities"""
        return AdapterCapabilities(
            name="Google Calendar",
            can_write=self.enabled and self.client is not None,
            supports_sync_token=True,  # Google Calendar supports sync tokens
            timezone=self.google_config.get('timezone', 'UTC')
        )

    async def list_calendars(self) -> List[CalendarRef]:
        """List configured Google calendars"""
        if not self.enabled:
            return []
        return self.calendars.copy()

    async def list_events(
        self,
        calendar: CalendarRef,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None
    ) -> EventListResult:
        """List events from Google Calendar"""
        if not self.enabled or not self.client:
            return EventListResult(events=[])

        try:
            # Use existing GoogleCalendarClient method
            raw_events = await self.client.fetch_events(
                calendar_id=calendar.url,  # For Google, url is the calendar ID
                days_ahead=None,  # Will use since/until instead
                since=since,
                until=until,
                page_token=page_token,
                sync_token=sync_token
            )

            # Normalize Google events to internal format
            normalized_events = []
            for event in raw_events:
                normalized = self._normalize_google_event(event, calendar)
                if normalized:
                    normalized_events.append(normalized)

            return EventListResult(
                events=normalized_events,
                next_page_token=None,  # TODO: Extract from Google response
                sync_token=None       # TODO: Extract from Google response
            )

        except Exception as e:
            self.logger.error(f"Failed to list events from Google calendar {calendar.alias}: {e}")
            return EventListResult(events=[])

    def _normalize_google_event(self, google_event: Dict[str, Any], calendar: CalendarRef) -> Optional[Dict[str, Any]]:
        """Normalize Google Calendar event to internal format"""
        try:
            event_id = google_event.get('id', '')
            summary = google_event.get('summary', '')
            description = google_event.get('description', '')

            # Handle start/end times
            start = google_event.get('start', {})
            end = google_event.get('end', {})

            start_time = None
            end_time = None
            all_day = False

            # Google Calendar uses different fields for all-day vs timed events
            if 'date' in start:
                # All-day event
                all_day = True
                start_time = datetime.fromisoformat(start['date']).replace(tzinfo=None)
                if 'date' in end:
                    end_time = datetime.fromisoformat(end['date']).replace(tzinfo=None)
            else:
                # Timed event
                start_dt_str = start.get('dateTime', '')
                end_dt_str = end.get('dateTime', '')

                if start_dt_str:
                    start_time = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00'))
                    if start_time.tzinfo:
                        start_time = start_time.astimezone(timezone.utc).replace(tzinfo=None)

                if end_dt_str:
                    end_time = datetime.fromisoformat(end_dt_str.replace('Z', '+00:00'))
                    if end_time.tzinfo:
                        end_time = end_time.astimezone(timezone.utc).replace(tzinfo=None)

            # Handle recurrence
            rrule = None
            recurrence = google_event.get('recurrence', [])
            if recurrence:
                # Google provides RRULE in a list
                for rule in recurrence:
                    if rule.startswith('RRULE:'):
                        rrule = rule[6:]  # Remove 'RRULE:' prefix
                        break

            # Check for recurring event instance
            recurrence_id = None
            recurring_event_id = google_event.get('recurringEventId')
            if recurring_event_id:
                # This is an instance of a recurring event
                # Google doesn't provide recurrence-id directly, but we can infer it
                original_start_time = google_event.get('originalStartTime', {})
                if 'dateTime' in original_start_time:
                    recurrence_id = datetime.fromisoformat(
                        original_start_time['dateTime'].replace('Z', '+00:00')
                    )
                    if recurrence_id.tzinfo:
                        recurrence_id = recurrence_id.astimezone(timezone.utc).replace(tzinfo=None)
                elif 'date' in original_start_time:
                    recurrence_id = datetime.fromisoformat(original_start_time['date']).replace(tzinfo=None)

            # Extract Google-specific idempotency markers
            extended_props = google_event.get('extendedProperties', {})
            private_props = extended_props.get('private', {})

            chronos_markers = {}
            # Map Google extended properties to internal markers
            if 'chronos.cleaned' in private_props:
                chronos_markers['cleaned'] = private_props['chronos.cleaned']
            if 'chronos.rule_id' in private_props:
                chronos_markers['rule_id'] = private_props['chronos.rule_id']
            if 'chronos.signature' in private_props:
                chronos_markers['signature'] = private_props['chronos.signature']
            if 'chronos.original_summary' in private_props:
                chronos_markers['original_summary'] = private_props['chronos.original_summary']
            if 'chronos.payload' in private_props:
                chronos_markers['payload'] = private_props['chronos.payload']

            # Build normalized event
            event = {
                'id': event_id,
                'uid': event_id,  # Google uses ID as UID
                'etag': google_event.get('etag', ''),
                'summary': summary,
                'description': description,
                'start_time': start_time,
                'end_time': end_time,
                'all_day': all_day,
                'timezone': start.get('timeZone') or calendar.timezone,
                'calendar_id': calendar.id,
                'rrule': rrule,
                'recurrence_id': recurrence_id,
                'is_series_master': bool(rrule and not recurring_event_id),
                'meta': {
                    'calendar_ref': calendar,
                    'chronos_markers': chronos_markers,
                    'google_data': google_event  # Keep original for reference
                }
            }

            return event

        except Exception as e:
            self.logger.error(f"Failed to normalize Google event {google_event.get('id')}: {e}")
            return None

    async def get_event(self, calendar: CalendarRef, event_id: str) -> Optional[Dict[str, Any]]:
        """Get single event from Google Calendar"""
        if not self.enabled or not self.client:
            return None

        try:
            # Use underlying client to get event
            google_event = await self.client.get_event(calendar.url, event_id)
            if google_event:
                return self._normalize_google_event(google_event, calendar)

        except Exception as e:
            self.logger.error(f"Failed to get Google event {event_id}: {e}")

        return None

    async def patch_event(
        self,
        calendar: CalendarRef,
        event_id: str,
        patch_data: Dict[str, Any],
        if_match_etag: Optional[str] = None
    ) -> str:
        """Patch existing Google Calendar event"""
        if not self.enabled or not self.client:
            raise PermissionError("Google Calendar adapter not enabled")

        if calendar.read_only:
            raise PermissionError(f"Calendar {calendar.alias} is read-only")

        try:
            # Convert internal patch format to Google Calendar format
            google_patch = self._convert_to_google_patch(patch_data)

            # Add idempotency markers if present
            chronos_markers = patch_data.get('chronos_markers', {})
            if chronos_markers:
                if 'extendedProperties' not in google_patch:
                    google_patch['extendedProperties'] = {'private': {}}

                private_props = google_patch['extendedProperties']['private']

                # Map internal markers to Google extended properties
                if 'cleaned' in chronos_markers:
                    private_props['chronos.cleaned'] = chronos_markers['cleaned']
                if 'rule_id' in chronos_markers:
                    private_props['chronos.rule_id'] = chronos_markers['rule_id']
                if 'signature' in chronos_markers:
                    private_props['chronos.signature'] = chronos_markers['signature']
                if 'original_summary' in chronos_markers:
                    private_props['chronos.original_summary'] = chronos_markers['original_summary']
                if 'payload' in chronos_markers:
                    private_props['chronos.payload'] = chronos_markers['payload']

            # Use existing client patch method
            headers = {}
            if if_match_etag:
                headers['If-Match'] = if_match_etag

            updated_event = await self.client.patch_event(
                calendar_id=calendar.url,
                event_id=event_id,
                event_data=google_patch,
                send_updates='none',  # Don't send email notifications
                headers=headers
            )

            return updated_event.get('etag', '')

        except Exception as e:
            # Handle Google-specific errors
            if '412' in str(e):  # Precondition Failed
                raise ConflictError(
                    "ETag conflict during patch",
                    if_match_etag or '',
                    ''  # Google doesn't provide current ETag in error
                )
            elif 'permission' in str(e).lower() or '403' in str(e):
                raise PermissionError(f"Permission denied: {e}")
            else:
                raise ValidationError(f"Failed to patch Google event: {e}")

    def _convert_to_google_patch(self, patch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert internal patch format to Google Calendar format"""
        google_patch = {}

        # Map basic fields
        if 'summary' in patch_data:
            google_patch['summary'] = patch_data['summary']
        if 'description' in patch_data:
            google_patch['description'] = patch_data['description']

        # Handle datetime fields
        if 'start_time' in patch_data or 'end_time' in patch_data:
            start_time = patch_data.get('start_time')
            end_time = patch_data.get('end_time')
            all_day = patch_data.get('all_day', False)

            if start_time:
                if all_day:
                    google_patch['start'] = {'date': start_time.strftime('%Y-%m-%d')}
                else:
                    google_patch['start'] = {'dateTime': start_time.isoformat() + 'Z'}

            if end_time:
                if all_day:
                    google_patch['end'] = {'date': end_time.strftime('%Y-%m-%d')}
                else:
                    google_patch['end'] = {'dateTime': end_time.isoformat() + 'Z'}

        # Handle recurrence
        if 'rrule' in patch_data:
            rrule = patch_data['rrule']
            if rrule:
                google_patch['recurrence'] = [f'RRULE:{rrule}']
            else:
                google_patch['recurrence'] = []

        return google_patch

    async def create_override(
        self,
        calendar: CalendarRef,
        master_id: str,
        recurrence_id: datetime,
        patch_data: Dict[str, Any]
    ) -> str:
        """Create recurrence exception in Google Calendar"""
        if not self.enabled or not self.client:
            raise PermissionError("Google Calendar adapter not enabled")

        # Get master event first
        master_event = await self.get_event(calendar, master_id)
        if not master_event:
            raise ValidationError(f"Master event {master_id} not found")

        # Create exception data
        exception_data = self._convert_to_google_patch(patch_data)
        exception_data['recurringEventId'] = master_id

        # Set original start time for the exception
        if patch_data.get('all_day'):
            exception_data['originalStartTime'] = {'date': recurrence_id.strftime('%Y-%m-%d')}
        else:
            exception_data['originalStartTime'] = {'dateTime': recurrence_id.isoformat() + 'Z'}

        try:
            # Create the exception using Google Calendar API
            created_event = await self.client.create_event(calendar.url, exception_data)
            return created_event.get('id', '')

        except Exception as e:
            raise ValidationError(f"Failed to create Google Calendar exception: {e}")

    async def get_series_master(self, calendar: CalendarRef, event_id: str) -> Optional[Dict[str, Any]]:
        """Get master event for recurring series"""
        event = await self.get_event(calendar, event_id)
        if not event:
            return None

        if event.get('is_series_master'):
            return event

        # If this is an instance, get the master by recurringEventId
        google_data = event.get('meta', {}).get('google_data', {})
        recurring_event_id = google_data.get('recurringEventId')

        if recurring_event_id:
            return await self.get_event(calendar, recurring_event_id)

        return None

    def extract_idempotency_markers(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Chronos idempotency markers from Google event"""
        meta = event.get('meta', {})
        return meta.get('chronos_markers', {})

    def inject_idempotency_markers(self, event: Dict[str, Any], markers: Dict[str, Any]) -> Dict[str, Any]:
        """Inject Chronos idempotency markers into Google event"""
        if 'meta' not in event:
            event['meta'] = {}
        event['meta']['chronos_markers'] = markers
        return event

    async def create_event(self, calendar: CalendarRef, event_data: Dict[str, Any]) -> str:
        """Create new event in Google Calendar"""
        if not self.enabled or not self.client:
            raise PermissionError("Google Calendar adapter not enabled")

        if calendar.read_only:
            raise PermissionError(f"Calendar {calendar.alias} is read-only")

        try:
            # Convert normalized event data to Google Calendar format
            google_event = self._convert_to_google_event(event_data)

            # Add idempotency markers if present
            chronos_markers = event_data.get('chronos_markers', {})
            if chronos_markers:
                if 'extendedProperties' not in google_event:
                    google_event['extendedProperties'] = {'private': {}}

                private_props = google_event['extendedProperties']['private']

                # Map internal markers to Google extended properties
                if 'cleaned' in chronos_markers:
                    private_props['chronos.cleaned'] = chronos_markers['cleaned']
                if 'rule_id' in chronos_markers:
                    private_props['chronos.rule_id'] = chronos_markers['rule_id']
                if 'signature' in chronos_markers:
                    private_props['chronos.signature'] = chronos_markers['signature']
                if 'original_summary' in chronos_markers:
                    private_props['chronos.original_summary'] = chronos_markers['original_summary']
                if 'payload' in chronos_markers:
                    private_props['chronos.payload'] = chronos_markers['payload']

            # Create event using Google Calendar API
            created_event = await self.client.create_event(calendar.url, google_event)
            event_id = created_event.get('id', '')

            self.logger.info(f"Created event {event_id} in Google Calendar {calendar.alias}")
            return event_id

        except Exception as e:
            self.logger.error(f"Failed to create event in Google Calendar {calendar.alias}: {e}")
            raise ValidationError(f"Failed to create Google Calendar event: {e}")

    async def delete_event(self, calendar: CalendarRef, event_id: str) -> bool:
        """Delete event from Google Calendar"""
        if not self.enabled or not self.client:
            raise PermissionError("Google Calendar adapter not enabled")

        if calendar.read_only:
            raise PermissionError(f"Calendar {calendar.alias} is read-only")

        try:
            await self.client.delete_event(event_id, calendar_id=calendar.url)
            self.logger.info(f"Deleted event {event_id} from Google Calendar {calendar.alias}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete event {event_id} from Google Calendar {calendar.alias}: {e}")
            return False

    def _convert_to_google_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert normalized event data to Google Calendar format"""
        google_event = {}

        # Map basic fields
        if 'summary' in event_data:
            google_event['summary'] = event_data['summary']
        if 'description' in event_data:
            google_event['description'] = event_data['description']

        # Handle datetime fields
        start_time = event_data.get('start_time')
        end_time = event_data.get('end_time')
        all_day = event_data.get('all_day', False)

        if start_time:
            if all_day:
                google_event['start'] = {'date': start_time.strftime('%Y-%m-%d')}
            else:
                google_event['start'] = {'dateTime': start_time.isoformat() + 'Z'}

        if end_time:
            if all_day:
                google_event['end'] = {'date': end_time.strftime('%Y-%m-%d')}
            else:
                google_event['end'] = {'dateTime': end_time.isoformat() + 'Z'}

        # Handle recurrence
        rrule = event_data.get('rrule')
        if rrule:
            google_event['recurrence'] = [f'RRULE:{rrule}']

        # Handle recurrence exceptions
        recurrence_id = event_data.get('recurrence_id')
        if recurrence_id:
            # This would be a recurrence exception
            if all_day:
                google_event['originalStartTime'] = {'date': recurrence_id.strftime('%Y-%m-%d')}
            else:
                google_event['originalStartTime'] = {'dateTime': recurrence_id.isoformat() + 'Z'}

        return google_event

    async def validate_connection(self) -> bool:
        """Test Google Calendar connection"""
        if not self.enabled or not self.client:
            return False

        try:
            # Try to list calendars as a connection test
            await self.client.list_calendars()
            return True
        except Exception as e:
            self.logger.error(f"Google Calendar connection validation failed: {e}")
            return False