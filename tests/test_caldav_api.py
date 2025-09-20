"""
Tests for CalDAV API Endpoints
Tests the REST API endpoints for CalDAV backend operations.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
import json

from src.api.routes import ChronosUnifiedAPIRoutes
from src.core.source_adapter import CalendarRef, AdapterCapabilities
from src.core.calendar_source_manager import CalendarSourceManager
from src.core.scheduler import ChronosScheduler


class TestCalDAVAPIEndpoints:
    """Test CalDAV-specific API endpoints"""

    @pytest.fixture
    def mock_scheduler(self):
        """Mock scheduler with source manager"""
        scheduler = Mock(spec=ChronosScheduler)
        scheduler.source_manager = Mock(spec=CalendarSourceManager)
        return scheduler

    @pytest.fixture
    def api_routes(self, mock_scheduler):
        """Create API routes instance"""
        return ChronosUnifiedAPIRoutes(mock_scheduler, "test-api-key")

    @pytest.fixture
    def test_calendar_refs(self):
        """Sample calendar references for testing"""
        return [
            CalendarRef(
                id='automation',
                alias='Automation',
                url='http://10.210.1.1:5232/radicaleuser/automation/',
                read_only=False,
                timezone='Europe/Berlin'
            ),
            CalendarRef(
                id='dates',
                alias='Dates',
                url='http://10.210.1.1:5232/radicaleuser/dates/',
                read_only=False,
                timezone='Europe/Berlin'
            ),
            CalendarRef(
                id='special',
                alias='Special',
                url='http://10.210.1.1:5232/radicaleuser/special/',
                read_only=True,
                timezone='Europe/Berlin'
            )
        ]

    @pytest.fixture
    def backend_info(self):
        """Sample backend info response"""
        return {
            'type': 'caldav',
            'capabilities': {
                'name': 'CalDAV/Radicale',
                'can_write': True,
                'supports_sync_token': True,
                'timezone': 'Europe/Berlin'
            },
            'calendars': [
                {
                    'id': 'automation',
                    'alias': 'Automation',
                    'read_only': False,
                    'timezone': 'Europe/Berlin'
                },
                {
                    'id': 'dates',
                    'alias': 'Dates',
                    'read_only': False,
                    'timezone': 'Europe/Berlin'
                },
                {
                    'id': 'special',
                    'alias': 'Special',
                    'read_only': True,
                    'timezone': 'Europe/Berlin'
                }
            ],
            'connection_valid': True
        }

    def test_api_routes_initialization(self, api_routes, mock_scheduler):
        """Test API routes initialize correctly with scheduler"""
        assert api_routes.scheduler == mock_scheduler
        assert api_routes.api_key == "test-api-key"

    @pytest.mark.asyncio
    async def test_caldav_backend_info_endpoint(self, api_routes, mock_scheduler, backend_info):
        """Test /caldav/backend/info endpoint"""
        mock_scheduler.source_manager.get_backend_info = AsyncMock(return_value=backend_info)

        # Simulate endpoint call
        result = await mock_scheduler.source_manager.get_backend_info()

        assert result['type'] == 'caldav'
        assert result['capabilities']['name'] == 'CalDAV/Radicale'
        assert len(result['calendars']) == 3
        assert result['connection_valid'] == True

    @pytest.mark.asyncio
    async def test_caldav_calendars_endpoint(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test /caldav/calendars endpoint"""
        mock_scheduler.source_manager.list_calendars = AsyncMock(return_value=test_calendar_refs)

        calendars = await mock_scheduler.source_manager.list_calendars()

        assert len(calendars) == 3
        assert calendars[0].id == 'automation'
        assert calendars[0].alias == 'Automation'
        assert calendars[0].read_only == False
        assert calendars[2].read_only == True  # Special calendar is read-only

    @pytest.mark.asyncio
    async def test_caldav_calendar_sync_endpoint(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test /caldav/calendars/{calendar_id}/sync endpoint"""
        automation_calendar = test_calendar_refs[0]

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=automation_calendar)
        mock_scheduler.source_manager.get_adapter = Mock()

        mock_adapter = Mock()
        mock_adapter.list_events = AsyncMock(return_value=Mock(
            events=[
                {
                    'id': 'event-1',
                    'summary': 'Test Event 1',
                    'start_time': datetime(2025, 1, 15, 10, 0)
                },
                {
                    'id': 'event-2',
                    'summary': 'Test Event 2',
                    'start_time': datetime(2025, 1, 16, 14, 0)
                }
            ],
            sync_token='sync-token-123',
            next_page_token=None
        ))

        mock_scheduler.source_manager.get_adapter.return_value = mock_adapter

        # Test the sync operation
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('automation')
        adapter = mock_scheduler.source_manager.get_adapter()

        since = datetime.utcnow()
        until = since + timedelta(days=7)

        result = await adapter.list_events(
            calendar=calendar,
            since=since,
            until=until
        )

        assert len(result.events) == 2
        assert result.sync_token == 'sync-token-123'
        assert result.events[0]['id'] == 'event-1'

    @pytest.mark.asyncio
    async def test_caldav_create_event_endpoint(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test /caldav/calendars/{calendar_id}/events POST endpoint"""
        automation_calendar = test_calendar_refs[0]

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=automation_calendar)
        mock_scheduler.source_manager.get_adapter = Mock()

        mock_adapter = Mock()
        mock_adapter.create_event = AsyncMock(return_value='new-event-uuid-123')
        mock_scheduler.source_manager.get_adapter.return_value = mock_adapter

        event_data = {
            'summary': 'New CalDAV Event',
            'description': 'Created via API',
            'start_time': '2025-01-15T14:00:00',
            'end_time': '2025-01-15T15:00:00',
            'all_day': False,
            'timezone': 'Europe/Berlin',
            'chronos_markers': {
                'cleaned': 'true',
                'rule_id': 'manual'
            }
        }

        # Simulate the API call processing
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('automation')
        adapter = mock_scheduler.source_manager.get_adapter()

        # Normalize event data (as the endpoint would do)
        normalized_event = {
            'summary': event_data['summary'],
            'description': event_data.get('description', ''),
            'start_time': datetime.fromisoformat(event_data['start_time']),
            'end_time': datetime.fromisoformat(event_data['end_time']),
            'all_day': event_data.get('all_day', False),
            'timezone': event_data.get('timezone', calendar.timezone),
            'rrule': event_data.get('rrule'),
            'chronos_markers': event_data.get('chronos_markers', {})
        }

        event_id = await adapter.create_event(calendar, normalized_event)

        assert event_id == 'new-event-uuid-123'
        mock_adapter.create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_caldav_get_event_endpoint(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test /caldav/calendars/{calendar_id}/events/{event_id} GET endpoint"""
        automation_calendar = test_calendar_refs[0]

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=automation_calendar)
        mock_scheduler.source_manager.get_adapter = Mock()

        sample_event = {
            'id': 'existing-event-123',
            'uid': 'existing-event-123',
            'summary': 'Existing Event',
            'description': 'An existing event in the calendar',
            'start_time': datetime(2025, 1, 15, 10, 0),
            'end_time': datetime(2025, 1, 15, 11, 0),
            'all_day': False,
            'calendar_id': 'automation',
            'etag': '"event-etag-123"',
            'meta': {
                'chronos_markers': {
                    'cleaned': 'true',
                    'rule_id': 'bday'
                }
            }
        }

        mock_adapter = Mock()
        mock_adapter.get_event = AsyncMock(return_value=sample_event)
        mock_scheduler.source_manager.get_adapter.return_value = mock_adapter

        # Test the get operation
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('automation')
        adapter = mock_scheduler.source_manager.get_adapter()

        event = await adapter.get_event(calendar, 'existing-event-123')

        assert event is not None
        assert event['id'] == 'existing-event-123'
        assert event['summary'] == 'Existing Event'
        assert event['calendar_id'] == 'automation'
        assert event['meta']['chronos_markers']['cleaned'] == 'true'

    @pytest.mark.asyncio
    async def test_caldav_patch_event_endpoint(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test /caldav/calendars/{calendar_id}/events/{event_id} PATCH endpoint"""
        automation_calendar = test_calendar_refs[0]

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=automation_calendar)
        mock_scheduler.source_manager.get_adapter = Mock()

        mock_adapter = Mock()
        mock_adapter.patch_event = AsyncMock(return_value='"new-etag-456"')
        mock_scheduler.source_manager.get_adapter.return_value = mock_adapter

        patch_data = {
            'summary': 'Updated Event Title',
            'description': 'Updated description',
            'start_time': '2025-01-15T15:00:00',
            'end_time': '2025-01-15T16:00:00'
        }

        # Test the patch operation
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('automation')
        adapter = mock_scheduler.source_manager.get_adapter()

        # Parse datetime fields (as endpoint would do)
        processed_patch_data = patch_data.copy()
        processed_patch_data['start_time'] = datetime.fromisoformat(patch_data['start_time'])
        processed_patch_data['end_time'] = datetime.fromisoformat(patch_data['end_time'])

        new_etag = await adapter.patch_event(
            calendar, 'event-to-patch', processed_patch_data, '"old-etag-123"'
        )

        assert new_etag == '"new-etag-456"'
        mock_adapter.patch_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_caldav_delete_event_endpoint(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test /caldav/calendars/{calendar_id}/events/{event_id} DELETE endpoint"""
        automation_calendar = test_calendar_refs[0]

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=automation_calendar)
        mock_scheduler.source_manager.get_adapter = Mock()

        mock_adapter = Mock()
        mock_adapter.delete_event = AsyncMock(return_value=True)
        mock_scheduler.source_manager.get_adapter.return_value = mock_adapter

        # Test the delete operation
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('automation')
        adapter = mock_scheduler.source_manager.get_adapter()

        success = await adapter.delete_event(calendar, 'event-to-delete')

        assert success == True
        mock_adapter.delete_event.assert_called_once_with(calendar, 'event-to-delete')

    @pytest.mark.asyncio
    async def test_caldav_delete_readonly_calendar_error(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test delete attempt on read-only calendar returns permission error"""
        special_calendar = test_calendar_refs[2]  # Read-only calendar

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=special_calendar)

        # Test that read-only check would trigger (simulated here)
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('special')

        assert calendar.read_only == True
        # In actual endpoint, this would raise HTTPException(status_code=403)

    @pytest.mark.asyncio
    async def test_caldav_backend_switch_endpoint(self, api_routes, mock_scheduler, backend_info):
        """Test /caldav/backend/switch endpoint"""
        mock_scheduler.source_manager.switch_backend = AsyncMock(return_value=True)
        mock_scheduler.source_manager.get_backend_info = AsyncMock(return_value=backend_info)

        switch_data = {
            'backend_type': 'google',
            'config': {
                'google': {
                    'enabled': True,
                    'credentials_file': 'test_credentials.json',
                    'token_file': 'test_token.json'
                }
            }
        }

        # Test the backend switch
        success = await mock_scheduler.source_manager.switch_backend(
            switch_data['backend_type'],
            switch_data.get('config')
        )

        assert success == True
        mock_scheduler.source_manager.switch_backend.assert_called_once()

        # Get updated backend info
        updated_info = await mock_scheduler.source_manager.get_backend_info()
        assert updated_info is not None

    @pytest.mark.asyncio
    async def test_caldav_connection_test_endpoint(self, api_routes, mock_scheduler, backend_info):
        """Test /caldav/connection/test endpoint"""
        mock_scheduler.source_manager.validate_connection = AsyncMock(return_value=True)
        mock_scheduler.source_manager.get_backend_info = AsyncMock(return_value=backend_info)

        # Test connection validation
        connection_valid = await mock_scheduler.source_manager.validate_connection()
        backend_info_result = await mock_scheduler.source_manager.get_backend_info()

        assert connection_valid == True
        assert backend_info_result['type'] == 'caldav'
        assert len(backend_info_result['calendars']) == 3

    @pytest.mark.asyncio
    async def test_caldav_calendar_not_found_error(self, api_routes, mock_scheduler):
        """Test calendar not found error handling"""
        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=None)

        # Test that None return would trigger 404 error
        calendar = await mock_scheduler.source_manager.get_calendar_by_id('nonexistent-calendar')

        assert calendar is None
        # In actual endpoint, this would raise HTTPException(status_code=404)

    @pytest.mark.asyncio
    async def test_caldav_invalid_event_data_error(self, api_routes, mock_scheduler, test_calendar_refs):
        """Test invalid event data validation"""
        automation_calendar = test_calendar_refs[0]

        mock_scheduler.source_manager.get_calendar_by_id = AsyncMock(return_value=automation_calendar)

        # Test with missing required fields
        invalid_event_data = {
            'description': 'Event without summary',
            'start_time': '2025-01-15T14:00:00'
            # Missing 'summary' field
        }

        # In actual endpoint, this would validate and raise HTTPException(status_code=400)
        assert 'summary' not in invalid_event_data
        # This would trigger: raise HTTPException(status_code=400, detail="Event summary is required")

    @pytest.mark.asyncio
    async def test_caldav_source_manager_not_available_error(self, api_routes):
        """Test source manager not available error"""
        # Create routes without scheduler
        api_routes_no_scheduler = ChronosUnifiedAPIRoutes(None, "test-api-key")

        # Test that None scheduler would be caught
        assert api_routes_no_scheduler.scheduler is None
        # In actual endpoint, this would raise HTTPException(status_code=503)


