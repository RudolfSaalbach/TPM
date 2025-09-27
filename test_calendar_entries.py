#!/usr/bin/env python3
"""
Test script to create calendar entries through Chronos API
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import pytest

# Configuration
API_BASE = "http://localhost:8080"
API_KEY = "super-secret-change-me"

@pytest.mark.asyncio
async def test_calendar_api():
    """Test calendar API and create test entries"""

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Test calendar entries
    test_events = [
        {
            "summary": "🎯 CalDAV Test Meeting",
            "description": "Test event to verify CalDAV integration is working properly",
            "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
            "end_time": (datetime.now() + timedelta(hours=2)).isoformat(),
            "location": "Home Office",
            "priority": "high"
        },
        {
            "summary": "📋 Daily Standup",
            "description": "Team synchronization meeting",
            "start_time": (datetime.now() + timedelta(days=1, hours=9)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=1, hours=9, minutes=15)).isoformat(),
            "location": "Conference Room A",
            "priority": "medium"
        },
        {
            "summary": "🔬 Research Session",
            "description": "Deep dive into new technologies and frameworks",
            "start_time": (datetime.now() + timedelta(days=1, hours=14)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=1, hours=16)).isoformat(),
            "location": "Library",
            "priority": "low"
        },
        {
            "summary": "💼 Client Presentation",
            "description": "Present quarterly results to stakeholders",
            "start_time": (datetime.now() + timedelta(days=2, hours=10)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=2, hours=11, minutes=30)).isoformat(),
            "location": "Main Conference Room",
            "priority": "high"
        },
        {
            "summary": "🎉 Team Lunch",
            "description": "Monthly team building lunch",
            "start_time": (datetime.now() + timedelta(days=3, hours=12)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=3, hours=13, minutes=30)).isoformat(),
            "location": "Restaurant Bella Vista",
            "priority": "low"
        }
    ]

    async with aiohttp.ClientSession() as session:
        print("🔧 Testing Chronos Calendar API...")
        print(f"📡 API Base: {API_BASE}")

        # Test health endpoint first
        try:
            async with session.get(f"{API_BASE}/health") as response:
                health_data = await response.json()
                print(f"🏥 Health Status: {response.status}")
                print(f"   Status: {health_data.get('success', 'unknown')}")
        except Exception as e:
            print(f"❌ Health check failed: {e}")

        # Test OpenAPI docs
        try:
            async with session.get(f"{API_BASE}/openapi.json") as response:
                if response.status == 200:
                    openapi_data = await response.json()
                    paths = list(openapi_data.get('paths', {}).keys())
                    print(f"📚 API Endpoints available: {len(paths)}")
                    print(f"   Sample paths: {paths[:5]}")
        except Exception as e:
            print(f"❌ OpenAPI check failed: {e}")

        # Try direct database approach through API
        print("\n📅 Creating test calendar entries...")

        for i, event in enumerate(test_events, 1):
            try:
                # Try different API endpoints to find the right one
                endpoints_to_try = [
                    "/api/v1/events",
                    "/api/v1/events/create",
                    "/api/dashboard/create-event",
                    "/events/create"
                ]

                created = False
                for endpoint in endpoints_to_try:
                    try:
                        print(f"   🔍 Trying endpoint: {endpoint}")
                        async with session.post(
                            f"{API_BASE}{endpoint}",
                            headers=headers,
                            json=event
                        ) as response:
                            result = await response.text()
                            print(f"   📄 Response ({response.status}): {result[:200]}...")

                            if response.status in [200, 201]:
                                print(f"   ✅ Event {i} created successfully via {endpoint}")
                                created = True
                                break
                            elif response.status == 422:
                                # Try with different payload format
                                simple_event = {
                                    "title": event["summary"],
                                    "start": event["start_time"],
                                    "end": event["end_time"]
                                }
                                async with session.post(
                                    f"{API_BASE}{endpoint}",
                                    headers=headers,
                                    json=simple_event
                                ) as response2:
                                    if response2.status in [200, 201]:
                                        print(f"   ✅ Event {i} created with simple format")
                                        created = True
                                        break
                    except Exception as e:
                        print(f"   ⚠️  Endpoint {endpoint} failed: {e}")
                        continue

                if not created:
                    print(f"   ❌ Could not create event {i}: {event['summary']}")

            except Exception as e:
                print(f"   ❌ Failed to create event {i}: {e}")

        # Try to fetch events to see what was created
        print("\n📋 Fetching existing events...")
        fetch_endpoints = [
            "/api/v1/events",
            "/api/dashboard/events",
            "/events"
        ]

        for endpoint in fetch_endpoints:
            try:
                async with session.get(f"{API_BASE}{endpoint}", headers=headers) as response:
                    if response.status == 200:
                        events_data = await response.json()
                        print(f"📊 Found events via {endpoint}: {len(events_data) if isinstance(events_data, list) else 'unknown'}")
                        break
            except Exception as e:
                print(f"⚠️  Could not fetch from {endpoint}: {e}")

async def main():
    """Main function"""
    print("🚀 Starting Chronos Calendar Test...")
    await test_calendar_api()
    print("\n🏁 Test completed!")

if __name__ == "__main__":
    asyncio.run(main())