import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from plugins.custom.command_handler_plugin import CommandHandlerPlugin
from src.core.models import (
    ChronosEvent,
    Priority,
    EventType,
    EventStatus,
    NoteDB,
    URLPayloadDB,
    ExternalCommandDB,
    CommandStatus,
)
from src.core.database import db_service


def build_event(title: str) -> ChronosEvent:
    now = datetime.utcnow().replace(microsecond=0)
    identifier = title.split()[0].lower().rstrip(":")
    return ChronosEvent(
        id=f"evt-{identifier}",
        title=title,
        description="Automated command event",
        start_time=now,
        end_time=now + timedelta(hours=1),
        calendar_id="primary",
        priority=Priority.MEDIUM,
        event_type=EventType.TASK,
        status=EventStatus.SCHEDULED,
        attendees=["operator@example.com"],
        tags=["automation"],
    )


@pytest.mark.asyncio
async def test_notiz_command_persists_note_and_consumes_event(setup_test_db):
    plugin = CommandHandlerPlugin()
    await plugin.initialize({"config": {"command_handler": {"action_whitelist": ["RUN_BACKUP"]}}})

    event = build_event("NOTIZ: Follow up with vendor")

    result = await plugin.process_event(event)

    assert result is None

    async with db_service.get_session() as session:
        rows = await session.execute(select(NoteDB))
        notes = rows.scalars().all()

    assert len(notes) == 1
    note = notes[0]
    assert note.content == "Follow up with vendor"
    assert note.event_details["title"] == event.title
    assert note.calendar_id == event.calendar_id


@pytest.mark.asyncio
async def test_url_command_persists_payload_and_consumes_event(setup_test_db):
    plugin = CommandHandlerPlugin()
    await plugin.initialize({"config": {"command_handler": {"action_whitelist": ["RUN_BACKUP"]}}})

    event = build_event("URL: https://example.com Useful link")

    result = await plugin.process_event(event)

    assert result is None

    async with db_service.get_session() as session:
        rows = await session.execute(select(URLPayloadDB))
        payloads = rows.scalars().all()

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload.url == "https://example.com"
    assert payload.title == "Useful link"
    assert payload.event_details["tags"] == event.tags


@pytest.mark.asyncio
async def test_action_command_requires_whitelist(setup_test_db):
    plugin = CommandHandlerPlugin()
    await plugin.initialize({"config": {"command_handler": {"action_whitelist": ["RUN_BACKUP"]}}})

    permitted_event = build_event("ACTION: RUN_BACKUP n8n nightly")
    blocked_event = build_event("ACTION: DELETE_ALL n8n now")

    permitted_result = await plugin.process_event(permitted_event)
    blocked_result = await plugin.process_event(blocked_event)

    assert permitted_result is None
    assert blocked_result is blocked_event

    async with db_service.get_session() as session:
        rows = await session.execute(select(ExternalCommandDB))
        commands = rows.scalars().all()

    assert len(commands) == 1
    command = commands[0]
    assert command.command == "RUN_BACKUP"
    assert command.target_system == "n8n"
    assert command.status == CommandStatus.PENDING.value
    assert command.parameters["args"] == ["nightly"]
    assert command.parameters["event_context"]["calendar_id"] == permitted_event.calendar_id
