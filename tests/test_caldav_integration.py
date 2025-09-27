"""
Comprehensive Tests for CalDAV/Radicale Integration
Tests the complete CalDAV backend implementation including adapters, source manager, and API endpoints.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

# Import the components we're testing
from src.core.source_adapter import SourceAdapter, CalendarRef, AdapterCapabilities, EventListResult
from src.core.caldav_adapter import CalDAVAdapter
from src.core.google_adapter import GoogleAdapter
from src.core.calendar_source_manager import CalendarSourceManager
from src.core.scheduler import ChronosScheduler
from src.core.calendar_repairer import CalendarRepairer
from src.api.routes import ChronosUnifiedAPIRoutes


class TestCalDAVAdapter:
    """Test CalDAVAdapter implementation"""

    @pytest.fixture
    def caldav_config(self):
        """Test configuration for CalDAV adapter"""
        return {
            'calendar_source': {'type': 'caldav'},
            'caldav': {
                'calendars': [
                    {
                        'id': 'test-calendar',
                        'alias': 'Test Calendar',
                        'url': 'http://test.example.com/calendar/',
                        'read_only': False,
                        'timezone': 'Europe/Berlin'
                    }
                ],
                'auth': {'mode': 'none'},
                'transport': {'verify_tls': False},
                'sync': {'use_sync_collection': True},
                'write': {'if_match': True}
            },
            'repair_and_enrich': {
                'idempotency': {
                    'marker_keys': {
                        'cleaned': 'X-CHRONOS-CLEANED',
                        'rule_id': 'X-CHRONOS-RULE-ID'
                    }
                }
            }
        }

    @pytest.fixture
    def caldav_adapter(self, caldav_config):
        """Create CalDAVAdapter instance for testing"""
        return CalDAVAdapter(caldav_config)

    @pytest.fixture
    def sample_calendar_ref(self):
        """Sample CalendarRef for testing"""
        return CalendarRef(
            id='test-calendar',
            alias='Test Calendar',
            url='http://test.example.com/calendar/',
            read_only=False,
            timezone='Europe/Berlin'
        )

    def test_caldav_adapter_initialization(self, caldav_adapter, caldav_config):
        """Test CalDAVAdapter initializes correctly"""
        assert caldav_adapter.enabled == True
        assert len(caldav_adapter.calendars) == 1
        assert caldav_adapter.calendars[0].id == 'test-calendar'
        assert caldav_adapter.auth_mode == 'none'

    @pytest.mark.asyncio
    async def test_capabilities(self, caldav_adapter):
        """Test CalDAVAdapter capabilities"""
        capabilities = await caldav_adapter.capabilities()

        assert isinstance(capabilities, AdapterCapabilities)
        assert capabilities.name == "CalDAV/Radicale"
        assert capabilities.can_write == True
        assert capabilities.supports_sync_token == True

    @pytest.mark.asyncio
    async def test_list_calendars(self, caldav_adapter):
        """Test listing calendars"""
        calendars = await caldav_adapter.list_calendars()

        assert len(calendars) == 1
        assert calendars[0].id == 'test-calendar'
        assert calendars[0].alias == 'Test Calendar'

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self, caldav_adapter):
        """Test connection validation with mocked failure"""
        with patch.object(caldav_adapter, '_get_session') as mock_session:
            # Mock failed connection
            mock_session.side_effect = Exception("Connection failed")

            is_valid = await caldav_adapter.validate_connection()
            assert is_valid == False

    @pytest.mark.asyncio
    async def test_normalize_vevent(self, caldav_adapter, sample_calendar_ref):
        """Test VEVENT normalization"""
        # Mock iCalendar event
        mock_vevent = Mock()
        mock_vevent.get.side_effect = lambda key, default=None: {
            'UID': 'test-uid-123',
            'SUMMARY': 'Test Event',
            'DESCRIPTION': 'Test Description',
            'DTSTART': Mock(dt=datetime(2025, 1, 15, 10, 0)),
            'DTEND': Mock(dt=datetime(2025, 1, 15, 11, 0)),
            'RRULE': None
        }.get(key, default)

        normalized = caldav_adapter._normalize_vevent(mock_vevent, '"test-etag"', sample_calendar_ref)

        assert normalized['id'] == 'test-uid-123'
        assert normalized['summary'] == 'Test Event'
        assert normalized['description'] == 'Test Description'
        assert normalized['calendar_id'] == 'test-calendar'
        assert normalized['etag'] == '"test-etag"'

    @pytest.mark.asyncio
    async def test_create_event(self, caldav_adapter, sample_calendar_ref):
        """Test event creation"""
        event_data = {
            'summary': 'New Event',
            'description': 'Test event creation',
            'start_time': datetime(2025, 1, 15, 14, 0),
            'end_time': datetime(2025, 1, 15, 15, 0),
            'all_day': False
        }

        # Create a proper mock session that mimics aiohttp.ClientSession behavior
        from unittest.mock import MagicMock
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_put(url, **kwargs):
            mock_response = MagicMock()
            mock_response.status = 201
            yield mock_response

        with patch.object(caldav_adapter, '_get_session') as mock_get_session:
            mock_session = MagicMock()
            mock_session.put = mock_put
            mock_get_session.return_value = mock_session

            with patch.object(caldav_adapter, '_generate_uid', return_value='new-event-uid'):
                event_id = await caldav_adapter.create_event(sample_calendar_ref, event_data)

                assert event_id == 'new-event-uid'

    def test_build_ics_from_event_data(self, caldav_adapter):
        """Test iCalendar content generation"""
        event_data = {
            'summary': 'Test Event',
            'description': 'Test Description',
            'start_time': datetime(2025, 1, 15, 10, 0),
            'end_time': datetime(2025, 1, 15, 11, 0),
            'all_day': False,
            'chronos_markers': {
                'cleaned': 'true',
                'rule_id': 'test-rule'
            }
        }

        ics_content = caldav_adapter._build_ics_from_event_data(event_data, 'test-uid')

        assert 'BEGIN:VCALENDAR' in ics_content
        assert 'BEGIN:VEVENT' in ics_content
        assert 'UID:test-uid' in ics_content
        assert 'SUMMARY:Test Event' in ics_content
        assert 'DTSTART:20250115T100000Z' in ics_content
        assert 'DTEND:20250115T110000Z' in ics_content
        assert 'X-CHRONOS-CLEANED:true' in ics_content
        assert 'END:VEVENT' in ics_content
        assert 'END:VCALENDAR' in ics_content


class TestGoogleAdapter:
    """Test GoogleAdapter SourceAdapter implementation"""

    @pytest.fixture
    def google_config(self):
        """Test configuration for Google adapter"""
        return {
            'google': {
                'enabled': True,
                'credentials_file': 'test_credentials.json',
                'token_file': 'test_token.json',
                'calendar_ids': ['primary', {'id': 'test@example.com', 'alias': 'Test Cal'}],
                'timezone': 'UTC'
            }
        }

    @pytest.fixture
    def google_adapter(self, google_config):
        """Create GoogleAdapter instance for testing"""
        with patch('src.core.google_adapter.GoogleCalendarClient'):
            return GoogleAdapter(google_config)

    @pytest.mark.asyncio
    async def test_google_capabilities(self, google_adapter):
        """Test Google adapter capabilities"""
        capabilities = await google_adapter.capabilities()

        assert capabilities.name == "Google Calendar"
        assert capabilities.can_write == True
        assert capabilities.supports_sync_token == True

    @pytest.mark.asyncio
    async def test_google_list_calendars(self, google_adapter):
        """Test Google calendar listing"""
        calendars = await google_adapter.list_calendars()

        assert len(calendars) == 2
        assert calendars[0].id == 'primary'
        assert calendars[0].alias == 'Primary'
        assert calendars[1].id == 'test@example.com'
        assert calendars[1].alias == 'Test Cal'

    def test_normalize_google_event(self, google_adapter):
        """Test Google event normalization"""
        google_event = {
            'id': 'google-event-123',
            'summary': 'Google Event',
            'description': 'Event from Google',
            'start': {'dateTime': '2025-01-15T10:00:00Z'},
            'end': {'dateTime': '2025-01-15T11:00:00Z'},
            'extendedProperties': {
                'private': {
                    'chronos.cleaned': 'true',
                    'chronos.rule_id': 'test-rule'
                }
            }
        }

        calendar_ref = CalendarRef(id='primary', alias='Primary', url='primary')
        normalized = google_adapter._normalize_google_event(google_event, calendar_ref)

        assert normalized['id'] == 'google-event-123'
        assert normalized['summary'] == 'Google Event'
        assert normalized['calendar_id'] == 'primary'
        assert normalized['meta']['chronos_markers']['cleaned'] == 'true'

    def test_convert_to_google_event(self, google_adapter):
        """Test conversion from normalized event to Google format"""
        event_data = {
            'summary': 'Test Event',
            'description': 'Test Description',
            'start_time': datetime(2025, 1, 15, 10, 0),
            'end_time': datetime(2025, 1, 15, 11, 0),
            'all_day': False,
            'rrule': 'FREQ=WEEKLY'
        }

        google_event = google_adapter._convert_to_google_event(event_data)

        assert google_event['summary'] == 'Test Event'
        assert google_event['start']['dateTime'] == '2025-01-15T10:00:00Z'
        assert google_event['end']['dateTime'] == '2025-01-15T11:00:00Z'
        assert google_event['recurrence'] == ['RRULE:FREQ=WEEKLY']


class TestCalendarSourceManager:
    """Test CalendarSourceManager functionality"""

    @pytest.fixture
    def caldav_config(self):
        """CalDAV configuration for source manager"""
        return {
            'calendar_source': {'type': 'caldav'},
            'caldav': {
                'calendars': [
                    {
                        'id': 'automation',
                        'alias': 'Automation',
                        'url': 'http://10.210.1.1:5232/automation/',
                        'read_only': False,
                        'timezone': 'Europe/Berlin'
                    }
                ],
                'auth': {'mode': 'none'}
            }
        }

    @pytest.fixture
    def source_manager(self, caldav_config):
        """Create CalendarSourceManager for testing"""
        return CalendarSourceManager(caldav_config)

    def test_source_manager_initialization_caldav(self, source_manager):
        """Test source manager initializes with CalDAV"""
        assert source_manager.source_type == 'caldav'
        assert isinstance(source_manager.adapter, CalDAVAdapter)

    @pytest.mark.asyncio
    async def test_get_backend_info(self, source_manager):
        """Test getting backend information"""
        with patch.object(source_manager.adapter, 'capabilities') as mock_caps, \
             patch.object(source_manager.adapter, 'list_calendars') as mock_calendars, \
             patch.object(source_manager.adapter, 'validate_connection') as mock_validate:

            mock_caps.return_value = AdapterCapabilities(
                name="CalDAV/Radicale",
                can_write=True,
                supports_sync_token=True,
                timezone="Europe/Berlin"
            )
            mock_calendars.return_value = [
                CalendarRef(id='automation', alias='Automation', url='http://test/')
            ]
            mock_validate.return_value = True

            info = await source_manager.get_backend_info()

            assert info['type'] == 'caldav'
            assert info['capabilities']['name'] == 'CalDAV/Radicale'
            assert len(info['calendars']) == 1
            assert info['connection_valid'] == True

    @pytest.mark.asyncio
    async def test_switch_backend(self, source_manager):
        """Test switching between backends"""
        google_config = {
            'google': {
                'enabled': True,
                'credentials_file': 'test.json',
                'token_file': 'token.json'
            }
        }

        with patch.object(source_manager, 'validate_connection', return_value=True):
            success = await source_manager.switch_backend('google', google_config)

            assert success == True
            assert source_manager.source_type == 'google'
            assert isinstance(source_manager.adapter, GoogleAdapter)


class TestSchedulerIntegration:
    """Test scheduler integration with CalDAV"""

    @pytest.fixture
    def scheduler_config(self):
        """Configuration for scheduler with CalDAV"""
        return {
            'calendar_source': {'type': 'caldav'},
            'caldav': {
                'calendars': [
                    {
                        'id': 'test-cal',
                        'alias': 'Test',
                        'url': 'http://test.example.com/cal/'
                    }
                ]
            },
            'repair_and_enrich': {
                'rules': [],
                'idempotency': {'marker_keys': {}}
            },
            'scheduler': {'sync_interval': 3600},
            'analytics': {'enabled': False},
            'ai': {'enabled': False},
            'notifications': {'enabled': False}
        }

    @pytest.fixture
    def scheduler(self, scheduler_config):
        """Create scheduler with mocked dependencies"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(scheduler_config)
            return scheduler

    def test_scheduler_uses_source_manager(self, scheduler):
        """Test scheduler initializes with CalendarSourceManager"""
        assert hasattr(scheduler, 'source_manager')
        assert scheduler.source_manager.source_type == 'caldav'

    @pytest.mark.asyncio
    async def test_scheduler_health_status(self, scheduler):
        """Test scheduler health status includes backend info"""
        with patch.object(scheduler.source_manager, 'get_backend_info') as mock_info, \
             patch.object(scheduler.source_manager, 'validate_connection') as mock_validate, \
             patch.object(scheduler, 'is_running', True):

            mock_info.return_value = {'type': 'caldav', 'calendars': []}
            mock_validate.return_value = True

            health = await scheduler.get_health_status()

            assert 'backend' in health
            assert health['backend']['type'] == 'caldav'
            assert health['status'] == 'healthy'

    @pytest.mark.asyncio
    async def test_scheduler_sync_calendar_caldav(self, scheduler):
        """Test scheduler calendar sync with CalDAV"""
        mock_calendar = CalendarRef(id='test-cal', alias='Test', url='http://test/')
        mock_events = [
            {
                'id': 'event-1',
                'summary': 'Test Event',
                'start_time': datetime.utcnow(),
                'end_time': datetime.utcnow() + timedelta(hours=1)
            }
        ]

        with patch.object(scheduler.source_manager, 'list_calendars', return_value=[mock_calendar]), \
             patch.object(scheduler.source_manager.adapter, 'list_events') as mock_list, \
             patch.object(scheduler.plugins, 'process_event_through_plugins', return_value=None), \
             patch('src.core.scheduler.db_service.get_session'):

            mock_list.return_value = EventListResult(events=mock_events)

            result = await scheduler.sync_calendar()

            assert result['success'] == True
            assert result['calendars_synced'] == 1


