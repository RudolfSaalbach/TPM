"""
Unit Tests for CalDAVAdapter
Tests the core CalDAV adapter functionality including event normalization, iCalendar parsing, and HTTP operations.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import aiohttp
from typing import Dict, Any, List

from src.core.caldav_adapter import CalDAVAdapter
from src.core.source_adapter import CalendarRef, AdapterCapabilities, EventListResult, ConflictError, PermissionError


@pytest.fixture
def minimal_config():
    """Minimal configuration for CalDAV adapter"""
    return {
        'calendar_source': {'type': 'caldav'},
        'caldav': {
            'calendars': [
                {
                    'id': 'test-cal',
                    'alias': 'Test Calendar',
                    'url': 'http://radicale.test:5232/user/collection/',
                    'read_only': False,
                    'timezone': 'Europe/Berlin'
                }
            ],
            'auth': {
                'mode': 'basic',
                'username': 'testuser',
                'password_ref': 'env:TEST_PASSWORD'
            },
            'transport': {
                'verify_tls': False,
                'connect_timeout_s': 5,
                'read_timeout_s': 15
            },
            'sync': {
                'use_sync_collection': True,
                'window_days': 400,
                'parallel_requests': 3
            },
            'write': {
                'if_match': True,
                'retry_conflict': 1,
                'include_vtimezone': True
            }
        },
        'repair_and_enrich': {
            'idempotency': {
                'marker_keys': {
                    'cleaned': 'X-CHRONOS-CLEANED',
                    'rule_id': 'X-CHRONOS-RULE-ID',
                    'signature': 'X-CHRONOS-SIGNATURE',
                    'original_summary': 'X-CHRONOS-ORIGINAL-SUMMARY',
                    'payload': 'X-CHRONOS-PAYLOAD'
                }
            }
        }
    }


class TestCalDAVAdapterCore:
    """Core CalDAVAdapter functionality tests"""

    @pytest.fixture
    def caldav_adapter(self, minimal_config):
        """Create CalDAVAdapter instance"""
        return CalDAVAdapter(minimal_config)

    @pytest.fixture
    def test_calendar_ref(self):
        """Test calendar reference"""
        return CalendarRef(
            id='test-cal',
            alias='Test Calendar',
            url='http://radicale.test:5232/user/collection/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    def test_adapter_initialization(self, caldav_adapter, minimal_config):
        """Test adapter initializes with correct configuration"""
        assert caldav_adapter.enabled == True
        assert caldav_adapter.auth_mode == 'basic'
        assert caldav_adapter.username == 'testuser'
        assert caldav_adapter.verify_tls == False
        assert caldav_adapter.use_sync_collection == True
        assert caldav_adapter.if_match == True
        assert len(caldav_adapter.calendars) == 1

    @pytest.mark.asyncio
    async def test_capabilities(self, caldav_adapter):
        """Test adapter capabilities reporting"""
        capabilities = await caldav_adapter.capabilities()

        assert isinstance(capabilities, AdapterCapabilities)
        assert capabilities.name == "CalDAV/Radicale"
        assert capabilities.can_write == True
        assert capabilities.supports_sync_token == True
        assert capabilities.timezone == "Europe/Berlin"

    @pytest.mark.asyncio
    async def test_list_calendars(self, caldav_adapter):
        """Test calendar listing"""
        calendars = await caldav_adapter.list_calendars()

        assert len(calendars) == 1
        calendar = calendars[0]
        assert calendar.id == 'test-cal'
        assert calendar.alias == 'Test Calendar'
        assert calendar.read_only == False
        assert calendar.timezone == 'Europe/Berlin'

    def test_session_creation(self, caldav_adapter):
        """Test HTTP session creation with proper authentication"""
        with patch.dict('os.environ', {'TEST_PASSWORD': 'secret123'}):
            session = caldav_adapter._create_session()

            assert isinstance(session, aiohttp.ClientSession)
            # Session should have proper timeout and auth configured


class TestCalDAVEventNormalization:
    """Test event normalization and iCalendar parsing"""

    @pytest.fixture
    def caldav_adapter(self, minimal_config):
        return CalDAVAdapter(minimal_config)

    @pytest.fixture
    def test_calendar_ref(self):
        return CalendarRef(
            id='test-cal',
            alias='Test Calendar',
            url='http://radicale.test:5232/user/collection/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    def test_normalize_simple_event(self, caldav_adapter, test_calendar_ref):
        """Test normalization of simple timed event"""
        # Mock iCalendar event
        mock_vevent = Mock()
        mock_vevent.get.side_effect = lambda key, default=None: {
            'UID': 'simple-event-123',
            'SUMMARY': 'Simple Meeting',
            'DESCRIPTION': 'A simple test meeting',
            'DTSTART': Mock(dt=datetime(2025, 1, 15, 14, 0)),
            'DTEND': Mock(dt=datetime(2025, 1, 15, 15, 30)),
            'RRULE': None,
            'RECURRENCE-ID': None
        }.get(key, default)

        mock_vevent.has_key = lambda key: key in ['UID', 'SUMMARY', 'DESCRIPTION', 'DTSTART', 'DTEND']

        normalized = caldav_adapter._normalize_vevent(mock_vevent, '"etag-123"', test_calendar_ref)

        assert normalized['id'] == 'simple-event-123'
        assert normalized['uid'] == 'simple-event-123'
        assert normalized['summary'] == 'Simple Meeting'
        assert normalized['description'] == 'A simple test meeting'
        assert normalized['start_time'] == datetime(2025, 1, 15, 14, 0)
        assert normalized['end_time'] == datetime(2025, 1, 15, 15, 30)
        assert normalized['all_day'] == False
        assert normalized['calendar_id'] == 'test-cal'
        assert normalized['etag'] == '"etag-123"'
        assert normalized['rrule'] is None
        assert normalized['recurrence_id'] is None
        assert normalized['is_series_master'] == False

    def test_normalize_all_day_event(self, caldav_adapter, test_calendar_ref):
        """Test normalization of all-day event"""
        from datetime import date
        mock_vevent = Mock()
        mock_vevent.get.side_effect = lambda key, default=None: {
            'UID': 'allday-event-456',
            'SUMMARY': 'All Day Event',
            'DTSTART': Mock(dt=date(2025, 1, 15)),
            'DTEND': Mock(dt=date(2025, 1, 16))
        }.get(key, default)

        mock_vevent.has_key = lambda key: key in ['UID', 'SUMMARY', 'DTSTART', 'DTEND']

        # Mock all-day detection
        mock_vevent.get('DTSTART').params = {}  # No time specified

        normalized = caldav_adapter._normalize_vevent(mock_vevent, '"etag-456"', test_calendar_ref)

        assert normalized['all_day'] == True
        assert normalized['start_time'] == datetime(2025, 1, 15)
        assert normalized['end_time'] == datetime(2025, 1, 16)

    def test_normalize_recurring_event(self, caldav_adapter, test_calendar_ref):
        """Test normalization of recurring event"""
        mock_vevent = Mock()
        mock_vevent.get.side_effect = lambda key, default=None: {
            'UID': 'recurring-event-789',
            'SUMMARY': 'Weekly Meeting',
            'DTSTART': Mock(dt=datetime(2025, 1, 15, 10, 0)),
            'DTEND': Mock(dt=datetime(2025, 1, 15, 11, 0)),
            'RRULE': Mock(to_ical=lambda: b'FREQ=WEEKLY;BYDAY=WE')
        }.get(key, default)

        mock_vevent.has_key = lambda key: key in ['UID', 'SUMMARY', 'DTSTART', 'DTEND', 'RRULE']

        normalized = caldav_adapter._normalize_vevent(mock_vevent, '"etag-789"', test_calendar_ref)

        assert normalized['rrule'] == 'FREQ=WEEKLY;BYDAY=WE'
        assert normalized['is_series_master'] == True
        assert normalized['recurrence_id'] is None

    def test_normalize_recurrence_exception(self, caldav_adapter, test_calendar_ref):
        """Test normalization of recurrence exception"""
        mock_vevent = Mock()
        mock_vevent.get.side_effect = lambda key, default=None: {
            'UID': 'recurring-event-789',
            'SUMMARY': 'Weekly Meeting - Moved',
            'DTSTART': Mock(dt=datetime(2025, 1, 22, 14, 0)),  # Different time
            'DTEND': Mock(dt=datetime(2025, 1, 22, 15, 0)),
            'RECURRENCE-ID': Mock(dt=datetime(2025, 1, 22, 10, 0))  # Original time
        }.get(key, default)

        mock_vevent.has_key = lambda key: key in ['UID', 'SUMMARY', 'DTSTART', 'DTEND', 'RECURRENCE-ID']

        normalized = caldav_adapter._normalize_vevent(mock_vevent, '"etag-exception"', test_calendar_ref)

        assert normalized['recurrence_id'] == datetime(2025, 1, 22, 10, 0)
        assert normalized['is_series_master'] == False
        assert normalized['summary'] == 'Weekly Meeting - Moved'

    def test_normalize_with_chronos_markers(self, caldav_adapter, test_calendar_ref):
        """Test normalization preserves Chronos idempotency markers"""
        mock_vevent = Mock()
        mock_vevent.get.side_effect = lambda key, default=None: {
            'UID': 'event-with-markers',
            'SUMMARY': '🎉 Birthday: John Doe (15.01)',
            'DTSTART': Mock(dt=datetime(2025, 1, 15)),
            'X-CHRONOS-CLEANED': 'true',
            'X-CHRONOS-RULE-ID': 'bday',
            'X-CHRONOS-SIGNATURE': 'abc123def456',
            'X-CHRONOS-ORIGINAL-SUMMARY': 'BDAY: John Doe 15.01.1990',
            'X-CHRONOS-PAYLOAD': '{"name": "John Doe", "date": "1990-01-15"}'
        }.get(key, default)

        mock_vevent.has_key = lambda key: key in [
            'UID', 'SUMMARY', 'DTSTART',
            'X-CHRONOS-CLEANED', 'X-CHRONOS-RULE-ID', 'X-CHRONOS-SIGNATURE',
            'X-CHRONOS-ORIGINAL-SUMMARY', 'X-CHRONOS-PAYLOAD'
        ]

        normalized = caldav_adapter._normalize_vevent(mock_vevent, '"etag-markers"', test_calendar_ref)

        markers = normalized['meta']['chronos_markers']
        assert markers['cleaned'] == 'true'
        assert markers['rule_id'] == 'bday'
        assert markers['signature'] == 'abc123def456'
        assert markers['original_summary'] == 'BDAY: John Doe 15.01.1990'
        assert '{"name": "John Doe"' in markers['payload']


class TestCalDAVHTTPOperations:
    """Test CalDAV HTTP operations and protocol handling"""

    @pytest.fixture
    def caldav_adapter(self, minimal_config):
        return CalDAVAdapter(minimal_config)

    @pytest.fixture
    def test_calendar_ref(self):
        return CalendarRef(
            id='test-cal',
            alias='Test Calendar',
            url='http://radicale.test:5232/user/collection/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    @pytest.mark.asyncio
    async def test_get_event_success(self, caldav_adapter, test_calendar_ref):
        """Test successful event retrieval"""
        sample_ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event-123
SUMMARY:Test Event
DTSTART:20250115T100000Z
DTEND:20250115T110000Z
END:VEVENT
END:VCALENDAR"""

        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text.return_value = sample_ics
            mock_response.headers = {'ETag': '"test-etag-123"'}

            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            event = await caldav_adapter.get_event(test_calendar_ref, 'test-event-123')

            assert event is not None
            assert event['id'] == 'test-event-123'
            assert event['summary'] == 'Test Event'
            assert event['etag'] == '"test-etag-123"'

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, caldav_adapter, test_calendar_ref):
        """Test event not found handling"""
        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 404

            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            event = await caldav_adapter.get_event(test_calendar_ref, 'nonexistent-event')

            assert event is None

    @pytest.mark.asyncio
    async def test_create_event_success(self, caldav_adapter, test_calendar_ref):
        """Test successful event creation"""
        event_data = {
            'summary': 'New Test Event',
            'description': 'Created via CalDAV',
            'start_time': datetime(2025, 1, 15, 14, 0),
            'end_time': datetime(2025, 1, 15, 15, 0),
            'all_day': False,
            'chronos_markers': {
                'cleaned': 'true',
                'rule_id': 'manual'
            }
        }

        with patch.object(caldav_adapter, '_get_session') as mock_session, \
             patch.object(caldav_adapter, '_generate_uid', return_value='new-event-uid'):

            mock_response = AsyncMock()
            mock_response.status = 201

            mock_session_instance = AsyncMock()
            mock_session_instance.put.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            event_id = await caldav_adapter.create_event(test_calendar_ref, event_data)

            assert event_id == 'new-event-uid'

            # Verify PUT was called with correct data
            mock_session_instance.put.assert_called_once()
            call_args = mock_session_instance.put.call_args

            # Check URL
            expected_url = 'http://radicale.test:5232/user/collection/new-event-uid.ics'
            assert call_args[0][0] == expected_url

            # Check iCalendar content
            ics_content = call_args[1]['data']
            assert 'SUMMARY:New Test Event' in ics_content
            assert 'DTSTART:20250115T140000Z' in ics_content
            assert 'DTEND:20250115T150000Z' in ics_content
            assert 'X-CHRONOS-CLEANED:true' in ics_content

    @pytest.mark.asyncio
    async def test_patch_event_success(self, caldav_adapter, test_calendar_ref):
        """Test successful event patching"""
        patch_data = {
            'summary': 'Updated Event Title',
            'description': 'Updated description',
            'chronos_markers': {
                'cleaned': 'true',
                'signature': 'new-signature'
            }
        }

        # Mock getting existing event first
        existing_ics = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:existing-event