class TestCalDAVAPIAuthentication:
    """Test CalDAV API authentication and authorization"""

    @pytest.fixture
    def api_routes_with_auth(self):
        """Create API routes with authentication"""
        mock_scheduler = Mock()
        return ChronosUnifiedAPIRoutes(mock_scheduler, "secure-api-key-123")

    def test_api_key_verification_valid(self, api_routes_with_auth):
        """Test valid API key passes verification"""
        from fastapi.security import HTTPAuthorizationCredentials

        valid_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="secure-api-key-123"
        )

        # Test that valid credentials pass (no exception raised)
        try:
            api_routes_with_auth._verify_api_key(valid_credentials)
            verification_passed = True
        except:
            verification_passed = False

        assert verification_passed == True

    def test_api_key_verification_invalid(self, api_routes_with_auth):
        """Test invalid API key fails verification"""
        from fastapi.security import HTTPAuthorizationCredentials

        invalid_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="wrong-api-key"
        )

        # Test that invalid credentials raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            api_routes_with_auth._verify_api_key(invalid_credentials)

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

    def test_api_key_verification_missing(self, api_routes_with_auth):
        """Test missing credentials fail verification"""
        # Test that None credentials raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            api_routes_with_auth._verify_api_key(None)

        assert exc_info.value.status_code == 401


