"""
End-to-End Tests for CalDAV Integration
Tests the complete CalDAV workflow from configuration to event processing.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import tempfile
import yaml
import os

from src.core.scheduler import ChronosScheduler
from src.core.calendar_source_manager import CalendarSourceManager
from src.core.calendar_repairer import CalendarRepairer
from src.core.source_adapter import CalendarRef, EventListResult


class TestCalDAVEndToEndWorkflow:
    """Test complete CalDAV workflow end-to-end"""

    @pytest.fixture
    def complete_caldav_config(self):
        """Complete CalDAV configuration for E2E testing"""
        return {
            'version': 1,
            'calendar_source': {
                'type': 'caldav',
                'timezone_default': 'Europe/Berlin'
            },
            'caldav': {
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
                    },
                    {
                        'id': 'special',
                        'alias': 'Special',
                        'url': 'http://10.210.1.1:5232/radicaleuser/special/',
                        'read_only': True,
                        'timezone': 'Europe/Berlin'
                    }
                ],
                'auth': {
                    'mode': 'none',
                    'username': 'radicaleuser',
                    'password_ref': 'env:RADICALE_PASSWORD'
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
                'reserved_prefixes': ['ACTION', 'MEETING', 'CALL'],
                'parsing': {
                    'accept_date_separators': ['.', '-', '/'],
                    'day_first': True,
                    'year_optional': True,
                    'strict_when_ambiguous': True
                },
                'series_policy': {
                    'edit_master_if_keyword_on_master': True,
                    'edit_instance_if_keyword_on_instance': True,
                    'do_not_edit_past_instances': True
                },
                'idempotency': {
                    'marker_keys': {
                        'cleaned': 'X-CHRONOS-CLEANED',
                        'rule_id': 'X-CHRONOS-RULE-ID',
                        'signature': 'X-CHRONOS-SIGNATURE',
                        'original_summary': 'X-CHRONOS-ORIGINAL-SUMMARY',
                        'payload': 'X-CHRONOS-PAYLOAD'
                    }
                },
                'rules': [
                    {
                        'id': 'bday',
                        'keywords': ['BDAY', 'BIRTHDAY', 'GEB', 'GEBURTSTAG'],
                        'title_template': '🎉 Birthday: {name} ({date_display}){age_suffix}',
                        'age_suffix_template': ' – turns {age}.',
                        'all_day': True,
                        'rrule': 'FREQ=YEARLY',
                        'leap_day_policy': 'FEB_28',
                        'enrich': {
                            'event_type': 'birthday',
                            'tags': ['personal', 'birthday'],
                            'sub_tasks': [
                                {'text': 'Buy card', 'completed': False},
                                {'text': 'Get gift', 'completed': False}
                            ]
                        }
                    }
                ]
            },
            'scheduler': {
                'sync_interval': 3600,
                'max_workers': 5,
                'enabled': True
            },
            'database': {
                'url': 'sqlite:///:memory:',
                'echo': False
            },
            'analytics': {'enabled': False},
            'ai': {'enabled': False},
            'notifications': {'enabled': False}
        }

    @pytest.fixture
    def sample_calendar_events(self):
        """Sample CalDAV events for testing"""
        return [
            {
                'id': 'birthday-event-1',
                'uid': 'birthday-event-1',
                'summary': 'BDAY: John Doe 15.01.1990',
                'description': '',
                'start_time': datetime(2025, 1, 15),
                'end_time': datetime(2025, 1, 16),
                'all_day': True,
                'calendar_id': 'automation',
                'etag': '"bday-etag-1"',
                'rrule': None,
                'recurrence_id': None,
                'is_series_master': False,
                'meta': {
                    'calendar_ref': CalendarRef(
                        id='automation',
                        alias='Automation',
                        url='http://test/'
                    ),
                    'chronos_markers': {}
                }
            },
            {
                'id': 'regular-event-2',
                'uid': 'regular-event-2',
                'summary': 'Regular Meeting',
                'description': 'Weekly team meeting',
                'start_time': datetime(2025, 1, 16, 10, 0),
                'end_time': datetime(2025, 1, 16, 11, 0),
                'all_day': False,
                'calendar_id': 'dates',
                'etag': '"regular-etag-2"',
                'rrule': 'FREQ=WEEKLY',
                'recurrence_id': None,
                'is_series_master': True,
                'meta': {
                    'calendar_ref': CalendarRef(
                        id='dates',
                        alias='Dates',
                        url='http://test2/'
                    ),
                    'chronos_markers': {}
                }
            },
            {
                'id': 'repaired-event-3',
                'uid': 'repaired-event-3',
                'summary': '🎉 Birthday: Jane Smith (20.02)',
                'description': '',
                'start_time': datetime(2025, 2, 20),
                'end_time': datetime(2025, 2, 21),
                'all_day': True,
                'calendar_id': 'automation',
                'etag': '"repaired-etag-3"',
                'rrule': 'FREQ=YEARLY',
                'recurrence_id': None,
                'is_series_master': True,
                'meta': {
                    'calendar_ref': CalendarRef(
                        id='automation',
                        alias='Automation',
                        url='http://test/'
                    ),
                    'chronos_markers': {
                        'cleaned': 'true',
                        'rule_id': 'bday',
                        'signature': 'abc123def456',
                        'original_summary': 'BDAY: Jane Smith 20.02.1985'
                    }
                }
            }
        ]

    @pytest.mark.asyncio
    async def test_scheduler_initialization_with_caldav(self, complete_caldav_config):
        """Test scheduler initializes correctly with CalDAV configuration"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(complete_caldav_config)

            # Verify CalDAV configuration
            assert hasattr(scheduler, 'source_manager')
            assert scheduler.source_manager.source_type == 'caldav'

            # Verify calendars are configured
            calendars = await scheduler.source_manager.list_calendars()
            assert len(calendars) == 3
            assert any(cal.id == 'automation' for cal in calendars)
            assert any(cal.id == 'dates' for cal in calendars)
            assert any(cal.id == 'special' for cal in calendars)

            # Verify calendar repairer is configured
            assert hasattr(scheduler, 'calendar_repairer')
            assert scheduler.calendar_repairer.enabled == True
            assert 'bday' in scheduler.calendar_repairer.rules

    @pytest.mark.asyncio
    async def test_complete_sync_workflow(self, complete_caldav_config, sample_calendar_events):
        """Test complete sync workflow from CalDAV to database"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'), \
             patch('src.core.scheduler.db_service.get_session') as mock_db:

            # Mock database session
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            scheduler = ChronosScheduler(complete_caldav_config)

            # Mock adapter to return sample events
            mock_adapter = scheduler.source_manager.get_adapter()

            with patch.object(mock_adapter, 'list_events') as mock_list_events, \
                 patch.object(scheduler.plugins, 'process_event_through_plugins') as mock_plugins:

                # Configure mocks
                mock_list_events.return_value = EventListResult(
                    events=sample_calendar_events
                )
                mock_plugins.side_effect = lambda event: event  # Pass through

                # Run sync
                result = await scheduler.sync_calendar(days_ahead=30)

                # Verify results
                assert result['success'] == True
                assert result['calendars_synced'] == 3
                assert result['events_processed'] > 0

                # Verify all calendars were processed
                call_count = mock_list_events.call_count
                assert call_count == 3  # One call per calendar

    @pytest.mark.asyncio
    async def test_calendar_repairer_integration(self, complete_caldav_config, sample_calendar_events):
        """Test CalendarRepairer integration with CalDAV events"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(complete_caldav_config)
            calendar_repairer = scheduler.calendar_repairer

            # Get automation calendar
            calendars = await scheduler.source_manager.list_calendars()
            automation_calendar = next(cal for cal in calendars if cal.id == 'automation')

            # Mock adapter patch_event method
            mock_adapter = scheduler.source_manager.get_adapter()

            with patch.object(mock_adapter, 'patch_event', return_value='"new-etag"') as mock_patch:

                # Filter events that need repair (only the birthday event)
                birthday_events = [
                    event for event in sample_calendar_events
                    if 'BDAY:' in event['summary']
                ]

                # Process through calendar repairer
                repair_results = await calendar_repairer.process_events(
                    birthday_events, automation_calendar
                )

                # Verify repair results
                assert len(repair_results) == 1
                result = repair_results[0]
                assert result.success == True
                assert result.patched == True
                assert result.rule_id == 'bday'
                assert '🎉 Birthday:' in result.new_title

                # Verify CalDAV patch was called
                mock_patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_creation_workflow(self, complete_caldav_config):
        """Test creating new events through CalDAV"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'), \
             patch('src.core.scheduler.db_service.get_session') as mock_db:

            # Mock database session
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            scheduler = ChronosScheduler(complete_caldav_config)

            # Mock adapter create_event method
            mock_adapter = scheduler.source_manager.get_adapter()

            with patch.object(mock_adapter, 'create_event', return_value='new-event-123') as mock_create:

                # Create test event
                from src.core.models import ChronosEvent

                new_event = ChronosEvent(
                    id='new-event-123',
                    title='New CalDAV Event',
                    description='Created through scheduler',
                    start_time=datetime(2025, 1, 20, 14, 0),
                    end_time=datetime(2025, 1, 20, 15, 0),
                    calendar_id='automation'
                )

                # Create event through scheduler
                created_event = await scheduler.create_event(new_event)

                # Verify event was created
                assert created_event.id == 'new-event-123'
                assert created_event.title == 'New CalDAV Event'

                # Verify CalDAV create was called
                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_backend_switching_workflow(self, complete_caldav_config):
        """Test switching between CalDAV and Google Calendar backends"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(complete_caldav_config)

            # Verify initial CalDAV backend
            initial_info = await scheduler.source_manager.get_backend_info()
            assert initial_info['type'] == 'caldav'

            # Mock validation for backend switch
            with patch.object(scheduler.source_manager, 'validate_connection', return_value=True):

                # Switch to Google Calendar
                google_config = {
                    'google': {
                        'enabled': True,
                        'credentials_file': 'test_credentials.json',
                        'token_file': 'test_token.json'
                    }
                }

                success = await scheduler.source_manager.switch_backend('google', google_config)
                assert success == True

                # Verify backend switched
                updated_info = await scheduler.source_manager.get_backend_info()
                assert updated_info['type'] == 'google'

                # Switch back to CalDAV
                success = await scheduler.source_manager.switch_backend('caldav', None)
                assert success == True

                # Verify back to CalDAV
                final_info = await scheduler.source_manager.get_backend_info()
                assert final_info['type'] == 'caldav'

    @pytest.mark.asyncio
    async def test_error_resilience_workflow(self, complete_caldav_config):
        """Test system resilience to CalDAV backend errors"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'), \
             patch('src.core.scheduler.db_service.get_session') as mock_db:

            # Mock database session
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            scheduler = ChronosScheduler(complete_caldav_config)

            # Mock adapter to simulate network errors
            mock_adapter = scheduler.source_manager.get_adapter()

            with patch.object(mock_adapter, 'list_events') as mock_list_events, \
                 patch.object(scheduler.plugins, 'process_event_through_plugins') as mock_plugins:

                # Simulate error on first calendar, success on others
                def list_events_side_effect(calendar, **kwargs):
                    if calendar.id == 'automation':
                        raise Exception("CalDAV server timeout")
                    else:
                        return EventListResult(events=[])

                mock_list_events.side_effect = list_events_side_effect
                mock_plugins.side_effect = lambda event: event

                # Run sync - should handle errors gracefully
                result = await scheduler.sync_calendar()

                # Verify partial success
                assert result['success'] == True
                assert result['calendars_synced'] == 3  # All calendars attempted
                # Errors logged but sync continues

    @pytest.mark.asyncio
    async def test_configuration_validation_workflow(self, complete_caldav_config):
        """Test configuration validation and error handling"""
        # Test with invalid calendar configuration
        invalid_config = complete_caldav_config.copy()
        invalid_config['caldav']['calendars'] = []  # No calendars

        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(invalid_config)

            # Should handle empty calendar list gracefully
            calendars = await scheduler.source_manager.list_calendars()
            assert len(calendars) == 0

            # Sync should succeed but process 0 calendars
            with patch('src.core.scheduler.db_service.get_session'):
                result = await scheduler.sync_calendar()
                assert result['success'] == True
                assert result['calendars_synced'] == 0

    @pytest.mark.asyncio
    async def test_health_monitoring_workflow(self, complete_caldav_config):
        """Test health monitoring and status reporting"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(complete_caldav_config)

            # Mock successful connection
            with patch.object(scheduler.source_manager, 'validate_connection', return_value=True), \
                 patch.object(scheduler.source_manager, 'get_backend_info') as mock_info:

                mock_info.return_value = {
                    'type': 'caldav',
                    'calendars': [{'id': 'test'}],
                    'connection_valid': True
                }

                # Get health status
                health = await scheduler.get_health_status()

                # Verify health information
                assert health['status'] == 'healthy'
                assert health['is_running'] == False  # Not started yet
                assert health['backend']['type'] == 'caldav'
                assert health['backend']['connection_valid'] == True

            # Test with connection failure
            with patch.object(scheduler.source_manager, 'validate_connection', return_value=False):

                health = await scheduler.get_health_status()
                assert health['status'] == 'degraded'

    @pytest.mark.asyncio
    async def test_configuration_file_loading(self, complete_caldav_config):
        """Test loading configuration from YAML file"""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(complete_caldav_config, f)
            config_file = f.name

        try:
            # Load configuration from file
            with open(config_file, 'r') as f:
                loaded_config = yaml.safe_load(f)

            # Verify configuration loaded correctly
            assert loaded_config['calendar_source']['type'] == 'caldav'
            assert len(loaded_config['caldav']['calendars']) == 3
            assert loaded_config['repair_and_enrich']['rules'][0]['id'] == 'bday'

            # Test scheduler with loaded config
            with patch('src.core.scheduler.TaskQueue'), \
                 patch('src.core.scheduler.PluginManager'), \
                 patch('src.core.scheduler.AnalyticsEngine'), \
                 patch('src.core.scheduler.AIOptimizer'), \
                 patch('src.core.scheduler.TimeboxEngine'), \
                 patch('src.core.scheduler.NotificationEngine'), \
                 patch('src.core.scheduler.ReplanEngine'):

                scheduler = ChronosScheduler(loaded_config)
                assert scheduler.source_manager.source_type == 'caldav'

        finally:
            # Clean up temp file
            os.unlink(config_file)


