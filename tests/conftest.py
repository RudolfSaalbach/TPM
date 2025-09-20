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
