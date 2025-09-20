"""
CalDAV Adapter for Radicale Integration
Implements SourceAdapter interface for CalDAV/Radicale backend
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
import hashlib
import aiohttp
from icalendar import Calendar, Event as ICalEvent
from icalendar.prop import vDDDTypes

from .source_adapter import (
    SourceAdapter, CalendarRef, AdapterCapabilities, EventListResult,
    ConflictError, PermissionError, ValidationError,
    parse_datetime_with_timezone, format_datetime_for_backend
)


class CalDAVAdapter(SourceAdapter):
    """
    CalDAV/Radicale adapter implementing SourceAdapter interface

    Supports:
    - RFC 4791 CalDAV
    - RFC 6578 Sync Collection
    - Radicale-specific features
    - X-CHRONOS-* properties for idempotency
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.caldav_config = config.get('caldav', {})
        self.auth_config = self.caldav_config.get('auth', {})
        self.transport_config = self.caldav_config.get('transport', {})
        self.sync_config = self.caldav_config.get('sync', {})
        self.write_config = self.caldav_config.get('write', {})

        # Build calendar references from config
        self.calendars = []
        for cal_config in self.caldav_config.get('calendars', []):
            self.calendars.append(CalendarRef(
                id=cal_config['id'],
                alias=cal_config['alias'],
                url=cal_config['url'],
                read_only=cal_config.get('read_only', False),
                timezone=cal_config.get('timezone', 'Europe/Berlin')
            ))

        # Idempotency marker configuration
        repair_config = config.get('repair_and_enrich', {})
        idempotency_config = repair_config.get('idempotency', {})
        marker_keys = idempotency_config.get('marker_keys', {})

        self.idempotency_markers = {
            'cleaned': marker_keys.get('cleaned', 'X-CHRONOS-CLEANED'),
            'rule_id': marker_keys.get('rule_id', 'X-CHRONOS-RULE-ID'),
            'signature': marker_keys.get('signature', 'X-CHRONOS-SIGNATURE'),
            'original_summary': marker_keys.get('original_summary', 'X-CHRONOS-ORIGINAL-SUMMARY'),
            'payload': marker_keys.get('payload', 'X-CHRONOS-PAYLOAD')
        }

        # HTTP session will be created on first use
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with proper auth and timeouts"""
        if self._session is None:
            auth = None
            auth_mode = self.auth_config.get('mode', 'none')

            if auth_mode == 'basic':
                username = self.auth_config.get('username')
                password = self._resolve_password()
                if username and password:
                    auth = aiohttp.BasicAuth(username, password)

            timeout = aiohttp.ClientTimeout(
                connect=self.transport_config.get('connect_timeout_s', 5),
                total=self.transport_config.get('read_timeout_s', 15)
            )

            connector = aiohttp.TCPConnector(
                verify_ssl=self.transport_config.get('verify_tls', False)
            )

            self._session = aiohttp.ClientSession(
                auth=auth,
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'Chronos-Engine/2.1 CalDAV-Client',
                    'Content-Type': 'application/xml; charset=utf-8'
                }
            )

        return self._session

    def _resolve_password(self) -> Optional[str]:
        """Resolve password from config (supports env: prefix)"""
        password_ref = self.auth_config.get('password_ref', '')
        if password_ref.startswith('env:'):
            import os
            env_var = password_ref[4:]
            return os.getenv(env_var)
        return password_ref

    async def capabilities(self) -> AdapterCapabilities:
        """Get CalDAV adapter capabilities"""
        return AdapterCapabilities(
            name="CalDAV/Radicale",
            can_write=True,  # Most CalDAV servers support writes
            supports_sync_token=self.sync_config.get('use_sync_collection', True),
            timezone=self.caldav_config.get('timezone_default', 'Europe/Berlin')
        )

    async def list_calendars(self) -> List[CalendarRef]:
        """List configured calendars"""
        return self.calendars.copy()

    async def list_events(
        self,
        calendar: CalendarRef,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None
    ) -> EventListResult:
        """List events from CalDAV calendar"""
        session = await self._get_session()

        try:
            if sync_token and self.sync_config.get('use_sync_collection', True):
                # Use RFC 6578 sync-collection
                return await self._sync_collection_report(session, calendar, sync_token)
            else:
                # Use calendar-query with time range
                return await self._calendar_query_report(session, calendar, since, until)

        except aiohttp.ClientError as e:
            self.logger.error(f"Failed to list events from {calendar.alias}: {e}")
            return EventListResult(events=[])

    async def _sync_collection_report(
        self,
        session: aiohttp.ClientSession,
        calendar: CalendarRef,
        sync_token: str
    ) -> EventListResult:
        """Use sync-collection REPORT for incremental sync"""
        body = f'''<?xml version="1.0" encoding="utf-8" ?>
<d:sync-collection xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
  <d:sync-token>{sync_token}</d:sync-token>
  <d:sync-level>1</d:sync-level>
  <d:prop>
    <d:getetag/>
    <cal:calendar-data/>
  </d:prop>
</d:sync-collection>'''

        async with session.request(
            'REPORT', calendar.url,
            data=body,
            headers={'Depth': '1'}
        ) as response:
            if response.status == 207:  # Multi-Status
                xml_data = await response.text()
                return self._parse_multistatus_response(xml_data, calendar)
            else:
                # Fallback to calendar-query
                self.logger.warning(f"Sync collection failed with {response.status}, falling back to calendar-query")
                return await self._calendar_query_report(session, calendar, None, None)

    async def _calendar_query_report(
        self,
        session: aiohttp.ClientSession,
        calendar: CalendarRef,
        since: Optional[datetime],
        until: Optional[datetime]
    ) -> EventListResult:
        """Use calendar-query REPORT with time range"""
        # Default window if no times specified
        if not since or not until:
            window_days = self.sync_config.get('window_days', 400)
            now = datetime.now(timezone.utc)
            since = since or (now - datetime.timedelta(days=30))
            until = until or (now + datetime.timedelta(days=window_days))

        time_range = f'''
    <cal:time-range start="{since.strftime('%Y%m%dT%H%M%SZ')}"
                    end="{until.strftime('%Y%m%dT%H%M%SZ')}"/>'''

        body = f'''<?xml version="1.0" encoding="utf-8" ?>
<cal:calendar-query xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <cal:calendar-data/>
  </d:prop>
  <cal:filter>
    <cal:comp-filter name="VCALENDAR">
      <cal:comp-filter name="VEVENT">{time_range}
      </cal:comp-filter>
    </cal:comp-filter>
  </cal:filter>
</cal:calendar-query>'''

        async with session.request(
            'REPORT', calendar.url,
            data=body,
            headers={'Depth': '1'}
        ) as response:
            if response.status == 207:
                xml_data = await response.text()
                return self._parse_multistatus_response(xml_data, calendar)
            else:
                self.logger.error(f"Calendar query failed with status {response.status}")
                return EventListResult(events=[])

    def _parse_multistatus_response(self, xml_data: str, calendar: CalendarRef) -> EventListResult:
        """Parse CalDAV REPORT response"""
        events = []

        try:
            root = ET.fromstring(xml_data)

            # Define namespaces
            namespaces = {
                'd': 'DAV:',
                'cal': 'urn:ietf:params:xml:ns:caldav'
            }

            for response in root.findall('.//d:response', namespaces):
                href = response.find('d:href', namespaces)
                propstat = response.find('.//d:propstat[d:status="HTTP/1.1 200 OK"]', namespaces)

                if href is not None and propstat is not None:
                    etag_elem = propstat.find('.//d:getetag', namespaces)
                    caldata_elem = propstat.find('.//cal:calendar-data', namespaces)

                    if etag_elem is not None and caldata_elem is not None:
                        etag = etag_elem.text.strip('"')
                        ics_data = caldata_elem.text

                        try:
                            event = self._parse_ics_event(ics_data, etag, calendar)
                            if event:
                                events.append(event)
                        except Exception as e:
                            self.logger.warning(f"Failed to parse event from {href.text}: {e}")

        except ET.ParseError as e:
            self.logger.error(f"Failed to parse CalDAV response XML: {e}")

        return EventListResult(events=events)

    def _parse_ics_event(self, ics_data: str, etag: str, calendar: CalendarRef) -> Optional[Dict[str, Any]]:
        """Parse iCalendar data into normalized event"""
        try:
            cal = Calendar.from_ical(ics_data)

            for component in cal.walk():
                if component.name == "VEVENT":
                    return self._normalize_vevent(component, etag, calendar)

        except Exception as e:
            self.logger.error(f"Failed to parse iCalendar data: {e}")

        return None

    def _normalize_vevent(self, vevent: ICalEvent, etag: str, calendar: CalendarRef) -> Dict[str, Any]:
        """Normalize VEVENT component to internal format"""
        # Extract basic properties
        uid = str(vevent.get('UID', ''))
        summary = str(vevent.get('SUMMARY', ''))
        description = str(vevent.get('DESCRIPTION', ''))

        # Handle start/end times
        dtstart = vevent.get('DTSTART')
        dtend = vevent.get('DTEND')

        start_time = None
        end_time = None
        all_day = False

        if dtstart:
            if hasattr(dtstart.dt, 'date'):
                # All-day event
                all_day = True
                start_time = datetime.combine(dtstart.dt, datetime.min.time())
                if dtend:
                    # End date is exclusive in CalDAV all-day events
                    end_time = datetime.combine(dtend.dt, datetime.min.time())
                else:
                    end_time = start_time + datetime.timedelta(days=1)
            else:
                # Timed event
                start_time = dtstart.dt
                if dtend:
                    end_time = dtend.dt
                else:
                    # Default 1-hour duration
                    end_time = start_time + datetime.timedelta(hours=1)

        # Convert to UTC
        if start_time and start_time.tzinfo:
            start_time = start_time.astimezone(timezone.utc).replace(tzinfo=None)
        if end_time and end_time.tzinfo:
            end_time = end_time.astimezone(timezone.utc).replace(tzinfo=None)

        # Handle recurrence
        rrule = None
        if 'RRULE' in vevent:
            rrule = str(vevent['RRULE'])

        # Check for recurrence-id (exception/override)
        recurrence_id = None
        if 'RECURRENCE-ID' in vevent:
            rid = vevent['RECURRENCE-ID']
            if hasattr(rid.dt, 'date'):
                recurrence_id = datetime.combine(rid.dt, datetime.min.time())
            else:
                recurrence_id = rid.dt
            if recurrence_id and recurrence_id.tzinfo:
                recurrence_id = recurrence_id.astimezone(timezone.utc).replace(tzinfo=None)

        # Extract X-CHRONOS-* properties (idempotency markers)
        chronos_markers = {}
        for key, marker_name in self.idempotency_markers.items():
            if marker_name in vevent:
                chronos_markers[key] = str(vevent[marker_name])

        # Build normalized event
        event = {
            'id': uid,
            'uid': uid,
            'etag': etag,
            'summary': summary,
            'description': description,
            'start_time': start_time,
            'end_time': end_time,
            'all_day': all_day,
            'timezone': calendar.timezone,
            'calendar_id': calendar.id,
            'rrule': rrule,
            'recurrence_id': recurrence_id,
            'is_series_master': bool(rrule and not recurrence_id),
            'meta': {
                'calendar_ref': calendar,
                'chronos_markers': chronos_markers,
                'ics_data': None  # Don't store full ICS by default
            }
        }

        return event

    async def get_event(self, calendar: CalendarRef, event_id: str) -> Optional[Dict[str, Any]]:
        """Get single event by UID"""
        session = await self._get_session()

        # For CalDAV, we typically need to find the event by UID first
        # This is a simplified implementation - in practice you might want to cache href->uid mappings
        events = await self.list_events(calendar)
        for event in events.events:
            if event.get('uid') == event_id or event.get('id') == event_id:
                return event

        return None

    async def patch_event(
        self,
        calendar: CalendarRef,
        event_id: str,
        patch_data: Dict[str, Any],
        if_match_etag: Optional[str] = None
    ) -> str:
        """Patch existing event using CalDAV PUT"""
        if calendar.read_only:
            raise PermissionError(f"Calendar {calendar.alias} is read-only")

        # First, get the current event to build the patched version
        current_event = await self.get_event(calendar, event_id)
        if not current_event:
            raise ValidationError(f"Event {event_id} not found")

        # Build the patched iCalendar data
        patched_ics = self._build_ics_with_patches(current_event, patch_data)

        # Determine the href for PUT (this is simplified - real implementation needs href tracking)
        href = f"{calendar.url.rstrip('/')}/{event_id}.ics"

        session = await self._get_session()
        headers = {
            'Content-Type': 'text/calendar; charset=utf-8'
        }

        # Add If-Match header for conflict detection
        if if_match_etag and self.write_config.get('if_match', True):
            headers['If-Match'] = f'"{if_match_etag}"'

        try:
            async with session.put(href, data=patched_ics, headers=headers) as response:
                if response.status == 204:  # No Content - success
                    # Extract new ETag from response
                    new_etag = response.headers.get('ETag', '').strip('"')
                    return new_etag
                elif response.status == 412:  # Precondition Failed
                    raise ConflictError(
                        "ETag conflict during patch",
                        if_match_etag or '',
                        response.headers.get('ETag', '')
                    )
                elif response.status in (401, 403):
                    raise PermissionError(f"Permission denied: {response.status}")
                else:
                    error_text = await response.text()
                    raise ValidationError(f"PUT failed with {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            self.logger.error(f"Failed to patch event {event_id}: {e}")
            raise ValidationError(f"Network error during patch: {e}")

    def _build_ics_with_patches(self, current_event: Dict[str, Any], patch_data: Dict[str, Any]) -> str:
        """Build iCalendar data with patches applied"""
        cal = Calendar()
        cal.add('prodid', '-//Chronos Engine//CalDAV Client//EN')
        cal.add('version', '2.0')

        # Add VTIMEZONE if configured
        if self.write_config.get('include_vtimezone', True):
            # This is a simplified timezone - real implementation should use proper VTIMEZONE
            pass

        # Create VEVENT
        event = ICalEvent()

        # Apply current values with patches
        merged_data = {**current_event, **patch_data}

        event.add('uid', merged_data.get('uid', merged_data.get('id')))
        event.add('summary', merged_data.get('summary', ''))

        if merged_data.get('description'):
            event.add('description', merged_data['description'])

        # Handle datetime fields
        start_time = merged_data.get('start_time')
        end_time = merged_data.get('end_time')
        all_day = merged_data.get('all_day', False)

        if start_time:
            if all_day:
                event.add('dtstart', start_time.date())
                if end_time:
                    # End date is exclusive for all-day events
                    event.add('dtend', end_time.date())
            else:
                event.add('dtstart', start_time.replace(tzinfo=timezone.utc))
                if end_time:
                    event.add('dtend', end_time.replace(tzinfo=timezone.utc))

        # Add recurrence rule if present
        if merged_data.get('rrule'):
            event.add('rrule', merged_data['rrule'])

        # Add recurrence-id for exceptions
        if merged_data.get('recurrence_id'):
            if all_day:
                event.add('recurrence-id', merged_data['recurrence_id'].date())
            else:
                event.add('recurrence-id', merged_data['recurrence_id'].replace(tzinfo=timezone.utc))

        # Add X-CHRONOS-* properties from patch_data
        chronos_markers = patch_data.get('chronos_markers', {})
        for key, marker_name in self.idempotency_markers.items():
            if key in chronos_markers:
                event.add(marker_name, chronos_markers[key])

        cal.add_component(event)
        return cal.to_ical().decode('utf-8')

    async def create_override(
        self,
        calendar: CalendarRef,
        master_id: str,
        recurrence_id: datetime,
        patch_data: Dict[str, Any]
    ) -> str:
        """Create recurrence exception"""
        # Get master event first
        master_event = await self.get_event(calendar, master_id)
        if not master_event:
            raise ValidationError(f"Master event {master_id} not found")

        # Create override with recurrence-id
        override_data = {**master_event, **patch_data}
        override_data['recurrence_id'] = recurrence_id
        override_data['is_series_master'] = False

        # Generate new UID for the override
        override_uid = f"{master_id}-override-{recurrence_id.strftime('%Y%m%dT%H%M%S')}"
        override_data['uid'] = override_uid
        override_data['id'] = override_uid

        # Create the override event
        override_ics = self._build_ics_with_patches({}, override_data)
        href = f"{calendar.url.rstrip('/')}/{override_uid}.ics"

        session = await self._get_session()
        headers = {'Content-Type': 'text/calendar; charset=utf-8'}

        async with session.put(href, data=override_ics, headers=headers) as response:
            if response.status == 201:  # Created
                return override_uid
            else:
                error_text = await response.text()
                raise ValidationError(f"Failed to create override: {response.status} {error_text}")

    async def get_series_master(self, calendar: CalendarRef, event_id: str) -> Optional[Dict[str, Any]]:
        """Get master event for recurring series"""
        event = await self.get_event(calendar, event_id)
        if not event:
            return None

        if event.get('is_series_master'):
            return event

        # If this is an exception, find the master by pattern matching
        # This is simplified - real implementation might need more sophisticated logic
        uid_base = event.get('uid', '').split('-override-')[0]
        return await self.get_event(calendar, uid_base)

    def extract_idempotency_markers(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Chronos idempotency markers from CalDAV event"""
        meta = event.get('meta', {})
        return meta.get('chronos_markers', {})

    def inject_idempotency_markers(self, event: Dict[str, Any], markers: Dict[str, Any]) -> Dict[str, Any]:
        """Inject Chronos idempotency markers into CalDAV event"""
        if 'meta' not in event:
            event['meta'] = {}
        event['meta']['chronos_markers'] = markers
        return event

    async def create_event(self, calendar: CalendarRef, event_data: Dict[str, Any]) -> str:
        """Create new event in CalDAV calendar"""
        if calendar.read_only:
            raise PermissionError(f"Calendar {calendar.alias} is read-only")

        try:
            # Generate UID if not provided
            event_uid = event_data.get('uid') or event_data.get('id') or self._generate_uid()

            # Build iCalendar content
            ics_content = self._build_ics_from_event_data(event_data, event_uid)

            # PUT to CalDAV server
            href = f"{calendar.url.rstrip('/')}/{event_uid}.ics"
            session = await self._get_session()
            headers = {'Content-Type': 'text/calendar; charset=utf-8'}

            async with session.put(href, data=ics_content, headers=headers) as response:
                if response.status in [201, 204]:  # Created or No Content
                    self.logger.info(f"Created event {event_uid} in calendar {calendar.alias}")
                    return event_uid
                else:
                    error_text = await response.text()
                    raise ValidationError(f"Failed to create event: {response.status} {error_text}")

        except Exception as e:
            self.logger.error(f"Failed to create event in CalDAV calendar {calendar.alias}: {e}")
            raise ValidationError(f"Failed to create CalDAV event: {e}")

    async def delete_event(self, calendar: CalendarRef, event_id: str) -> bool:
        """Delete event from CalDAV calendar"""
        if calendar.read_only:
            raise PermissionError(f"Calendar {calendar.alias} is read-only")

        try:
            # DELETE from CalDAV server
            href = f"{calendar.url.rstrip('/')}/{event_id}.ics"
            session = await self._get_session()

            async with session.delete(href) as response:
                if response.status in [200, 204, 404]:  # OK, No Content, or Not Found (already deleted)
                    self.logger.info(f"Deleted event {event_id} from calendar {calendar.alias}")
                    return True
                else:
                    error_text = await response.text()
                    self.logger.warning(f"Failed to delete event {event_id}: {response.status} {error_text}")
                    return False

        except Exception as e:
            self.logger.error(f"Failed to delete event {event_id} from CalDAV calendar {calendar.alias}: {e}")
            return False

    def _build_ics_from_event_data(self, event_data: Dict[str, Any], uid: str) -> str:
        """Build iCalendar content from normalized event data"""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Chronos//CalDAV Adapter//EN",
            "BEGIN:VEVENT"
        ]

        # Add UID
        lines.append(f"UID:{uid}")

        # Add summary
        summary = event_data.get('summary', 'Untitled Event')
        lines.append(f"SUMMARY:{summary}")

        # Add description if present
        description = event_data.get('description', '')
        if description:
            # Escape special characters in description
            description = description.replace('\\', '\\\\').replace('\n', '\\n').replace(',', '\\,').replace(';', '\\;')
            lines.append(f"DESCRIPTION:{description}")

        # Add start/end times
        start_time = event_data.get('start_time')
        end_time = event_data.get('end_time')
        all_day = event_data.get('all_day', False)

        if start_time:
            if all_day:
                lines.append(f"DTSTART;VALUE=DATE:{start_time.strftime('%Y%m%d')}")
                if end_time:
                    lines.append(f"DTEND;VALUE=DATE:{end_time.strftime('%Y%m%d')}")
            else:
                lines.append(f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}")
                if end_time:
                    lines.append(f"DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}")

        # Add recurrence rule if present
        rrule = event_data.get('rrule')
        if rrule:
            lines.append(f"RRULE:{rrule}")

        # Add recurrence-id if this is an exception
        recurrence_id = event_data.get('recurrence_id')
        if recurrence_id:
            if all_day:
                lines.append(f"RECURRENCE-ID;VALUE=DATE:{recurrence_id.strftime('%Y%m%d')}")
            else:
                lines.append(f"RECURRENCE-ID:{recurrence_id.strftime('%Y%m%dT%H%M%SZ')}")

        # Add Chronos idempotency markers
        chronos_markers = event_data.get('chronos_markers', {})
        if chronos_markers:
            for key, value in chronos_markers.items():
                marker_key = self.config.get('repair_and_enrich', {}).get('idempotency', {}).get('marker_keys', {}).get(key, f'X-CHRONOS-{key.upper()}')
                lines.append(f"{marker_key}:{value}")

        # Add timestamp
        lines.append(f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}")

        lines.extend([
            "END:VEVENT",
            "END:VCALENDAR"
        ])

        return '\r\n'.join(lines)

    def _generate_uid(self) -> str:
        """Generate unique identifier for new events"""
        import uuid
        return str(uuid.uuid4())

    async def close(self):
        """Close HTTP session"""
        if self._session:
            await self._session.close()
            self._session = None