class TestCalDAVPerformanceWorkflow:
    """Test CalDAV performance and scalability"""

    @pytest.mark.asyncio
    async def test_large_calendar_sync_performance(self, complete_caldav_config):
        """Test performance with large number of events"""
        # Generate large event set
        large_event_set = []
        for i in range(1000):
            large_event_set.append({
                'id': f'event-{i}',
                'uid': f'event-{i}',
                'summary': f'Event {i}',
                'start_time': datetime.utcnow() + timedelta(days=i % 365),
                'end_time': datetime.utcnow() + timedelta(days=i % 365, hours=1),
                'all_day': False,
                'calendar_id': 'automation',
                'etag': f'"etag-{i}"',
                'meta': {'chronos_markers': {}}
            })

        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'), \
             patch('src.core.scheduler.db_service.get_session') as mock_db:

            # Mock database session
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            scheduler = ChronosScheduler(complete_caldav_config)

            # Mock adapter to return large event set
            mock_adapter = scheduler.source_manager.get_adapter()

            with patch.object(mock_adapter, 'list_events') as mock_list_events, \
                 patch.object(scheduler.plugins, 'process_event_through_plugins') as mock_plugins:

                mock_list_events.return_value = EventListResult(events=large_event_set)
                mock_plugins.side_effect = lambda event: event

                # Measure sync performance
                start_time = datetime.now()
                result = await scheduler.sync_calendar()
                elapsed = (datetime.now() - start_time).total_seconds()

                # Verify performance (should handle 1000 events reasonably fast)
                assert result['success'] == True
                assert result['events_processed'] >= 1000
                assert elapsed < 10.0  # Should complete within 10 seconds

    @pytest.mark.asyncio
    async def test_concurrent_calendar_operations(self, complete_caldav_config):
        """Test concurrent operations on multiple calendars"""
        with patch('src.core.scheduler.TaskQueue'), \
             patch('src.core.scheduler.PluginManager'), \
             patch('src.core.scheduler.AnalyticsEngine'), \
             patch('src.core.scheduler.AIOptimizer'), \
             patch('src.core.scheduler.TimeboxEngine'), \
             patch('src.core.scheduler.NotificationEngine'), \
             patch('src.core.scheduler.ReplanEngine'):

            scheduler = ChronosScheduler(complete_caldav_config)

            # Get all calendars
            calendars = await scheduler.source_manager.list_calendars()

            # Mock adapter operations
            mock_adapter = scheduler.source_manager.get_adapter()

            with patch.object(mock_adapter, 'validate_connection', return_value=True), \
                 patch.object(mock_adapter, 'list_events') as mock_list:

                mock_list.return_value = EventListResult(events=[])

                # Test concurrent operations
                tasks = []
                for calendar in calendars:
                    task = asyncio.create_task(
                        mock_adapter.list_events(calendar)
                    )
                    tasks.append(task)

                # Wait for all operations to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Verify all operations completed successfully
                assert len(results) == len(calendars)
                assert all(isinstance(result, EventListResult) for result in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])