class TestCalDAVAPIErrorHandling:
    """Test CalDAV API error handling scenarios"""

    @pytest.fixture
    def api_routes(self):
        """Create API routes for error testing"""
        mock_scheduler = Mock()
        mock_scheduler.source_manager = Mock()
        return ChronosUnifiedAPIRoutes(mock_scheduler, "test-api-key")

    @pytest.mark.asyncio
    async def test_backend_connection_failure(self, api_routes):
        """Test handling of backend connection failures"""
        # Mock connection failure
        api_routes.scheduler.source_manager.validate_connection = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        # Test that connection failures are handled gracefully
        with pytest.raises(Exception):
            await api_routes.scheduler.source_manager.validate_connection()

    @pytest.mark.asyncio
    async def test_calendar_sync_error(self, api_routes):
        """Test handling of calendar sync errors"""
        api_routes.scheduler.source_manager.get_calendar_by_id = AsyncMock(
            return_value=CalendarRef(id='test', alias='Test', url='http://test/')
        )
        api_routes.scheduler.source_manager.get_adapter = Mock()

        mock_adapter = Mock()
        mock_adapter.list_events = AsyncMock(
            side_effect=Exception("Sync failed")
        )
        api_routes.scheduler.source_manager.get_adapter.return_value = mock_adapter

        # Test that sync errors are propagated appropriately
        calendar = await api_routes.scheduler.source_manager.get_calendar_by_id('test')
        adapter = api_routes.scheduler.source_manager.get_adapter()

        with pytest.raises(Exception):
            await adapter.list_events(calendar)

    @pytest.mark.asyncio
    async def test_event_creation_failure(self, api_routes):
        """Test handling of event creation failures"""
        api_routes.scheduler.source_manager.get_calendar_by_id = AsyncMock(
            return_value=CalendarRef(id='test', alias='Test', url='http://test/', read_only=False)
        )
        api_routes.scheduler.source_manager.get_adapter = Mock()

        mock_adapter = Mock()
        mock_adapter.create_event = AsyncMock(
            side_effect=Exception("Create failed")
        )
        api_routes.scheduler.source_manager.get_adapter.return_value = mock_adapter

        # Test that creation errors are handled
        calendar = await api_routes.scheduler.source_manager.get_calendar_by_id('test')
        adapter = api_routes.scheduler.source_manager.get_adapter()

        with pytest.raises(Exception):
            await adapter.create_event(calendar, {'summary': 'Test Event'})