SUMMARY:Old Title
DTSTART:20250115T100000Z
DTEND:20250115T110000Z
END:VEVENT
END:VCALENDAR"""

        with patch.object(caldav_adapter, '_get_session') as mock_session:
            # Mock GET for existing event
            mock_get_response = AsyncMock()
            mock_get_response.status = 200
            mock_get_response.text.return_value = existing_ics
            mock_get_response.headers = {'ETag': '"old-etag"'}

            # Mock PUT for updated event
            mock_put_response = AsyncMock()
            mock_put_response.status = 204
            mock_put_response.headers = {'ETag': '"new-etag"'}

            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_get_response
            mock_session_instance.put.return_value.__aenter__.return_value = mock_put_response
            mock_session.return_value = mock_session_instance

            new_etag = await caldav_adapter.patch_event(
                test_calendar_ref, 'existing-event', patch_data, '"old-etag"'
            )

            assert new_etag == '"new-etag"'

    @pytest.mark.asyncio
    async def test_patch_event_conflict(self, caldav_adapter, test_calendar_ref):
        """Test ETag conflict during patch"""
        patch_data = {'summary': 'Updated Title'}

        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 412  # Precondition Failed
            mock_response.text.return_value = "Precondition Failed"

            mock_session_instance = AsyncMock()
            mock_session_instance.put.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            with pytest.raises(ConflictError) as exc_info:
                await caldav_adapter.patch_event(
                    test_calendar_ref, 'event-id', patch_data, '"wrong-etag"'
                )

            assert "ETag conflict" in str(exc_info.value)
            assert exc_info.value.expected_etag == '"wrong-etag"'

    @pytest.mark.asyncio
    async def test_delete_event_success(self, caldav_adapter, test_calendar_ref):
        """Test successful event deletion"""
        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 204

            mock_session_instance = AsyncMock()
            mock_session_instance.delete.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            success = await caldav_adapter.delete_event(test_calendar_ref, 'event-to-delete')

            assert success == True

            # Verify DELETE was called
            expected_url = 'http://radicale.test:5232/user/collection/event-to-delete.ics'
            mock_session_instance.delete.assert_called_once_with(expected_url)

    @pytest.mark.asyncio
    async def test_delete_readonly_calendar(self, caldav_adapter):
        """Test deletion attempt on read-only calendar"""
        readonly_calendar = CalendarRef(
            id='readonly-cal',
            alias='Read Only Calendar',
            url='http://readonly.test/',
            read_only=True,
            timezone='UTC'
        )

        with pytest.raises(PermissionError) as exc_info:
            await caldav_adapter.delete_event(readonly_calendar, 'some-event')

        assert "read-only" in str(exc_info.value)


class TestCalDAVSyncOperations:
    """Test CalDAV sync operations and RFC 6578 support"""

    @pytest.fixture
    def caldav_adapter(self, minimal_config):
        return CalDAVAdapter(minimal_config)

    @pytest.fixture
    def test_calendar_ref(self):
        return CalendarRef(
            id='sync-test-cal',
            alias='Sync Test Calendar',
            url='http://radicale.test:5232/user/synctest/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    @pytest.mark.asyncio
    async def test_list_events_with_sync_token(self, caldav_adapter, test_calendar_ref):
        """Test listing events with sync-token for incremental sync"""
        sync_response = """<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
    <d:sync-token>sync-token-123</d:sync-token>
    <d:response>
        <d:href>/user/synctest/event1.ics</d:href>
        <d:propstat>
            <d:prop>
                <d:getetag>"etag1"</d:getetag>
                <cal:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event1
