import pytest
from datetime import datetime, timedelta
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from src.api.enhanced_routes_fixed import ChronosEnhancedRoutes
from src.core.models import (
    ChronosEvent,
    Priority,
    EventType,
    EventStatus,
    ExternalCommand,
    ExternalCommandDB,
    CommandStatus,
)
from src.core.database import db_service


class DummyScheduler:
    """Minimal scheduler stub for route initialization."""

    async def start(self):
        raise NotImplementedError


@pytest.fixture
def api_app():
    app = FastAPI()
    routes = ChronosEnhancedRoutes(scheduler=DummyScheduler(), api_key="test-key")
    app.include_router(routes.router, prefix="/api/v1")
    return app


API_HEADERS = {"Authorization": "Bearer test-key"}


async def _store_events(events):
    async with db_service.get_session() as session:
        for event in events:
            session.add(event.to_db_model())


async def _store_commands(commands):
    async with db_service.get_session() as session:
        for command in commands:
            session.add(command.to_db_model())


@pytest.mark.asyncio
async def test_get_events_future_filters_by_range(api_app, setup_test_db):
    anchor = datetime(2024, 1, 1, 9, 0, 0)
    events = [
        ChronosEvent(
            id="evt-past",
            title="Past Review",
            description="Last year's wrap-up",
            start_time=anchor - timedelta(days=2),
            end_time=anchor - timedelta(days=2) + timedelta(hours=1),
            priority=Priority.MEDIUM,
            event_type=EventType.MEETING,
            status=EventStatus.COMPLETED,
            calendar_id="primary",
        ),
        ChronosEvent(
            id="evt-future",
            title="Project Kickoff",
            description="Discuss roadmap",
            start_time=anchor + timedelta(days=1),
            end_time=anchor + timedelta(days=1, hours=2),
            priority=Priority.HIGH,
            event_type=EventType.MEETING,
            status=EventStatus.SCHEDULED,
            calendar_id="primary",
        ),
        ChronosEvent(
            id="evt-far",
            title="Planning Retreat",
            description="Strategic planning",
            start_time=anchor + timedelta(days=15),
            end_time=anchor + timedelta(days=15, hours=3),
            priority=Priority.MEDIUM,
            event_type=EventType.MEETING,
            status=EventStatus.SCHEDULED,
            calendar_id="primary",
        ),
    ]

    await _store_events(events)

    async with AsyncClient(app=api_app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/events",
            params={"anchor": "2024-01-01", "range": 7, "direction": "future"},
            headers=API_HEADERS,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "evt-future"
    assert payload["items"][0]["title"] == "Project Kickoff"


@pytest.mark.asyncio
async def test_get_events_all_supports_text_search(api_app, setup_test_db):
    anchor = datetime(2024, 1, 1, 9, 0, 0)
    events = [
        ChronosEvent(
            id="evt-sync",
            title="Weekly Sync",
            description="Project Apollo planning session",
            start_time=anchor + timedelta(days=3),
            end_time=anchor + timedelta(days=3, hours=1),
            priority=Priority.MEDIUM,
            event_type=EventType.MEETING,
            status=EventStatus.SCHEDULED,
            calendar_id="primary",
        ),
        ChronosEvent(
            id="evt-personal",
            title="Gym",
            description="Personal training",
            start_time=anchor + timedelta(days=5),
            end_time=anchor + timedelta(days=5, hours=1),
            priority=Priority.LOW,
            event_type=EventType.APPOINTMENT,
            status=EventStatus.SCHEDULED,
            calendar_id="personal",
        ),
    ]

    await _store_events(events)

    async with AsyncClient(app=api_app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/events",
            params={
                "anchor": "2024-01-01",
                "range": 30,
                "direction": "all",
                "q": "Apollo",
            },
            headers=API_HEADERS,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["id"] == "evt-sync"
    assert "Apollo" in payload["items"][0]["description"]


@pytest.mark.asyncio
async def test_command_polling_and_completion_flow(api_app, setup_test_db):
    now = datetime.utcnow().replace(microsecond=0)
    commands = [
        ExternalCommand(
            target_system="n8n",
            command="RUN_BACKUP",
            parameters={"args": ["full"]},
            status=CommandStatus.PENDING,
        ),
        ExternalCommand(
            target_system="n8n",
            command="STATUS_CHECK",
            parameters={"args": []},
            status=CommandStatus.PROCESSING,
            processed_at=now - timedelta(minutes=10),
        ),
        ExternalCommand(
            target_system="telegram",
            command="SEND_MESSAGE",
            parameters={"args": ["hello"]},
            status=CommandStatus.PENDING,
        ),
    ]

    await _store_commands(commands)

    async with AsyncClient(app=api_app, base_url="http://test") as client:
        poll_response = await client.get(
            "/api/v1/commands/n8n",
            params={"limit": 5},
            headers=API_HEADERS,
        )

        assert poll_response.status_code == 200
        poll_payload = poll_response.json()
        assert poll_payload["count"] == 2
        returned_ids = {cmd["id"] for cmd in poll_payload["commands"]}

        async with db_service.get_session() as session:
            rows = await session.execute(select(ExternalCommandDB))
            stored_commands = {cmd.id: cmd for cmd in rows.scalars().all()}

        pending_ids = [cmd.id for cmd in stored_commands.values() if cmd.target_system == "n8n"]
        assert returned_ids.issubset(set(pending_ids))

        for cmd_id in returned_ids:
            assert stored_commands[cmd_id].status == CommandStatus.PROCESSING.value
            assert stored_commands[cmd_id].processed_at is not None

        # Complete the first command
        first_command_id = next(iter(returned_ids))
        completion_payload = {"state": "ok"}
        complete_response = await client.post(
            f"/api/v1/commands/{first_command_id}/complete",
            json=completion_payload,
            headers=API_HEADERS,
        )

    assert complete_response.status_code == 200
    async with db_service.get_session() as session:
        completed = await session.get(ExternalCommandDB, first_command_id)
        assert completed.status == CommandStatus.COMPLETED.value
        assert completed.result == completion_payload

        other_system = [cmd for cmd in (await session.execute(select(ExternalCommandDB))).scalars().all() if cmd.target_system == "telegram"]
        assert other_system[0].status == CommandStatus.PENDING.value