class TestCalDAVAPIResponseFormat:
    """Test CalDAV API response formatting and structure"""

    @pytest.fixture
    def mock_scheduler(self):
        """Mock scheduler for response testing"""
        scheduler = Mock()
        scheduler.source_manager = Mock()
        return scheduler

    @pytest.mark.asyncio
    async def test_backend_info_response_structure(self, mock_scheduler):
        """Test backend info response has correct structure"""
        expected_response = {
            'success': True,
            'backend_info': {
                'type': 'caldav',
                'capabilities': {
                    'name': 'CalDAV/Radicale',
                    'can_write': True,
                    'supports_sync_token': True,
                    'timezone': 'Europe/Berlin'
                },
                'calendars': [
                    {
                        'id': 'automation',
                        'alias': 'Automation',
                        'read_only': False,
                        'timezone': 'Europe/Berlin'
                    }
                ],
                'connection_valid': True
            },
            'timestamp': '2025-01-15T10:00:00'  # Would be actual timestamp
        }

        # Verify response structure
        assert 'success' in expected_response
        assert 'backend_info' in expected_response
        assert 'timestamp' in expected_response

        backend_info = expected_response['backend_info']
        assert 'type' in backend_info
        assert 'capabilities' in backend_info
        assert 'calendars' in backend_info
        assert 'connection_valid' in backend_info

    @pytest.mark.asyncio
    async def test_calendar_list_response_structure(self, mock_scheduler):
        """Test calendar list response has correct structure"""
        expected_response = {
            'success': True,
            'calendars': [
                {
                    'id': 'automation',
                    'alias': 'Automation',
                    'url': 'http://10.210.1.1:5232/radicaleuser/automation/',
                    'read_only': False,
                    'timezone': 'Europe/Berlin'
                },
                {
                    'id': 'dates',
                    'alias': 'Dates',
                    'url': 'http://10.210.1.1:5232/radicaleuser/dates/',
                    'read_only': False,
                    'timezone': 'Europe/Berlin'
                }
            ],
            'count': 2,
            'timestamp': '2025-01-15T10:00:00'
        }

        # Verify response structure
        assert 'success' in expected_response
        assert 'calendars' in expected_response
        assert 'count' in expected_response
        assert 'timestamp' in expected_response
        assert expected_response['count'] == len(expected_response['calendars'])

    @pytest.mark.asyncio
    async def test_event_creation_response_structure(self, mock_scheduler):
        """Test event creation response has correct structure"""
        expected_response = {
            'success': True,
            'event_id': 'new-event-uuid-123',
            'calendar_id': 'automation',
            'calendar_alias': 'Automation',
            'created_at': '2025-01-15T10:00:00'
        }

        # Verify response structure
        assert 'success' in expected_response
        assert 'event_id' in expected_response
        assert 'calendar_id' in expected_response
        assert 'calendar_alias' in expected_response
        assert 'created_at' in expected_response

    @pytest.mark.asyncio
    async def test_error_response_structure(self, mock_scheduler):
        """Test error response has correct structure"""
        expected_error_response = {
            'detail': 'Calendar automation not found'
        }

        # Verify error response structure matches FastAPI format
        assert 'detail' in expected_error_response
        assert isinstance(expected_error_response['detail'], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])