"""
Unit tests for GoogleCalendarClient - Mock Implementation Tests
"""

import pytest
from datetime import datetime, timedelta

from src.core.calendar_client import GoogleCalendarClient


class TestGoogleCalendarClient:
    """Test GoogleCalendarClient mock implementation"""
    
    @pytest.fixture
    def calendar_client(self):
        """Create calendar client for testing"""
        return GoogleCalendarClient(
            credentials_file="config/credentials.json",
            token_file="config/token.json"
        )
    
    @pytest.mark.asyncio
    async def test_authentication(self, calendar_client):
        """Test mock authentication"""
        result = await calendar_client.authenticate()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_fetch_events(self, calendar_client):
        """Test fetching mock events"""
        events = await calendar_client.fetch_events(days_ahead=7)
        
        assert isinstance(events, list)
        assert len(events) > 0
        
        # Check first event structure
        if events:
            event = events[0]
            assert 'id' in event
            assert 'summary' in event
            assert 'start' in event
            assert 'end' in event
    
    @pytest.mark.asyncio
    async def test_create_event(self, calendar_client):
        """Test creating mock event"""
        event_data = {
            'summary': 'Test Event',
            'description': 'Test Description',
            'start': {'dateTime': datetime.utcnow().isoformat() + 'Z'},
            'end': {'dateTime': (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'}
        }
        
        created_event = await calendar_client.create_event(event_data)
        
        assert created_event['summary'] == 'Test Event'
        assert created_event['description'] == 'Test Description'
        assert 'id' in created_event
    
    @pytest.mark.asyncio
    async def test_update_event(self, calendar_client):
        """Test updating mock event"""
        # First create an event
        event_data = {
            'summary': 'Original Event',
            'description': 'Original Description'
        }
        
        created_event = await calendar_client.create_event(event_data)
        event_id = created_event['id']
        
        # Update the event
        update_data = {
            'summary': 'Updated Event',
            'description': 'Updated Description'
        }
        
        updated_event = await calendar_client.update_event(event_id, update_data)
        
        assert updated_event['summary'] == 'Updated Event'
        assert updated_event['description'] == 'Updated Description'
        assert updated_event['id'] == event_id
    
    @pytest.mark.asyncio
    async def test_delete_event(self, calendar_client):
        """Test deleting mock event"""
        # First create an event
        event_data = {
            'summary': 'Event to Delete',
            'description': 'Will be deleted'
        }
        
        created_event = await calendar_client.create_event(event_data)
        event_id = created_event['id']
        
        # Delete the event
        result = await calendar_client.delete_event(event_id)
        assert result is True
    
    def test_mock_event_count(self, calendar_client):
        """Test mock event count"""
        count = calendar_client.get_mock_event_count()
        assert isinstance(count, int)
        assert count > 0
    
    def test_reset_mock_events(self, calendar_client):
        """Test resetting mock events"""
        initial_count = calendar_client.get_mock_event_count()
        calendar_client.reset_mock_events()
        reset_count = calendar_client.get_mock_event_count()
        
        assert reset_count == initial_count  # Should restore initial state
