"""
Mock Google Calendar implementation for development/testing
Separated from production calendar client for clarity
"""

import json
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path


class MockCredentials:
    """Mock credentials for development"""
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.expired = False
        self.valid = True
    
    def refresh(self, request):
        """Mock refresh"""
        pass
    
    def to_json(self) -> str:
        """Mock JSON serialization"""
        return json.dumps(self.data)


class MockCalendarService:
    """Complete mock calendar service with persistent event storage"""
    def __init__(self, credentials):
        self.credentials = credentials
        self.events_db = []  # In-memory event storage for mock
        self._initialize_sample_events()
    
    def _initialize_sample_events(self):
        """Create realistic sample events for development"""
        base_time = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
        
        # Sample events for the next 7 days
        sample_events = [
            {
                'id': 'mock_event_1',
                'summary': 'Daily Standup',
                'description': 'Team sync meeting #urgent',
                'start': {'dateTime': base_time.isoformat() + 'Z'},
                'end': {'dateTime': (base_time + timedelta(minutes=30)).isoformat() + 'Z'},
                'attendees': [{'email': 'team@example.com'}],
                'location': 'Conference Room A',
                'status': 'confirmed',
                'created': (base_time - timedelta(days=7)).isoformat() + 'Z',
                'updated': (base_time - timedelta(days=1)).isoformat() + 'Z'
            },
            {
                'id': 'mock_event_2', 
                'summary': 'Sprint Planning',
                'description': 'Plan upcoming sprint tasks',
                'start': {'dateTime': (base_time + timedelta(hours=2)).isoformat() + 'Z'},
                'end': {'dateTime': (base_time + timedelta(hours=4)).isoformat() + 'Z'},
                'attendees': [
                    {'email': 'manager@example.com'}, 
                    {'email': 'lead@example.com'}
                ],
                'location': 'Online',
                'status': 'confirmed',
                'created': (base_time - timedelta(days=5)).isoformat() + 'Z',
                'updated': (base_time - timedelta(hours=12)).isoformat() + 'Z'
            },
            {
                'id': 'mock_event_3',
                'summary': 'Focus Time - Code Review',
                'description': 'Deep work session for code review #focus',
                'start': {'dateTime': (base_time + timedelta(days=1, hours=1)).isoformat() + 'Z'},
                'end': {'dateTime': (base_time + timedelta(days=1, hours=3)).isoformat() + 'Z'},
                'attendees': [],
                'location': '',
                'status': 'confirmed',
                'created': (base_time - timedelta(days=3)).isoformat() + 'Z',
                'updated': (base_time - timedelta(days=1)).isoformat() + 'Z'
            },
            {
                'id': 'mock_event_4',
                'summary': 'Client Meeting',
                'description': 'Quarterly business review with client',
                'start': {'dateTime': (base_time + timedelta(days=2, hours=3)).isoformat() + 'Z'},
                'end': {'dateTime': (base_time + timedelta(days=2, hours=4)).isoformat() + 'Z'},
                'attendees': [
                    {'email': 'client@customer.com'},
                    {'email': 'sales@example.com'}
                ],
                'location': 'Client Office',
                'status': 'confirmed',
                'created': (base_time - timedelta(days=10)).isoformat() + 'Z',
                'updated': (base_time - timedelta(days=2)).isoformat() + 'Z'
            },
            {
                'id': 'mock_event_5',
                'summary': 'Team Retrospective',
                'description': 'Sprint retrospective and improvement planning',
                'start': {'dateTime': (base_time + timedelta(days=3, hours=2)).isoformat() + 'Z'},
                'end': {'dateTime': (base_time + timedelta(days=3, hours=3)).isoformat() + 'Z'},
                'attendees': [{'email': 'team@example.com'}],
                'location': 'Conference Room B',
                'status': 'confirmed',
                'created': (base_time - timedelta(days=8)).isoformat() + 'Z',
                'updated': (base_time - timedelta(days=3)).isoformat() + 'Z'
            }
        ]
        
        self.events_db.extend(sample_events)
    
    def events(self):
        return MockEventsResource(self.events_db)
    
    def calendarList(self):
        return MockCalendarListResource()


class MockEventsResource:
    """Mock events resource with CRUD operations"""
    def __init__(self, events_db: List[Dict[str, Any]]):
        self.events_db = events_db
    
    def list(self, **kwargs):
        return MockExecutableRequest(self.events_db, 'list', **kwargs)
    
    def insert(self, **kwargs):
        return MockExecutableRequest(self.events_db, 'insert', **kwargs)
    
    def update(self, **kwargs):
        return MockExecutableRequest(self.events_db, 'update', **kwargs)
    
    def delete(self, **kwargs):
        return MockExecutableRequest(self.events_db, 'delete', **kwargs)
    
    def get(self, **kwargs):
        return MockExecutableRequest(self.events_db, 'get', **kwargs)