SUMMARY:Event 1
DTSTART:20250115T100000Z
DTEND:20250115T110000Z
END:VEVENT
END:VCALENDAR</cal:calendar-data>
            </d:prop>
            <d:status>HTTP/1.1 200 OK</d:status>
        </d:propstat>
    </d:response>
</d:multistatus>"""

        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 207
            mock_response.text.return_value = sync_response

            mock_session_instance = AsyncMock()
            mock_session_instance.request.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            result = await caldav_adapter.list_events(
                test_calendar_ref,
                sync_token="old-sync-token"
            )

            assert isinstance(result, EventListResult)
            assert len(result.events) == 1
            assert result.sync_token == "sync-token-123"
            assert result.events[0]['id'] == 'event1'
            assert result.events[0]['summary'] == 'Event 1'

    @pytest.mark.asyncio
    async def test_list_events_calendar_query(self, caldav_adapter, test_calendar_ref):
        """Test listing events with calendar-query (time-range)"""
        query_response = """<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
    <d:response>
        <d:href>/user/synctest/event2.ics</d:href>
        <d:propstat>
            <d:prop>
                <d:getetag>"etag2"</d:getetag>
                <cal:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event2
SUMMARY:Event 2
DTSTART:20250120T140000Z
DTEND:20250120T150000Z
END:VEVENT
END:VCALENDAR</cal:calendar-data>
            </d:prop>
            <d:status>HTTP/1.1 200 OK</d:status>
        </d:propstat>
    </d:response>
