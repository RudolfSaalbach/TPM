"""Unit tests for core model helpers."""

from datetime import datetime, timedelta, timezone

from src.core.models import ChronosEvent, EventStatus, EventType, Priority, TimeSlot


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestChronosEvent:
    def test_duration_and_total_time(self):
        start = _utc_now()
        event = ChronosEvent(
            title="Design Review",
            start_time=start,
            end_time=start + timedelta(hours=2),
            preparation_time=timedelta(minutes=15),
            buffer_time=timedelta(minutes=5),
        )

        assert event.duration == timedelta(hours=2)
        assert event.total_time_needed == timedelta(hours=2, minutes=20)

    def test_conflicts_with_and_time_slot(self):
        start = _utc_now()
        first = ChronosEvent(
            id="one",
            title="Call",
            start_time=start,
            end_time=start + timedelta(hours=1),
        )
        second = ChronosEvent(
            id="two",
            title="Workshop",
            start_time=start + timedelta(minutes=30),
            end_time=start + timedelta(hours=2),
        )

        assert first.conflicts_with(second) is True
        assert first.get_time_slot().overlaps_with(second.get_time_slot())

    def test_to_dict_round_trip(self):
        start = _utc_now()
        event = ChronosEvent(
            id="round",
            title="Round Trip",
            description="Serialize and back",
            start_time=start,
            end_time=start + timedelta(hours=1),
            priority=Priority.URGENT,
            event_type=EventType.TASK,
            status=EventStatus.IN_PROGRESS,
            tags=["serialize"],
            flexible_timing=False,
        )

        payload = event.to_dict()
        restored = ChronosEvent.from_dict(payload)

        assert restored.id == event.id
        assert restored.priority == Priority.URGENT
        assert restored.event_type == EventType.TASK
        assert restored.status == EventStatus.IN_PROGRESS
        assert restored.tags == ["serialize"]
        assert restored.flexible_timing is False

    def test_is_flexible_flag(self):
        event = ChronosEvent(flexible_timing=False)
        assert event.is_flexible() is False
        assert ChronosEvent().is_flexible() is True

    def test_to_db_model_normalizes_utc_fields(self):
        start = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=2)

        event = ChronosEvent(
            id="utc-event",
            title="UTC Meeting",
            start_time=start,
            end_time=end,
        )

        db_event = event.to_db_model()

        assert db_event.start_utc == start.replace(tzinfo=None)
        assert db_event.end_utc == end.replace(tzinfo=None)
        assert db_event.all_day_date is None

    def test_to_db_model_detects_all_day(self):
        start = datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        event = ChronosEvent(
            id="all-day",
            title="Workshop",
            start_time=start,
            end_time=end,
        )

        db_event = event.to_db_model()

        assert db_event.start_utc == start.replace(tzinfo=None)
        assert db_event.end_utc == end.replace(tzinfo=None)
        assert db_event.all_day_date == "2024-01-02"


class TestTimeSlot:
    def test_basic_properties(self):
        start = _utc_now()
        slot = TimeSlot(start, start + timedelta(hours=2))

        assert slot.duration == timedelta(hours=2)
        assert slot.contains(start + timedelta(hours=1))
        assert slot.contains(start) is True
        assert slot.contains(start + timedelta(hours=2)) is False

    def test_overlap_detection(self):
        base = _utc_now()
        slot_a = TimeSlot(base, base + timedelta(hours=1))
        slot_b = TimeSlot(base + timedelta(minutes=30), base + timedelta(hours=2))
        slot_c = TimeSlot(base + timedelta(hours=1), base + timedelta(hours=2))

        assert slot_a.overlaps_with(slot_b) is True
        assert slot_a.overlaps_with(slot_c) is False


class TestEnums:
    def test_priority_values(self):
        assert Priority.URGENT.value == 4

    def test_event_type_values(self):
        assert EventType.MEETING.value == "meeting"

    def test_event_status_values(self):
        assert EventStatus.SCHEDULED.value == "scheduled"
