"""
Unit tests for Chronos Engine models
"""

import pytest
from datetime import datetime, timedelta

from src.core.models import (
    ChronosEvent, 
    Priority, 
    EventType, 
    EventStatus,
    TimeSlot
)


class TestChronosEvent:
    """Test ChronosEvent model"""
    
    def test_event_creation(self):
        """Test basic event creation"""
        now = datetime.utcnow()
        event = ChronosEvent(
            title="Test Event",
            description="Test Description", 
            start_time=now,
            end_time=now + timedelta(hours=1),
            priority=Priority.HIGH
        )
        
        assert event.title == "Test Event"
        assert event.description == "Test Description"
        assert event.priority == Priority.HIGH
        assert event.duration == timedelta(hours=1)
        assert event.id is not None
    
    def test_duration_calculation(self):
        """Test duration property"""
        now = datetime.utcnow()
        event = ChronosEvent(
            title="Duration Test",
            start_time=now,
            end_time=now + timedelta(hours=2, minutes=30)
        )
        
        expected_duration = timedelta(hours=2, minutes=30)
        assert event.duration == expected_duration
    
    def test_total_time_needed(self):
        """Test total time calculation including prep and buffer"""
        now = datetime.utcnow()
        event = ChronosEvent(
            title="Total Time Test",
            start_time=now,
            end_time=now + timedelta(hours=1),
            preparation_time=timedelta(minutes=15),
            buffer_time=timedelta(minutes=10)
        )
        
        expected_total = timedelta(hours=1, minutes=25)
        assert event.total_time_needed == expected_total
    
    def test_is_flexible(self):
        """Test event flexibility detection"""
        task_event = ChronosEvent(
            title="Flexible Task",
            event_type=EventType.TASK
        )
        
        meeting_event = ChronosEvent(
            title="Fixed Meeting", 
            event_type=EventType.MEETING
        )
        
        assert task_event.is_flexible() is True
        assert meeting_event.is_flexible() is False
    
    def test_conflicts_with(self):
        """Test conflict detection between events"""
        base_time = datetime.utcnow()
        
        event1 = ChronosEvent(
            title="Event 1",
            start_time=base_time,
            end_time=base_time + timedelta(hours=2)
        )
        
        # Overlapping event
        event2 = ChronosEvent(
            title="Event 2", 
            start_time=base_time + timedelta(hours=1),
            end_time=base_time + timedelta(hours=3)
        )
        
        # Non-overlapping event
        event3 = ChronosEvent(
            title="Event 3",
            start_time=base_time + timedelta(hours=3),
            end_time=base_time + timedelta(hours=4)
        )
        
        assert event1.conflicts_with(event2) is True
        assert event1.conflicts_with(event3) is False
    
    def test_to_dict(self):
        """Test dictionary serialization"""
        now = datetime.utcnow()
        event = ChronosEvent(
            title="Dict Test",
            start_time=now,
            end_time=now + timedelta(hours=1),
            priority=Priority.URGENT,
            tags=['test', 'urgent']
        )
        
        result = event.to_dict()
        
        assert result['title'] == "Dict Test"
        assert result['priority'] == "URGENT"
        assert result['tags'] == ['test', 'urgent']
        assert 'start_time' in result
        assert 'end_time' in result
    
    def test_from_dict(self):
        """Test dictionary deserialization"""
        now = datetime.utcnow()
        data = {
            'title': 'From Dict Test',
            'start_time': now.isoformat(),
            'end_time': (now + timedelta(hours=1)).isoformat(),
            'priority': 'HIGH',
            'event_type': 'task',
            'status': 'scheduled'
        }
        
        event = ChronosEvent.from_dict(data)
        
        assert event.title == 'From Dict Test'
        assert event.priority == Priority.HIGH
        assert event.event_type == EventType.TASK
        assert event.status == EventStatus.SCHEDULED


class TestTimeSlot:
    """Test TimeSlot model"""
    
    def test_time_slot_creation(self):
        """Test TimeSlot creation and properties"""
        start = datetime.utcnow()
        end = start + timedelta(hours=2)
        
        slot = TimeSlot(start, end)
        
        assert slot.start == start
        assert slot.end == end
        assert slot.duration == timedelta(hours=2)
        assert slot.available is True
    
    def test_overlaps_with(self):
        """Test overlap detection"""
        base_time = datetime.utcnow()
        
        slot1 = TimeSlot(
            base_time,
            base_time + timedelta(hours=2)
        )
        
        # Overlapping slot
        slot2 = TimeSlot(
            base_time + timedelta(hours=1),
            base_time + timedelta(hours=3)
        )
        
        # Adjacent slot (no overlap)
        slot3 = TimeSlot(
            base_time + timedelta(hours=2),
            base_time + timedelta(hours=4)
        )
        
        assert slot1.overlaps_with(slot2) is True
        assert slot1.overlaps_with(slot3) is False
    
    def test_contains(self):
        """Test datetime containment"""
        start = datetime.utcnow()
        end = start + timedelta(hours=2)
        slot = TimeSlot(start, end)
        
        inside_time = start + timedelta(hours=1)
        outside_time = start + timedelta(hours=3)
        
        assert slot.contains(inside_time) is True
        assert slot.contains(outside_time) is False
        assert slot.contains(start) is True
        assert slot.contains(end) is False  # End is exclusive


class TestEnums:
    """Test enum classes"""
    
    def test_priority_values(self):
        """Test Priority enum values"""
        assert Priority.LOW.value == 1
        assert Priority.MEDIUM.value == 2
        assert Priority.HIGH.value == 3
        assert Priority.URGENT.value == 4
    
    def test_event_type_values(self):
        """Test EventType enum values"""
        assert EventType.MEETING.value == "meeting"
        assert EventType.TASK.value == "task"
        assert EventType.APPOINTMENT.value == "appointment"
    
    def test_event_status_values(self):
        """Test EventStatus enum values"""
        assert EventStatus.SCHEDULED.value == "scheduled"
        assert EventStatus.COMPLETED.value == "completed"
        assert EventStatus.CANCELLED.value == "cancelled"
