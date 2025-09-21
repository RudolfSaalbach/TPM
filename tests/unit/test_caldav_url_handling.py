"""
Unit Tests for CalDAV URL Handling
Tests the robust URL caching and retrieval mechanisms in CalDAVAdapter
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.core.caldav_adapter import CalDAVAdapter
from src.core.source_adapter import CalendarRef


class TestCalDAVUrlHandling:
    """Test CalDAV URL handling and caching functionality"""

    @pytest.fixture
    def caldav_adapter(self):
        """Create CalDAV adapter with test configuration"""
        config = {
            'caldav': {
                'calendars': [
                    {
                        'id': 'test-cal',
                        'alias': 'Test Calendar',
                        'url': 'https://radicale.example.com/user/calendar/',
                        'read_only': False,
                        'timezone': 'Europe/Berlin'
                    }
                ],
                'auth': {'mode': 'none'},
                'transport': {'verify_tls': False},
                'sync': {'use_sync_collection': True}
            }
        }
        return CalDAVAdapter(config)

    @pytest.fixture
    def test_calendar(self):
        """Test calendar reference"""
        return CalendarRef(
            id='test-cal',
            alias='Test Calendar',
            url='https://radicale.example.com/user/calendar/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    def test_normalize_href_absolute_url(self, caldav_adapter, test_calendar):
        """Test href normalization with absolute URLs"""
        # Absolute URLs should remain unchanged
        absolute_href = "https://server.com/path/to/event.ics"
        result = caldav_adapter._normalize_href(absolute_href, test_calendar)
        assert result == absolute_href

    def test_normalize_href_absolute_path(self, caldav_adapter, test_calendar):
        """Test href normalization with absolute paths"""
        # Absolute path should be converted to full URL
        absolute_path = "/remote.php/dav/calendars/user/personal/event.ics"
        result = caldav_adapter._normalize_href(absolute_path, test_calendar)
        assert result == "https://radicale.example.com/remote.php/dav/calendars/user/personal/event.ics"

    def test_normalize_href_relative_path(self, caldav_adapter, test_calendar):
        """Test href normalization with relative paths"""
        # Relative path should be appended to calendar URL
        relative_path = "event-123.ics"
        result = caldav_adapter._normalize_href(relative_path, test_calendar)
        assert result == "https://radicale.example.com/user/calendar/event-123.ics"

    def test_get_event_href_with_cache(self, caldav_adapter, test_calendar):
        """Test getting event href when cached href is available"""
        event = {
            'meta': {
                'caldav_href': 'https://server.com/calendars/user/cal/event-real-url.ics'
            }
        }

        with patch.object(caldav_adapter, 'logger') as mock_logger:
            result = caldav_adapter._get_event_href(event, test_calendar, 'test-event-id')

            assert result == 'https://server.com/calendars/user/cal/event-real-url.ics'
            mock_logger.debug.assert_called_once()

    def test_get_event_href_without_cache_fallback(self, caldav_adapter, test_calendar):
        """Test getting event href when no cached href is available (fallback)"""
        event = {'meta': {}}  # No cached href

        with patch.object(caldav_adapter, 'logger') as mock_logger:
            result = caldav_adapter._get_event_href(event, test_calendar, 'test-event-id')

            expected_href = "https://radicale.example.com/user/calendar/test-event-id.ics"
            assert result == expected_href
            mock_logger.warning.assert_called_once()
            assert "No cached CalDAV href" in mock_logger.warning.call_args[0][0]

    def test_parse_multistatus_response_caches_href(self, caldav_adapter, test_calendar):
        """Test that _parse_multistatus_response caches href in event meta"""
        xml_response = '''<?xml version="1.0" encoding="UTF-8"?>
        <d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
            <d:response>
                <d:href>/remote.php/dav/calendars/user/personal/abc123.ics</d:href>
                <d:propstat>
                    <d:status>HTTP/1.1 200 OK</d:status>
                    <d:prop>
                        <d:getetag>"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"</d:getetag>
                        <cal:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event-123
SUMMARY:Test Event
DTSTART:20241203T100000Z
DTEND:20241203T110000Z
END:VEVENT
END:VCALENDAR</cal:calendar-data>
                    </d:prop>
                </d:propstat>
            </d:response>
        </d:multistatus>'''

        result = caldav_adapter._parse_multistatus_response(xml_response, test_calendar)

        assert len(result.events) == 1
        event = result.events[0]

        # Check that href was cached correctly
        expected_href = "https://radicale.example.com/remote.php/dav/calendars/user/personal/abc123.ics"
        assert event['meta']['caldav_href'] == expected_href

    @pytest.mark.asyncio
    async def test_patch_event_uses_cached_href(self, caldav_adapter, test_calendar):
        """Test that patch_event uses cached href instead of constructing one"""
        # Mock the current event with cached href
        current_event = {
            'uid': 'test-event-123',
            'summary': 'Original Event',
            'meta': {
                'caldav_href': 'https://server.com/real/path/to/event.ics'
            }
        }

        # Mock dependencies
        with patch.object(caldav_adapter, 'get_event', return_value=current_event) as mock_get, \
             patch.object(caldav_adapter, '_build_ics_with_patches', return_value='MOCK_ICS') as mock_build, \
             patch.object(caldav_adapter, '_get_session') as mock_session:

            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.status = 204
            mock_response.headers = {'ETag': '"new-etag"'}
            mock_session.return_value.__aenter__.return_value.put.return_value.__aenter__.return_value = mock_response

            # Call patch_event
            result = await caldav_adapter.patch_event(
                test_calendar,
                'test-event-123',
                {'summary': 'Updated Event'},
                'old-etag'
            )

            # Verify that the cached href was used
            mock_session.return_value.__aenter__.return_value.put.assert_called_once()
            call_args = mock_session.return_value.__aenter__.return_value.put.call_args
            used_href = call_args[0][0]  # First positional argument

            assert used_href == 'https://server.com/real/path/to/event.ics'
            assert result == 'new-etag'

    @pytest.mark.asyncio
    async def test_delete_event_uses_cached_href(self, caldav_adapter, test_calendar):
        """Test that delete_event uses cached href instead of constructing one"""
        # Mock the current event with cached href
        current_event = {
            'uid': 'test-event-123',
            'meta': {
                'caldav_href': 'https://server.com/real/path/to/event.ics'
            }
        }

        # Mock dependencies
        with patch.object(caldav_adapter, 'get_event', return_value=current_event) as mock_get, \
             patch.object(caldav_adapter, '_get_session') as mock_session:

            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.status = 204
            mock_session.return_value.__aenter__.return_value.delete.return_value.__aenter__.return_value = mock_response

            # Call delete_event
            result = await caldav_adapter.delete_event(test_calendar, 'test-event-123')

            # Verify that the cached href was used
            mock_session.return_value.__aenter__.return_value.delete.assert_called_once()
            call_args = mock_session.return_value.__aenter__.return_value.delete.call_args
            used_href = call_args[0][0]  # First positional argument

            assert used_href == 'https://server.com/real/path/to/event.ics'
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_event_fallback_when_event_not_found(self, caldav_adapter, test_calendar):
        """Test that delete_event falls back to constructed href when event not found"""
        # Mock get_event to return None (event not found)
        with patch.object(caldav_adapter, 'get_event', return_value=None) as mock_get, \
             patch.object(caldav_adapter, '_get_session') as mock_session, \
             patch.object(caldav_adapter, 'logger') as mock_logger:

            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.status = 404  # Not found
            mock_session.return_value.__aenter__.return_value.delete.return_value.__aenter__.return_value = mock_response

            # Call delete_event
            result = await caldav_adapter.delete_event(test_calendar, 'test-event-123')

            # Verify that a warning was logged and constructed href was used
            mock_logger.warning.assert_called_once()
            assert "not found for deletion" in mock_logger.warning.call_args[0][0]

            # Verify the constructed href was used
            mock_session.return_value.__aenter__.return_value.delete.assert_called_once()
            call_args = mock_session.return_value.__aenter__.return_value.delete.call_args
            used_href = call_args[0][0]

            expected_href = "https://radicale.example.com/user/calendar/test-event-123.ics"
            assert used_href == expected_href
            assert result is True  # 404 is considered success for delete

    def test_href_caching_handles_complex_caldav_urls(self, caldav_adapter, test_calendar):
        """Test that href caching works with complex real-world CalDAV URLs"""
        complex_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
            <d:response>
                <d:href>/remote.php/dav/calendars/john.doe/personal/20241203T102030Z-abc123def456.ics</d:href>
                <d:propstat>
                    <d:status>HTTP/1.1 200 OK</d:status>
                    <d:prop>
                        <d:getetag>"complex-etag-hash-value"</d:getetag>
                        <cal:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Nextcloud//Nextcloud//EN
BEGIN:VEVENT
UID:simple-uid-123
SUMMARY:Complex Event
DTSTART:20241203T100000Z
DTEND:20241203T110000Z
END:VEVENT
END:VCALENDAR</cal:calendar-data>
                    </d:prop>
                </d:propstat>
            </d:response>
        </d:multistatus>'''

        result = caldav_adapter._parse_multistatus_response(complex_xml, test_calendar)

        assert len(result.events) == 1
        event = result.events[0]

        # The UID is simple but the href is complex - this is the real-world scenario
        assert event['uid'] == 'simple-uid-123'
        expected_complex_href = "https://radicale.example.com/remote.php/dav/calendars/john.doe/personal/20241203T102030Z-abc123def456.ics"
        assert event['meta']['caldav_href'] == expected_complex_href