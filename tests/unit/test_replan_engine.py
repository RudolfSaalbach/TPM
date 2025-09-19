"""Unit tests for the ReplanEngine."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.models import ChronosEvent, EventType, Priority, TimeSlot
from src.core.replan_engine import ConflictType, ReplanEngine


def _utc(hour: int) -> datetime:
    return datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0, tzinfo=None)


@pytest.fixture
def replan_engine():
    analytics = Mock()
    timebox = Mock()
    return ReplanEngine(analytics, timebox)


@pytest.fixture
def overlapping_events():
    start = _utc(9)
    return [
        ChronosEvent(
            id="a",
            title="Planning",
            start_time=start,
            end_time=start + timedelta(hours=1),
            priority=Priority.HIGH,
            event_type=EventType.MEETING,
        ),
        ChronosEvent(
            id="b",
            title="Review",
            start_time=start + timedelta(minutes=30),
            end_time=start + timedelta(hours=2),
            priority=Priority.MEDIUM,
            event_type=EventType.MEETING,
        ),
    ]


@pytest.mark.asyncio
async def test_detect_conflicts_reports_overlap(replan_engine: ReplanEngine, overlapping_events):
    conflicts = await replan_engine.detect_conflicts(overlapping_events)

    assert conflicts
    overlap = next(c for c in conflicts if c.type == ConflictType.OVERLAP)
    assert set(overlap.events) == {"a", "b"}
    assert overlap.severity > 0


@pytest.mark.asyncio
async def test_suggest_replanning_generates_slot(monkeypatch, replan_engine: ReplanEngine, overlapping_events):
    slot = TimeSlot(_utc(12), _utc(13))
    monkeypatch.setattr(replan_engine, "_find_alternative_slot", AsyncMock(return_value=slot))

    conflicts = await replan_engine.detect_conflicts(overlapping_events)
    suggestions = await replan_engine.suggest_replanning(conflicts, overlapping_events)

    assert suggestions
    assert suggestions[0].suggested_start == slot.start
    assert suggestions[0].event_id in {"a", "b"}


@pytest.mark.asyncio
async def test_apply_replan_suggestion_updates_event(monkeypatch, replan_engine: ReplanEngine, overlapping_events):
    slot = TimeSlot(_utc(13), _utc(14))
    monkeypatch.setattr(replan_engine, "_find_alternative_slot", AsyncMock(return_value=slot))

    conflicts = await replan_engine.detect_conflicts(overlapping_events)
    suggestions = await replan_engine.suggest_replanning(conflicts, overlapping_events)

    updated = await replan_engine.apply_replan_suggestion(suggestions[0], overlapping_events)

    assert updated is True
    target = next(e for e in overlapping_events if e.id == suggestions[0].event_id)
    assert target.start_time == slot.start
    assert target.version == 2


@pytest.mark.asyncio
async def test_auto_replan_conflicts_returns_summary(monkeypatch, replan_engine: ReplanEngine, overlapping_events):
    slot = TimeSlot(_utc(15), _utc(16))
    monkeypatch.setattr(replan_engine, "_find_alternative_slot", AsyncMock(return_value=slot))

    summary = await replan_engine.auto_replan_conflicts(overlapping_events, auto_apply=False)

    assert summary["conflicts_found"] >= 1
    assert summary["suggestions_generated"] >= 1
    assert "conflicts" in summary