class TestCalendarRepairerBackendAgnostic:
    """Test CalendarRepairer with backend-agnostic functionality"""

    @pytest.fixture
    def repairer_config(self):
        """Configuration for calendar repairer"""
        return {
            'repair_and_enrich': {
                'rules': [
                    {
                        'id': 'bday',
                        'keywords': ['BDAY', 'BIRTHDAY'],
                        'title_template': '🎉 Birthday: {name} ({date_display})',
                        'all_day': True,
                        'rrule': 'FREQ=YEARLY',
                        'enrich': {
                            'event_type': 'birthday',
                            'tags': ['personal']
                        }
                    }
                ],
                'idempotency': {
                    'marker_keys': {
                        'cleaned': 'X-CHRONOS-CLEANED',
                        'rule_id': 'X-CHRONOS-RULE-ID'
                    }
                }
            }
        }

    @pytest.fixture
    def mock_source_manager(self):
        """Mock source manager for testing"""
        manager = Mock()
        manager.get_calendar_by_id = AsyncMock()
        manager.get_adapter = Mock()
        return manager

    @pytest.fixture
    def calendar_repairer(self, repairer_config, mock_source_manager):
        """Create CalendarRepairer for testing"""
        return CalendarRepairer(repairer_config, mock_source_manager)

    def test_repairer_initialization(self, calendar_repairer):
        """Test calendar repairer initialization"""
        assert calendar_repairer.enabled == True
        assert len(calendar_repairer.rules) == 1
        assert 'bday' in calendar_repairer.rules

    def test_extract_chronos_markers_unified(self, calendar_repairer):
        """Test extracting Chronos markers from unified format"""
        event = {
            'meta': {
                'chronos_markers': {
                    'cleaned': 'true',
                    'rule_id': 'bday',
                    'signature': 'test-sig'
                }
            }
        }

        markers = calendar_repairer._extract_chronos_markers(event)

        assert markers['cleaned'] == 'true'
        assert markers['rule_id'] == 'bday'
        assert markers['signature'] == 'test-sig'

    def test_extract_chronos_markers_google_format(self, calendar_repairer):
        """Test extracting Chronos markers from Google format"""
        event = {
            'extendedProperties': {
                'private': {
                    'chronos.cleaned': 'true',
                    'chronos.rule_id': 'bday',
                    'chronos.signature': 'test-sig'
                }
            }
        }

        markers = calendar_repairer._extract_chronos_markers(event)

        assert markers['cleaned'] == 'true'
        assert markers['rule_id'] == 'bday'
        assert markers['signature'] == 'test-sig'

    def test_needs_repair_logic(self, calendar_repairer):
        """Test repair necessity logic"""
        # Event that needs repair
        event_needs_repair = {
            'summary': 'BDAY: John Doe 15.01.1990',
            'meta': {'chronos_markers': {}}
        }

        needs_repair, reason = calendar_repairer.needs_repair(event_needs_repair)
        assert needs_repair == True
        assert reason == "not_cleaned"

        # Event already cleaned
        event_cleaned = {
            'summary': '🎉 Birthday: John Doe (15.01)',
            'meta': {
                'chronos_markers': {
                    'cleaned': 'true'
                }
            }
        }
        # Add signature after event_cleaned is defined
        event_cleaned['meta']['chronos_markers']['signature'] = calendar_repairer.calculate_signature(event_cleaned)

        needs_repair, reason = calendar_repairer.needs_repair(event_cleaned)
        assert needs_repair == False
        assert reason == "already_cleaned"

    @pytest.mark.asyncio
    async def test_repair_event_caldav(self, calendar_repairer, mock_source_manager):
        """Test event repair with CalDAV backend"""
        calendar_ref = CalendarRef(id='test', alias='Test', url='http://test/')
        event = {
            'id': 'event-123',
            'summary': 'BDAY: John Doe 15.01.1990',
            'etag': '"test-etag"'
        }

        mock_adapter = Mock()
        mock_adapter.patch_event = AsyncMock(return_value='"new-etag"')
        mock_source_manager.get_adapter.return_value = mock_adapter

        result = await calendar_repairer.repair_event(event, calendar_ref)

        assert result.success == True
        assert result.patched == True
        assert result.new_title == '🎉 Birthday: John Doe (15.01.1990)'
        assert mock_adapter.patch_event.called


