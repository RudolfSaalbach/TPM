#!/usr/bin/env python3
"""
Simple test script to create calendar entries through Chronos API
"""

import requests
import json
from datetime import datetime, timedelta

# Configuration
API_BASE = "http://localhost:8080"
API_KEY = "super-secret-change-me"

def test_calendar_api():
    """Test calendar API and create test entries"""

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

    print("Testing Chronos Calendar API...")
    print(f"API Base: {API_BASE}")

    # Test health endpoint first
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        print(f"Health Status: {response.status_code}")
        if response.status_code == 200:
            health_data = response.json()
            print(f"   Success: {health_data.get('success', 'unknown')}")
        else:
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"Health check failed: {e}")

    # Test OpenAPI docs
    try:
        response = requests.get(f"{API_BASE}/openapi.json", timeout=10)
        if response.status_code == 200:
            openapi_data = response.json()
            paths = list(openapi_data.get('paths', {}).keys())
            print(f"API Endpoints available: {len(paths)}")
            print(f"Sample paths: {paths[:10]}")
        else:
            print(f"OpenAPI not available: {response.status_code}")
    except Exception as e:
        print(f"OpenAPI check failed: {e}")

    # Test event creation
    print("\nCreating test calendar entries...")

    # Simple test event
    event = {
        "summary": "CalDAV Test Meeting",
        "description": "Test event to verify CalDAV integration",
        "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(hours=2)).isoformat(),
        "location": "Home Office"
    }

    # Try different API endpoints
    endpoints_to_try = [
        "/api/v1/events",
        "/api/v1/events/create",
        "/api/dashboard/create-event",
        "/events/create",
        "/api/v1/caldav/events"
    ]

    for endpoint in endpoints_to_try:
        try:
            print(f"Trying endpoint: {endpoint}")
            response = requests.post(
                f"{API_BASE}{endpoint}",
                headers=headers,
                json=event,
                timeout=10
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:300]}")

            if response.status_code in [200, 201]:
                print(f"   SUCCESS: Event created via {endpoint}")
                break

        except Exception as e:
            print(f"   ERROR: {e}")

    # Try to fetch events
    print("\nFetching existing events...")
    fetch_endpoints = [
        "/api/v1/events",
        "/api/dashboard/events",
        "/events",
        "/api/v1/caldav/events"
    ]

    for endpoint in fetch_endpoints:
        try:
            response = requests.get(f"{API_BASE}{endpoint}", headers=headers, timeout=10)
            print(f"GET {endpoint}: {response.status_code}")
            if response.status_code == 200:
                try:
                    events_data = response.json()
                    print(f"   Events found: {len(events_data) if isinstance(events_data, list) else 'unknown format'}")
                    if isinstance(events_data, list) and len(events_data) > 0:
                        print(f"   Sample event: {events_data[0]}")
                except:
                    print(f"   Response text: {response.text[:200]}")
                break
        except Exception as e:
            print(f"   ERROR: {e}")

def main():
    """Main function"""
    test_calendar_api()
    print("\nTest completed!")

if __name__ == "__main__":
    main()