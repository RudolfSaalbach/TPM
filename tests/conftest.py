"""
Pytest configuration and fixtures for Chronos Engine tests
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from typing import List
import os
import tempfile

from httpx import AsyncClient
from fastapi.testclient import TestClient

from src.core.models import ChronosEvent, Priority, EventType, EventStatus
from src.core.analytics_engine import AnalyticsEngine
from src.core.event_parser import EventParser
from src.core.database import db_service
from src.main import create_app
from src.config.config_loader import load_config


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_calendar_event():
    """Sample calendar event data"""
    now = datetime.utcnow()
    return {
        'id': 'test_event_1',
        'summary': 'Team Meeting',
        'description': 'Weekly team sync #urgent',
        'start': {'dateTime': now.isoformat() + 'Z'},
        'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'},
        'attendees': [{'email': 'team@example.com'}],
        'location': 'Conference Room A'
    }


@pytest.fixture
def sample_chronos_event():
    """Sample ChronosEvent instance"""
    now = datetime.utcnow()
    return ChronosEvent(
        id='test_chronos_1',
        title='Sample Task',
        description='Test task for unit testing',
        start_time=now,
        end_time=now + timedelta(hours=2),
        priority=Priority.HIGH,
        event_type=EventType.TASK,
        status=EventStatus.SCHEDULED,
        tags=['test', 'sample']
    )


@pytest.fixture
def sample_events_list():
    """List of sample ChronosEvent instances"""
    now = datetime.utcnow()
    events = []
    
    for i in range(5):
        event = ChronosEvent(
            id=f'test_event_{i}',
            title=f'Test Event {i}',
            description=f'Test event number {i}',
            start_time=now + timedelta(hours=i),
            end_time=now + timedelta(hours=i + 1),
            priority=Priority.MEDIUM,
            event_type=EventType.TASK,
            status=EventStatus.SCHEDULED
        )
        events.append(event)
    
    return events


@pytest.fixture
async def analytics_engine():
    """Analytics engine instance for testing"""
    return AnalyticsEngine(cache_dir='test_data/analytics')


@pytest.fixture
def event_parser():
    """Event parser instance for testing"""
    return EventParser()


@pytest.fixture
def mock_calendar_events():
    """Mock calendar events data"""
    base_time = datetime.utcnow()
    return [
        {
            'id': f'mock_event_{i}',
            'summary': f'Mock Event {i}',
            'description': f'Test event {i}',
            'start': {'dateTime': (base_time + timedelta(hours=i)).isoformat() + 'Z'},
            'end': {'dateTime': (base_time + timedelta(hours=i + 1)).isoformat() + 'Z'},
            'attendees': [],
            'location': ''
        }
        for i in range(3)
    ]


@pytest.fixture(autouse=True)
async def cleanup_test_data():
    """Cleanup test data after each test"""
    yield
    # Cleanup code would go here if needed
    # For now, we're using in-memory data structures
    pass


@pytest.fixture
async def test_app():
    """Create a test FastAPI application"""
    # Create test configuration
    test_config = {
        'database': {
            'url': ':memory:',  # Use in-memory SQLite for testing
            'echo': False
        },
        'api': {
            'api_key': 'test-api-key',
            'host': '127.0.0.1',
            'port': 8080,
            'cors_origins': ["*"]
        },
        'scheduler': {
            'sync_interval': 3600,
            'max_workers': 2
        },
        'calendar': {
            'provider': 'mock',
            'credentials_file': None
        }
    }

    # Create app with test config
    app = create_app(test_config)

    # Initialize database for testing
    await db_service.close()  # Close any existing connections
    await db_service.initialize(':memory:')  # Use in-memory database
    await db_service.create_tables()

    yield app

    # Cleanup
    await db_service.close()


@pytest.fixture
async def client(test_app):
    """Create an AsyncClient for testing"""
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac


# CalDAV-specific fixtures
from src.core.source_adapter import CalendarRef, AdapterCapabilities, EventListResult
from src.core.caldav_adapter import CalDAVAdapter
from src.core.calendar_source_manager import CalendarSourceManager
from unittest.mock import Mock, AsyncMock
import yaml


@pytest.fixture
def caldav_test_config():
    """Test configuration for CalDAV"""
    return {
        'calendar_source': {'type': 'caldav'},
        'caldav': {
            'calendars': [
                {
                    'id': 'test-calendar',
                    'alias': 'Test Calendar',
                    'url': 'http://test.radicale.local:5232/user/calendar/',
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
                    'rule_id': 'X-CHRONOS-RULE-ID',
                    'signature': 'X-CHRONOS-SIGNATURE',
                    'original_summary': 'X-CHRONOS-ORIGINAL-SUMMARY',
                    'payload': 'X-CHRONOS-PAYLOAD'
                }
            },
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
            ]
        }
    }


@pytest.fixture
def sample_calendar_refs():
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
def sample_caldav_events():
    """Sample CalDAV events for testing"""
    return [
        {
            'id': 'caldav-event-1',
            'uid': 'caldav-event-1',
            'summary': 'CalDAV Test Event',
            'description': 'Test event from CalDAV',
            'start_time': datetime.utcnow(),
            'end_time': datetime.utcnow() + timedelta(hours=1),
            'all_day': False,
            'calendar_id': 'automation',
            'etag': '"caldav-etag-1"',
            'rrule': None,
            'recurrence_id': None,
            'is_series_master': False,
            'timezone': 'Europe/Berlin',
            'meta': {
                'chronos_markers': {}
            }
        },
        {
            'id': 'birthday-event',
            'uid': 'birthday-event',
            'summary': 'BDAY: John Doe 15.01.1990',
            'description': '',
            'start_time': datetime(2025, 1, 15),
            'end_time': datetime(2025, 1, 16),
            'all_day': True,
            'calendar_id': 'automation',
            'etag': '"birthday-etag"',
            'rrule': None,
            'recurrence_id': None,
            'is_series_master': False,
            'timezone': 'Europe/Berlin',
            'meta': {
                'chronos_markers': {}
            }
        }
    ]


@pytest.fixture
def mock_caldav_adapter():
    """Mock CalDAV adapter for testing"""
    adapter = Mock(spec=CalDAVAdapter)
    adapter.enabled = True
    adapter.list_calendars.return_value = []
    adapter.capabilities.return_value = AdapterCapabilities(
        name="CalDAV/Radicale",
        can_write=True,
        supports_sync_token=True,
        timezone="Europe/Berlin"
    )
    adapter.validate_connection.return_value = True
    return adapter


@pytest.fixture
def mock_source_manager(mock_caldav_adapter):
    """Mock calendar source manager for testing"""
    manager = Mock(spec=CalendarSourceManager)
    manager.source_type = 'caldav'
    manager.get_adapter.return_value = mock_caldav_adapter
    manager.list_calendars = AsyncMock(return_value=[])
    manager.get_backend_info = AsyncMock(return_value={
        'type': 'caldav',
        'calendars': [],
        'connection_valid': True
    })
    manager.validate_connection = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_http_session():
    """Mock aiohttp session for CalDAV testing"""
    session = AsyncMock()

    # Create mock response
    def create_response(status=200, text="", headers=None):
        response = AsyncMock()
        response.status = status
        response.text = AsyncMock(return_value=text)
        response.headers = headers or {}
        return response

    # Configure default responses
    session.get.return_value.__aenter__.return_value = create_response()
    session.put.return_value.__aenter__.return_value = create_response(status=201)
    session.delete.return_value.__aenter__.return_value = create_response(status=204)
    session.request.return_value.__aenter__.return_value = create_response(status=207)

    return session


@pytest.fixture
def sample_icalendar_data():
    """Sample iCalendar data for testing"""
    return {
        'simple_event': """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:simple-event-123
SUMMARY:Simple Test Event
DTSTART:20250115T100000Z
DTEND:20250115T110000Z
END:VEVENT
END:VCALENDAR""",

        'birthday_with_markers': """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Chronos//CalDAV Adapter//EN
BEGIN:VEVENT
UID:birthday-event-123
SUMMARY:🎉 Birthday: John Doe (15.01)
DTSTART;VALUE=DATE:20250115
DTEND;VALUE=DATE:20250116
RRULE:FREQ=YEARLY
X-CHRONOS-CLEANED:true
X-CHRONOS-RULE-ID:bday
X-CHRONOS-SIGNATURE:abc123def456
X-CHRONOS-ORIGINAL-SUMMARY:BDAY: John Doe 15.01.1990
END:VEVENT
END:VCALENDAR"""
    }


# Test configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "caldav: mark test as CalDAV integration test"
    )
    config.addinivalue_line(
        "markers", "api: mark test as API endpoint test"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
