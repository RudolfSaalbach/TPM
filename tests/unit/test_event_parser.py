"""
Unit tests for EventParser
"""

from datetime import datetime, timedelta, timezone

from src.core.event_parser import EventParser
from src.core.models import Priority, EventType


class TestEventParser:
    """Test EventParser functionality"""
    
    def test_parse_basic_event(self, event_parser, sample_calendar_event):
        """Test parsing a basic calendar event"""
        result = event_parser.parse_event(sample_calendar_event)
        
        assert result.title == "Team Meeting"
        assert result.description == "Weekly team sync #urgent"
        assert result.location == "Conference Room A"
        assert len(result.attendees) == 1
        assert result.attendees[0] == "team@example.com"
    
    def test_priority_detection(self, event_parser):
        """Test priority detection from content"""
        # Test urgent priority
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        urgent_event = {
            'id': 'urgent_test',
            'summary': 'URGENT: Fix production issue',
            'description': 'Critical system failure',
            'start': {'dateTime': now.isoformat() + 'Z'},
            'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'}
        }

        result = event_parser.parse_event(urgent_event)
        assert result.priority == Priority.URGENT

        # Test low priority
        low_event = {
            'id': 'low_test',
            'summary': 'Optional team lunch sometime',
            'description': 'Casual social event with optional attendance',
            'start': {'dateTime': now.isoformat() + 'Z'},
            'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'}
        }
        
        result = event_parser.parse_event(low_event)
        assert result.priority == Priority.LOW
    
    def test_event_type_detection(self, event_parser):
        """Test event type detection"""
        # Test meeting detection
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        meeting_event = {
            'id': 'meeting_test',
            'summary': 'Team meeting with stakeholders',
            'description': 'Weekly sync call',
            'start': {'dateTime': now.isoformat() + 'Z'},
            'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'}
        }

        result = event_parser.parse_event(meeting_event)
        assert result.event_type == EventType.MEETING
        
        # Test task detection
        task_event = {
            'id': 'task_test',
            'summary': 'Complete project documentation',
            'description': 'Work on finishing the docs',
            'start': {'dateTime': now.isoformat() + 'Z'},
            'end': {'dateTime': (now + timedelta(hours=2)).isoformat() + 'Z'}
        }
        
        result = event_parser.parse_event(task_event)
        assert result.event_type == EventType.TASK
    
    def test_tag_extraction(self, event_parser):
        """Test hashtag extraction from description"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        tagged_event = {
            'id': 'tag_test',
            'summary': 'Tagged Event',
            'description': 'Event with #urgent #priority #project tags',
            'start': {'dateTime': now.isoformat() + 'Z'},
            'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'}
        }
        
        result = event_parser.parse_event(tagged_event)
        assert 'urgent' in result.tags
        assert 'priority' in result.tags
        assert 'project' in result.tags
    
    def test_datetime_parsing(self, event_parser):
        """Test datetime parsing variations"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Test with Z timezone
        event_z = {
            'id': 'datetime_test',
            'summary': 'DateTime Test',
            'start': {'dateTime': now.isoformat() + 'Z'},
            'end': {'dateTime': (now + timedelta(hours=1)).isoformat() + 'Z'}
        }
        
        result = event_parser.parse_event(event_z)
        assert result.start_time is not None
        assert result.end_time is not None
        
        # Test all-day event
        all_day_event = {
            'id': 'allday_test', 
            'summary': 'All Day Event',
            'start': {'date': now.date().isoformat()},
            'end': {'date': (now + timedelta(days=1)).date().isoformat()}
        }
        
        result = event_parser.parse_event(all_day_event)
        assert result.start_time is not None
        assert result.end_time is not None
    
    def test_parse_events_batch(self, event_parser, mock_calendar_events):
        """Test batch parsing of events"""
        results = event_parser.parse_events_batch(mock_calendar_events)
        
        assert len(results) == len(mock_calendar_events)
        assert all(hasattr(event, 'title') for event in results)
        assert all(hasattr(event, 'id') for event in results)
    
    def test_parse_event_error_handling(self, event_parser):
        """Test error handling in event parsing"""
        # Malformed event
        malformed_event = {
            'id': 'error_test',
            'summary': 'Error Test',
            # Missing required fields
        }
        
        result = event_parser.parse_event(malformed_event)
        
        # Should still return an event object, possibly with default values
        assert result is not None
        assert hasattr(result, 'title')
        assert hasattr(result, 'id')
    
    def test_update_event_from_calendar(self, event_parser, sample_chronos_event):
        """Test updating existing ChronosEvent with new calendar data"""
        new_calendar_data = {
            'id': sample_chronos_event.id,
            'summary': 'Updated Title',
            'description': 'Updated description #high',
            'start': {'dateTime': sample_chronos_event.start_time.isoformat() + 'Z'},
            'end': {'dateTime': sample_chronos_event.end_time.isoformat() + 'Z'}
        }
        
        original_version = sample_chronos_event.version
        updated_event = event_parser.update_event_from_calendar(
            sample_chronos_event, 
            new_calendar_data
        )
        
        assert updated_event.title == 'Updated Title'
        assert updated_event.description == 'Updated description #high'
        assert updated_event.version == original_version + 1
        assert 'high' in updated_event.tags
