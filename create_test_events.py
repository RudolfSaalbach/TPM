#!/usr/bin/env python3
"""
Create test calendar entries using correct Chronos API schema
"""

import requests
import json
from datetime import datetime, timedelta

# Configuration
API_BASE = "http://localhost:8080"
API_KEY = "super-secret-change-me"

def create_test_events():
    """Create test calendar entries using proper schema"""

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

    print("Creating test calendar entries with proper schema...")

    # Test events using correct schema (title not summary!)
    test_events = [
        {
            "title": "CalDAV Test Meeting",
            "description": "Test event to verify CalDAV integration is working properly",
            "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
            "end_time": (datetime.now() + timedelta(hours=2)).isoformat(),
            "location": "Home Office",
            "priority": "HIGH",
            "event_type": "meeting",
            "status": "scheduled",
            "tags": ["test", "caldav"],
            "attendees": ["admin@chronos.local"]
        },
        {
            "title": "Daily Standup",
            "description": "Team synchronization meeting",
            "start_time": (datetime.now() + timedelta(days=1, hours=9)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=1, hours=9, minutes=15)).isoformat(),
            "location": "Conference Room A",
            "priority": "MEDIUM",
            "event_type": "meeting",
            "status": "scheduled",
            "tags": ["standup", "team"],
            "attendees": ["team@company.com"]
        },
        {
            "title": "Research Session",
            "description": "Deep dive into new technologies and frameworks",
            "start_time": (datetime.now() + timedelta(days=1, hours=14)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=1, hours=16)).isoformat(),
            "location": "Library",
            "priority": "LOW",
            "event_type": "task",
            "status": "scheduled",
            "tags": ["research", "learning"],
            "attendees": []
        },
        {
            "title": "Client Presentation",
            "description": "Present quarterly results to stakeholders",
            "start_time": (datetime.now() + timedelta(days=2, hours=10)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=2, hours=11, minutes=30)).isoformat(),
            "location": "Main Conference Room",
            "priority": "URGENT",
            "event_type": "meeting",
            "status": "scheduled",
            "tags": ["presentation", "quarterly", "stakeholders"],
            "attendees": ["client@company.com", "manager@company.com"]
        },
        {
            "title": "Team Building Lunch",
            "description": "Monthly team building activity",
            "start_time": (datetime.now() + timedelta(days=3, hours=12)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=3, hours=13, minutes=30)).isoformat(),
            "location": "Restaurant Bella Vista",
            "priority": "LOW",
            "event_type": "appointment",
            "status": "scheduled",
            "tags": ["team-building", "social"],
            "attendees": ["team@company.com"]
        }
    ]

    created_events = []

    for i, event in enumerate(test_events, 1):
        try:
            print(f"\nCreating event {i}: {event['title']}")

            response = requests.post(
                f"{API_BASE}/api/v1/events",
                headers=headers,
                json=event,
                timeout=10
            )

            print(f"   Status: {response.status_code}")

            if response.status_code == 201:
                result = response.json()
                created_events.append(result)
                print(f"   SUCCESS: Event created with ID {result.get('id', 'unknown')}")
                print(f"   Title: {result.get('title')}")
                print(f"   Start: {result.get('start_time')}")
                print(f"   Priority: {result.get('priority')}")
            else:
                print(f"   ERROR: {response.text[:500]}")

        except Exception as e:
            print(f"   EXCEPTION: {e}")

    print(f"\n=== SUMMARY ===")
    print(f"Created {len(created_events)} events successfully")

    if created_events:
        print("Event IDs created:")
        for event in created_events:
            print(f"  - {event.get('id')}: {event.get('title')}")

    # Try to fetch all events to verify
    print("\n=== FETCHING EVENTS ===")
    try:
        response = requests.get(f"{API_BASE}/api/v1/events", headers=headers, timeout=10)
        print(f"Fetch Status: {response.status_code}")

        if response.status_code == 200:
            events_data = response.json()
            if isinstance(events_data, dict) and "events" in events_data:
                events_list = events_data["events"]
                print(f"Total events in system: {len(events_list)}")
                for event in events_list[-5:]:  # Show last 5 events
                    print(f"  - {event.get('title')} ({event.get('start_time')})")
            else:
                print(f"Unexpected response format: {type(events_data)}")
        else:
            print(f"Failed to fetch events: {response.text[:200]}")

    except Exception as e:
        print(f"Exception fetching events: {e}")

def main():
    print("=== Chronos Calendar Test Event Creation ===")
    create_test_events()
    print("\n=== Test completed! ===")

if __name__ == "__main__":
    main()