class MockCalendarListResource:
    """Mock calendar list resource"""
    def list(self, **kwargs):
        return MockExecutableRequest([], 'calendar_list', **kwargs)


class MockExecutableRequest:
    """Mock executable request with realistic responses"""
    def __init__(self, events_db: List[Dict[str, Any]], operation: str, **kwargs):
        self.events_db = events_db
        self.operation = operation
        self.kwargs = kwargs
    
    def execute(self) -> Dict[str, Any]:
        """Execute mock request"""
        if self.operation == 'list':
            return self._list_events()
        elif self.operation == 'insert':
            return self._insert_event()
        elif self.operation == 'update':
            return self._update_event()
        elif self.operation == 'delete':
            return self._delete_event()
        elif self.operation == 'get':
            return self._get_event()
        elif self.operation == 'calendar_list':
            return self._get_calendar_list()
        else:
            return {}
    
    def _list_events(self) -> Dict[str, Any]:
        """List events with filtering"""
        events = self.events_db.copy()
        
        # Apply time filtering
        time_min_str = self.kwargs.get('timeMin')
        time_max_str = self.kwargs.get('timeMax')
        
        if time_min_str and time_max_str:
            time_min = datetime.fromisoformat(time_min_str.replace('Z', '+00:00'))
            time_max = datetime.fromisoformat(time_max_str.replace('Z', '+00:00'))
            
            filtered_events = []
            for event in events:
                event_start_str = event.get('start', {}).get('dateTime', '')
                if event_start_str:
                    event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                    if time_min <= event_start <= time_max:
                        filtered_events.append(event)
            
            events = filtered_events
        
        # Apply max results limit
        max_results = self.kwargs.get('maxResults', len(events))
        events = events[:max_results]
        
        return {'items': events}
    
    def _insert_event(self) -> Dict[str, Any]:
        """Insert a new event"""
        body = self.kwargs.get('body', {})
        
        # Generate new event with ID
        new_event = {
            'id': f'mock_event_{random.randint(1000, 9999)}',
            'summary': body.get('summary', 'New Event'),
            'description': body.get('description', ''),
            'start': body.get('start', {'dateTime': datetime.utcnow().isoformat() + 'Z'}),
            'end': body.get('end', {'dateTime': (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'}),
            'attendees': body.get('attendees', []),
            'location': body.get('location', ''),
            'status': 'confirmed',
            'created': datetime.utcnow().isoformat() + 'Z',
            'updated': datetime.utcnow().isoformat() + 'Z'
        }
        
        self.events_db.append(new_event)
        return new_event
    
    def _update_event(self) -> Dict[str, Any]:
        """Update an existing event"""
        event_id = self.kwargs.get('eventId')
        body = self.kwargs.get('body', {})
        
        # Find and update event
        for i, event in enumerate(self.events_db):
            if event['id'] == event_id:
                # Update fields
                for key, value in body.items():
                    if key != 'id':  # Don't allow ID changes
                        event[key] = value
                
                # Update timestamp
                event['updated'] = datetime.utcnow().isoformat() + 'Z'
                return event
        
        # Event not found - create new one
        new_event = self._insert_event()
        new_event['id'] = event_id
        return new_event
    
    def _delete_event(self) -> Dict[str, Any]:
        """Delete an event"""
        event_id = self.kwargs.get('eventId')
        
        # Remove event from database
        self.events_db[:] = [e for e in self.events_db if e['id'] != event_id]
        return {}  # Google Calendar delete returns empty response
    
    def _get_event(self) -> Dict[str, Any]:
        """Get a specific event"""
        event_id = self.kwargs.get('eventId')
        
        # Find event
        for event in self.events_db:
            if event['id'] == event_id:
                return event
        
        # Event not found - raise equivalent of 404
        raise Exception(f"Event {event_id} not found")
    
    def _get_calendar_list(self) -> Dict[str, Any]:
        """Get calendar list"""
        return {
            'items': [
                {
                    'id': 'primary',
                    'summary': 'Primary Calendar',
                    'description': 'Your main calendar',
                    'accessRole': 'owner'
                },
                {
                    'id': 'mock_calendar_2',
                    'summary': 'Work Calendar',
                    'description': 'Work-related events',
                    'accessRole': 'owner'
                }
            ]
        }
