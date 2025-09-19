"""Common pytest fixtures for Chronos Engine tests."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
import pytest_asyncio

from src.core.database import db_service
from src.core.event_parser import EventParser
from src.core.models import Base, ChronosEvent, EventStatus, EventType, Priority


def _utc_now_naive() -> datetime:
    """Return a timezone-naive UTC timestamp without using datetime.utcnow."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture(scope="session")
def event_loop():
    """Provide a dedicated event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_calendar_event():
    """Sample calendar event payload resembling Google Calendar output."""
    now = _utc_now_naive()
    return {
        "id": "test_event_1",
        "summary": "Team Meeting",
        "description": "Weekly team sync #urgent",
        "start": {"dateTime": f"{now.isoformat()}Z"},
        "end": {"dateTime": f"{(now + timedelta(hours=1)).isoformat()}Z"},
        "attendees": [{"email": "team@example.com"}],
        "location": "Conference Room A",
    }


@pytest.fixture
def sample_chronos_event() -> ChronosEvent:
    """A pre-populated ChronosEvent instance for mutation tests."""
    now = _utc_now_naive()
    return ChronosEvent(
        id="test_chronos_1",
        title="Sample Task",
        description="Test task for unit testing",
        start_time=now,
        end_time=now + timedelta(hours=2),
        priority=Priority.HIGH,
        event_type=EventType.TASK,
        status=EventStatus.SCHEDULED,
        tags=["test", "sample"],
    )


@pytest.fixture
def sample_events_list() -> List[ChronosEvent]:
    """Generate a small list of scheduled ChronosEvent objects."""
    now = _utc_now_naive()
    events = []
    for i in range(5):
        events.append(
            ChronosEvent(
                id=f"test_event_{i}",
                title=f"Test Event {i}",
                description=f"Test event number {i}",
                start_time=now + timedelta(hours=i),
                end_time=now + timedelta(hours=i + 1),
                priority=Priority.MEDIUM,
                event_type=EventType.TASK,
                status=EventStatus.SCHEDULED,
            )
        )
    return events


@pytest_asyncio.fixture
async def setup_test_db():
    """Ensure a clean database schema before and after a test."""
    async with db_service.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with db_service.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def analytics_engine():
    """Analytics engine instance pointing to the shared test DB."""
    from src.core.analytics_engine import AnalyticsEngine

    return AnalyticsEngine()


@pytest.fixture
def event_parser() -> EventParser:
    """EventParser instance for parsing calendar payloads."""
    return EventParser()


@pytest.fixture
def mock_calendar_events():
    """Generate a batch of synthetic calendar events."""
    base_time = _utc_now_naive()
    return [
        {
            "id": f"mock_event_{i}",
            "summary": f"Mock Event {i}",
            "description": f"Test event {i}",
            "start": {"dateTime": f"{(base_time + timedelta(hours=i)).isoformat()}Z"},
            "end": {"dateTime": f"{(base_time + timedelta(hours=i + 1)).isoformat()}Z"},
            "attendees": [],
            "location": "",
        }
        for i in range(3)
    ]


@pytest.fixture(autouse=True)
async def cleanup_test_data():
    """Placeholder for post-test cleanup hooks."""
    yield


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used throughout the test-suite."""
    config.addinivalue_line("markers", "asyncio: mark test as async")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