</d:multistatus>"""

        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 207
            mock_response.text.return_value = query_response

            mock_session_instance = AsyncMock()
            mock_session_instance.request.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            since = datetime(2025, 1, 15)
            until = datetime(2025, 1, 25)

            result = await caldav_adapter.list_events(
                test_calendar_ref,
                since=since,
                until=until
            )

            assert len(result.events) == 1
            assert result.events[0]['id'] == 'event2'
            assert result.events[0]['summary'] == 'Event 2'

            # Verify calendar-query was used
            mock_session_instance.request.assert_called_once()
            call_args = mock_session_instance.request.call_args
            assert call_args[0][0] == 'REPORT'  # HTTP method

            # Check that time-range was included in request body
            request_body = call_args[1]['data']
            assert 'time-range' in request_body
            assert '20250115T000000Z' in request_body
            assert '20250125T000000Z' in request_body


class TestCalDAVErrorHandling:
    """Test CalDAV error handling and resilience"""

    @pytest.fixture
    def caldav_adapter(self, minimal_config):
        return CalDAVAdapter(minimal_config)

    @pytest.fixture
    def test_calendar_ref(self):
        return CalendarRef(
            id='error-test-cal',
            alias='Error Test Calendar',
            url='http://radicale.test:5232/user/errortest/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    @pytest.mark.asyncio
    async def test_network_timeout_handling(self, caldav_adapter, test_calendar_ref):
        """Test handling of network timeouts"""
        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session_instance.get.side_effect = asyncio.TimeoutError()
            mock_session.return_value = mock_session_instance

            event = await caldav_adapter.get_event(test_calendar_ref, 'timeout-event')

            assert event is None  # Should gracefully handle timeout

    @pytest.mark.asyncio
    async def test_server_error_handling(self, caldav_adapter, test_calendar_ref):
        """Test handling of server errors (5xx)"""
        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text.return_value = "Internal Server Error"

            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            event = await caldav_adapter.get_event(test_calendar_ref, 'server-error-event')

            assert event is None

    @pytest.mark.asyncio
    async def test_malformed_icalendar_handling(self, caldav_adapter, test_calendar_ref):
        """Test handling of malformed iCalendar data"""
        malformed_ics = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:malformed-event
SUMMARY:Event with bad data
DTSTART:INVALID-DATE-FORMAT
DTEND:20250115T110000Z
END:VEVENT
END:VCALENDAR"""

        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text.return_value = malformed_ics
            mock_response.headers = {'ETag': '"malformed-etag"'}

            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            event = await caldav_adapter.get_event(test_calendar_ref, 'malformed-event')

            # Should handle malformed data gracefully
            assert event is None or event.get('start_time') is None

    @pytest.mark.asyncio
    async def test_authentication_failure(self, caldav_adapter, test_calendar_ref):
        """Test handling of authentication failures"""
        with patch.object(caldav_adapter, '_get_session') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_response.text.return_value = "Unauthorized"

            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance

            # Should return False for connection validation
            is_valid = await caldav_adapter.validate_connection()
            assert is_valid == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])