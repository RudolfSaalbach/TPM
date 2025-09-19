"""Unit tests for the AIOptimizer component."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.ai_optimizer import AIOptimizer, OptimizationSuggestion
from src.core.models import ChronosEvent, EventType, Priority


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


@pytest.fixture
def mock_analytics():
    analytics = Mock()
    analytics.get_productivity_metrics = AsyncMock(
        return_value={
            "total_events": 5,
            "completed_events": 3,
            "completion_rate": 0.6,
            "total_hours": 12,
            "average_productivity": 3.2,
            "events_per_day": 4,
        }
    )
    analytics.get_time_distribution = AsyncMock(
        return_value={hour: (3.0 if hour in {9, 10} else 0.5) for hour in range(24)}
    )
    return analytics


@pytest.fixture
def ai_optimizer(mock_analytics):
    return AIOptimizer(mock_analytics)


@pytest.fixture
def sample_events():
    base = _utc(datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0))
    return [
        ChronosEvent(
            id="event_1",
            title="Project Sync",
            start_time=base,
            end_time=base + timedelta(hours=1),
            priority=Priority.HIGH,
            event_type=EventType.MEETING,
            flexible_timing=True,
        ),
        ChronosEvent(
            id="event_2",
            title="Deep Work",
            start_time=base + timedelta(hours=2),
            end_time=base + timedelta(hours=4),
            priority=Priority.URGENT,
            event_type=EventType.TASK,
            flexible_timing=True,
        ),
    ]


@pytest.mark.asyncio
async def test_optimize_schedule_returns_suggestions(ai_optimizer, sample_events):
    suggestions = await ai_optimizer.optimize_schedule(sample_events)

    assert suggestions, "Expected at least one optimization suggestion"
    assert all(isinstance(s, OptimizationSuggestion) for s in suggestions)
    # Ensure reschedule suggestions aim for peak hours (09:00/10:00)
    reschedules = [s for s in suggestions if s.type == "reschedule"]
    assert reschedules
    assert reschedules[0].suggested_time.hour in {9, 10}


@pytest.mark.asyncio
async def test_optimize_schedule_handles_analytics_errors(ai_optimizer, mock_analytics):
    mock_analytics.get_productivity_metrics.side_effect = RuntimeError("boom")

    suggestions = await ai_optimizer.optimize_schedule([])

    assert suggestions == []


@pytest.mark.asyncio
async def test_find_optimal_time_slot_prefers_high_score(ai_optimizer):
    event = ChronosEvent(
        id="slot_test",
        title="Research",
        priority=Priority.HIGH,
        flexible_timing=True,
        estimated_duration=timedelta(hours=1),
    )
    existing = [
        ChronosEvent(
            id="existing",
            title="Morning standup",
            start_time=_utc(datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)),
            end_time=_utc(datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)),
        )
    ]
    start = _utc(datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0))
    end = start + timedelta(hours=5)

    slot = await ai_optimizer.find_optimal_time_slot(event, existing, start, end)

    assert slot is not None
    assert slot.start.hour >= 10  # avoid conflicting with existing event


@pytest.mark.asyncio
async def test_suggest_break_times_identifies_gap(ai_optimizer):
    base = _utc(datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0))
    events = [
        ChronosEvent(
            id="morning",
            title="Morning session",
            start_time=base,
            end_time=base + timedelta(hours=1),
        ),
        ChronosEvent(
            id="afternoon",
            title="Afternoon session",
            start_time=base + timedelta(hours=2),
            end_time=base + timedelta(hours=3),
        ),
    ]

    breaks = await ai_optimizer.suggest_break_times(events, base)

    assert breaks
    assert breaks[0].start >= events[0].end_time


@pytest.mark.asyncio
async def test_calculate_workload_balance(ai_optimizer):
    now = _utc(datetime.now(timezone.utc))
    events = [
        ChronosEvent(
            id="balance_1",
            title="Workshop",
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=2),
        ),
        ChronosEvent(
            id="balance_2",
            title="Planning",
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=2, hours=5),
        ),
    ]

    metrics = await ai_optimizer.calculate_workload_balance(events)

    assert metrics["total_scheduled_days"] == 2
    assert metrics["average_daily_hours"] > 0
    assert 0.0 <= metrics["balance_score"] <= 1.0