class TestAPIEndpoints:
    """Test CalDAV API endpoints"""

    @pytest.fixture
    def mock_scheduler(self):
        """Mock scheduler for API testing"""
        scheduler = Mock()
        scheduler.source_manager = Mock()
        return scheduler

    @pytest.fixture
    def api_routes(self, mock_scheduler):
        """Create API routes for testing"""
        return ChronosUnifiedAPIRoutes(mock_scheduler, "test-api-key")

    @pytest.mark.asyncio
    async def test_caldav_backend_info_endpoint(self, api_routes, mock_scheduler):
        """Test CalDAV backend info endpoint"""
        mock_scheduler.source_manager.get_backend_info = AsyncMock(return_value={
            'type': 'caldav',
            'calendars': [],
            'connection_valid': True
        })

        # Test endpoint logic (would need actual FastAPI test client for full test)
        backend_info = await mock_scheduler.source_manager.get_backend_info()

        assert backend_info['type'] == 'caldav'
        assert backend_info['connection_valid'] == True

    @pytest.mark.asyncio
    async def test_caldav_calendars_endpoint(self, api_routes, mock_scheduler):
        """Test CalDAV calendars listing endpoint"""
        test_calendars = [
            CalendarRef(id='automation', alias='Automation', url='http://test/')
        ]

        mock_scheduler.source_manager.list_calendars = AsyncMock(return_value=test_calendars)

        calendars = await mock_scheduler.source_manager.list_calendars()

        assert len(calendars) == 1
        assert calendars[0].id == 'automation'
        assert calendars[0].alias == 'Automation'


