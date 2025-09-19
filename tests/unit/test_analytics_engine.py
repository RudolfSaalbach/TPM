"""Unit tests for the AnalyticsEngine."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.core.analytics_engine import AnalyticsEngine
from src.core.database import db_service
from src.core.models import (
    AnalyticsDataDB,
    ChronosEvent,
    ChronosEventDB,
    EventStatus,
    EventType,
    Priority,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_track_event_persists_metrics(analytics_engine: AnalyticsEngine, setup_test_db):
    event = ChronosEvent(
        id="track_test",
        title="Test Event",
        start_time=_utc_now(),
        end_time=_utc_now() + timedelta(hours=1),
        priority=Priority.HIGH,
        event_type=EventType.MEETING,
    )

    await analytics_engine.track_event(event)

    async with db_service.get_session() as session:
        result = await session.execute(select(AnalyticsDataDB))
        stored = result.scalars().all()

    assert len(stored) == 1
    assert stored[0].event_id == event.id
    assert stored[0].metrics["duration_hours"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_get_productivity_metrics_aggregates_data(analytics_engine: AnalyticsEngine, setup_test_db):
    now = _utc_now()
    event_completed = ChronosEvent(
        id="completed",
        title="Completed Work",
        start_time=now - timedelta(days=1),
        end_time=now - timedelta(days=1) + timedelta(hours=2),
        priority=Priority.MEDIUM,
        event_type=EventType.TASK,
        status=EventStatus.COMPLETED,
    )
    event_scheduled = ChronosEvent(
        id="scheduled",
        title="Upcoming Meeting",
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=3),
        priority=Priority.LOW,
        event_type=EventType.MEETING,
        status=EventStatus.SCHEDULED,
    )

    async with db_service.get_session() as session:
        session.add(event_completed.to_db_model())
        session.add(event_scheduled.to_db_model())
        await session.commit()

    # Track analytics for the completed event to provide productivity data
    await analytics_engine.track_event(event_completed)

    metrics = await analytics_engine.get_productivity_metrics(days_back=7)

    assert metrics["total_events"] == 1
    assert metrics["completed_events"] == 1
    assert metrics["completion_rate"] == pytest.approx(1.0)
    assert metrics["total_hours"] > 0


@pytest.mark.asyncio
async def test_generate_insights_handles_empty_database(analytics_engine: AnalyticsEngine, setup_test_db):
    insights = await analytics_engine.generate_insights(days_back=7)

    assert isinstance(insights, list)
    # With no events we expect a fallback insight
    assert isinstance(insights, list)
    # With no data we still receive informational guidance
    assert insights[0]


def test_calculate_event_metrics_contains_expected_keys(analytics_engine: AnalyticsEngine):
    event = ChronosEvent(
        id="metrics",
        title="Metrics Test",
        start_time=_utc_now(),
        end_time=_utc_now() + timedelta(hours=2),
        priority=Priority.URGENT,
        event_type=EventType.TASK,
        status=EventStatus.IN_PROGRESS,
        requires_focus=True,
    )

    metrics = analytics_engine._calculate_event_metrics(event)

    assert metrics["duration_hours"] == pytest.approx(2.0)
    assert metrics["priority_score"] == 4.0
    assert metrics["type_score"] == 3.0
    assert metrics["requires_focus"] == 1.0
