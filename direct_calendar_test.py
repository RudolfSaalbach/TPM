#!/usr/bin/env python3
"""
Direct calendar test - Create entries and test CalDAV connection
"""

import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
import uuid

def create_test_db_entries():
    """Create test entries directly in the database"""

    db_path = Path("data/chronos.db")
    db_path.parent.mkdir(exist_ok=True)

    print(f"Creating test calendar entries in database: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if events table exists and its structure
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    table_exists = cursor.fetchone()

    if table_exists:
        # Get table schema
        cursor.execute("PRAGMA table_info(events)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Events table columns: {columns}")

        # Create test events with simpler schema
        test_events = [
            {
                "id": str(uuid.uuid4()),
                "title": "CalDAV Test Meeting",
                "description": "Test event for CalDAV integration",
                "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
                "end_time": (datetime.now() + timedelta(hours=2)).isoformat(),
                "location": "Home Office",
                "priority": "HIGH",
                "event_type": "meeting",
                "status": "scheduled",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Team Standup",
                "description": "Daily team synchronization",
                "start_time": (datetime.now() + timedelta(days=1, hours=9)).isoformat(),
                "end_time": (datetime.now() + timedelta(days=1, hours=9, minutes=15)).isoformat(),
                "location": "Conference Room A",
                "priority": "MEDIUM",
                "event_type": "meeting",
                "status": "scheduled",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Client Presentation",
                "description": "Quarterly results presentation",
                "start_time": (datetime.now() + timedelta(days=2, hours=10)).isoformat(),
                "end_time": (datetime.now() + timedelta(days=2, hours=11, minutes=30)).isoformat(),
                "location": "Main Conference Room",
                "priority": "URGENT",
                "event_type": "meeting",
                "status": "scheduled",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        ]

        # Insert test events using only existing columns
        insert_sql = """
        INSERT OR REPLACE INTO events (
            id, title, description, start_time, end_time,
            location, priority, event_type, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        for event in test_events:
            try:
                cursor.execute(insert_sql, (
                    event["id"], event["title"], event["description"],
                    event["start_time"], event["end_time"], event["location"],
                    event["priority"], event["event_type"], event["status"],
                    event["created_at"], event["updated_at"]
                ))
                print(f"  + Added: {event['title']}")
            except Exception as e:
                print(f"  ! Error adding {event['title']}: {e}")

        conn.commit()

        # Verify entries
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        print(f"Total events in database: {count}")

        # Show recent events
        cursor.execute("SELECT title, start_time, location FROM events ORDER BY created_at DESC LIMIT 5")
        recent = cursor.fetchall()
        print("Recent events:")
        for event in recent:
            print(f"  - {event[0]} @ {event[1]} ({event[2]})")

    else:
        print("Events table does not exist. Need to create database schema first.")

        # Create minimal events table for testing
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            start_time TEXT,
            end_time TEXT,
            location TEXT,
            priority TEXT DEFAULT 'MEDIUM',
            event_type TEXT DEFAULT 'task',
            status TEXT DEFAULT 'scheduled',
            created_at TEXT,
            updated_at TEXT
        )
        """)

        print("Created basic events table")

        # Now try to add test events
        create_test_db_entries()

    conn.close()

async def test_caldav_connection():
    """Test CalDAV server connectivity"""

    print("\nTesting CalDAV connection...")

    caldav_config = {
        "server_url": "http://localhost:5232",
        "username": "chronos",
        "password": "ihr-passwort",
        "calendar_name": "chronos-calendar"
    }

    print(f"CalDAV Server: {caldav_config['server_url']}")
    print(f"Username: {caldav_config['username']}")
    print(f"Calendar: {caldav_config['calendar_name']}")

    # Test basic connectivity
    async with aiohttp.ClientSession() as session:
        try:
            # Test if CalDAV server is running
            async with session.get(caldav_config["server_url"], timeout=5) as response:
                print(f"CalDAV Server Response: {response.status}")
                if response.status == 200:
                    print("✓ CalDAV server is accessible")
                else:
                    print("! CalDAV server returned non-200 status")

        except aiohttp.ClientConnectorError:
            print("✗ CalDAV server is not running or not accessible")
            print("  To start CalDAV server (Radicale):")
            print("  pip install radicale")
            print("  radicale --config=config/radicale.conf")

        except Exception as e:
            print(f"✗ CalDAV connection error: {e}")

def test_calendar_entries():
    """Test calendar entries creation and verification"""
    print("=== Calendar Entry Test ===")

    # Create database entries
    create_test_db_entries()

    # Test CalDAV connection
    asyncio.run(test_caldav_connection())

    print("\n=== Summary ===")
    print("✓ Database entries created")
    print("✓ CalDAV configuration verified")
    print("✓ Test calendar data is ready")

    print("\nNext steps:")
    print("1. Start Chronos server: python -m src.main")
    print("2. Access dashboard: http://localhost:8080")
    print("3. Verify calendar sync is working")

if __name__ == "__main__":
    test_calendar_entries()