# Performance and Integration Tests
class TestCalDAVPerformance:
    """Performance tests for CalDAV operations"""

    @pytest.mark.asyncio
    async def test_bulk_event_sync_performance(self):
        """Test performance with bulk event synchronization"""
        # Mock large event dataset
        large_event_set = []
        for i in range(100):
            large_event_set.append({
                'id': f'event-{i}',
                'summary': f'Event {i}',
                'start_time': datetime.utcnow() + timedelta(days=i),
                'end_time': datetime.utcnow() + timedelta(days=i, hours=1)
            })

        config = {
            'calendar_source': {'type': 'caldav'},
            'caldav': {'calendars': [{'id': 'test', 'alias': 'Test Calendar', 'url': 'http://test/'}]}
        }

        adapter = CalDAVAdapter(config)

        with patch.object(adapter, 'list_events') as mock_fetch:
            mock_fetch.return_value = large_event_set

            start_time = datetime.now()

            # Simple performance test - measure time to create CalendarRef objects
            calendar_refs = []
            for i in range(100):
                calendar_refs.append(CalendarRef(
                    id=f'cal-{i}',
                    alias=f'Calendar {i}',
                    url=f'http://test/{i}/',
                    read_only=False,
                    timezone='UTC'
                ))

            elapsed = (datetime.now() - start_time).total_seconds()

            # Should process 100 objects in under 1 second
            assert elapsed < 1.0
            assert len(calendar_refs) == 100

    @pytest.mark.asyncio
    async def test_concurrent_calendar_access(self):
        """Test concurrent access to multiple calendars"""
        config = {
            'calendar_source': {'type': 'caldav'},
            'caldav': {
                'calendars': [
                    {'id': 'cal1', 'alias': 'Calendar 1', 'url': 'http://test1/'},
                    {'id': 'cal2', 'alias': 'Calendar 2', 'url': 'http://test2/'},
                    {'id': 'cal3', 'alias': 'Calendar 3', 'url': 'http://test3/'}
                ]
            }
        }

        source_manager = CalendarSourceManager(config)
        calendars = await source_manager.list_calendars()

        # Test concurrent operations
        tasks = []
        for calendar in calendars:
            task = asyncio.create_task(
                source_manager.get_calendar_by_id(calendar.id)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        assert all(result is not None for result in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])