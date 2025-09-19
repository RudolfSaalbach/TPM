from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.database import db_service
from src.core.models import ChronosEvent, ChronosEventDB
from src.core.scheduler import ChronosScheduler


class PluginStub:
    """Minimal plugin manager replacement used for scheduler tests."""

    def __init__(self, handler):
        self._handler = handler

    async def process_event_through_plugins(self, event):
        return await self._handler(event)


@pytest.mark.asyncio
async def test_sync_calendar_updates_existing_event(setup_test_db):
    scheduler = ChronosScheduler(config={})

    async def passthrough(event):
        return event

    scheduler.plugins = PluginStub(passthrough)

    calendar_stub = SimpleNamespace(
        fetch_events=AsyncMock(),
        delete_event=AsyncMock(return_value=True),
    )
    scheduler.calendar_client = calendar_stub

    existing_event = ChronosEvent(
        id="evt-123",
        title="Original Standup",
        description="Initial agenda",
        start_time=datetime(2024, 1, 1, 9, 0),
        end_time=datetime(2024, 1, 1, 10, 0),
        calendar_id="primary",
        attendees=["old@example.com"],
    )

    async with db_service.get_session() as session:
        session.add(existing_event.to_db_model())

    updated_start = datetime(2024, 1, 2, 9, 0)
    calendar_stub.fetch_events.return_value = [
        {
            "id": "evt-123",
            "summary": "Updated Standup",
            "description": "Refined discussion points",
            "start": {"dateTime": "2024-01-02T09:00:00Z"},
            "end": {"dateTime": "2024-01-02T10:00:00Z"},
            "organizer": {"email": "primary"},
            "attendees": [{"email": "new@example.com"}],
            "location": "Board Room",
        }
    ]

    result = await scheduler.sync_calendar()

    assert result["events_updated"] == 1
    assert result["events_created"] == 0

    async with db_service.get_session() as session:
        stored = await session.get(ChronosEventDB, "evt-123")

    assert stored is not None
    assert stored.title == "Updated Standup"
    assert stored.description == "Refined discussion points"
    assert stored.start_utc == updated_start
    assert stored.end_utc == updated_start + timedelta(hours=1)
    assert stored.attendees == ["new@example.com"]


@pytest.mark.asyncio
async def test_sync_calendar_consumes_command_events(setup_test_db):
    scheduler = ChronosScheduler(config={})

    async def consume(_event):
        return None

    scheduler.plugins = PluginStub(consume)

    calendar_stub = SimpleNamespace(
        fetch_events=AsyncMock(),
        delete_event=AsyncMock(return_value=True),
    )
    scheduler.calendar_client = calendar_stub

    command_event = ChronosEvent(
        id="cmd-42",
        title="ACTION: RUN_BACKUP n8n full",
        description="Trigger nightly backup",
        start_time=datetime(2024, 1, 3, 8, 0),
        end_time=datetime(2024, 1, 3, 9, 0),
        calendar_id="primary",
    )

    async with db_service.get_session() as session:
        session.add(command_event.to_db_model())

    calendar_stub.fetch_events.return_value = [
        {
            "id": "cmd-42",
            "summary": "ACTION: RUN_BACKUP n8n full",
            "description": "Trigger nightly backup",
            "start": {"dateTime": "2024-01-03T08:00:00Z"},
            "end": {"dateTime": "2024-01-03T09:00:00Z"},
            "organizer": {"email": "primary"},
            "attendees": [],
            "location": "",
        }
    ]

    result = await scheduler.sync_calendar()

    assert result["events_processed"] == 1
    assert result["events_created"] == 0
    assert result["events_updated"] == 0

    async with db_service.get_session() as session:
        deleted = await session.get(ChronosEventDB, "cmd-42")

    assert deleted is None
    calendar_stub.delete_event.assert_awaited_once_with("cmd-42", calendar_id="primary")
