#!/usr/bin/env python3
"""
MINI-TEST: Isolierte Ursachenanalyse für 'str' object has no attribute 'name'
Teste was die Datenbank tatsächlich zurückgibt ohne die gesamte API zu beeinflussen
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.database import db_service
from src.core.models import ChronosEventDB
from sqlalchemy import select

async def debug_enum_issue():
    """Debug what the database actually returns for enum fields"""
    print("=== ENUM DEBUG TEST ===")

    try:
        await db_service.create_tables()

        async with db_service.get_session() as session:
            # Get one event from database
            query = select(ChronosEventDB).limit(1)
            result = await session.execute(query)
            event = result.scalars().first()

            if event:
                print(f"Event found: {event.title}")
                print(f"Priority type: {type(event.priority)} = {event.priority}")
                print(f"Event_type type: {type(event.event_type)} = {event.event_type}")
                print(f"Status type: {type(event.status)} = {event.status}")

                # Test .name access
                try:
                    print(f"Priority.name: {event.priority.name}")
                except AttributeError as e:
                    print(f"ERROR accessing priority.name: {e}")

                try:
                    print(f"Event_type.name: {event.event_type.name}")
                except AttributeError as e:
                    print(f"ERROR accessing event_type.name: {e}")

                try:
                    print(f"Status.name: {event.status.name}")
                except AttributeError as e:
                    print(f"ERROR accessing status.name: {e}")

            else:
                print("No events found in database")

    except Exception as e:
        print(f"Database error: {e}")

    await db_service.close()

if __name__ == "__main__":
    asyncio.run(debug_enum_issue())