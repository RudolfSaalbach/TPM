#!/usr/bin/env python3
"""
MINI-TEST: TemplateDB.usage Relationship Problem isoliert analysieren
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.database import db_service
from src.core.models import TemplateDB
from sqlalchemy import select

async def debug_template_usage():
    """Debug TemplateDB.usage relationship"""
    print("=== TEMPLATE USAGE DEBUG ===")

    try:
        await db_service.create_tables()

        async with db_service.get_session() as session:
            # Get one template from database
            query = select(TemplateDB).limit(1)
            result = await session.execute(query)
            template = result.scalars().first()

            if template:
                print(f"Template found: {template.title}")
                print(f"Template attributes: {[attr for attr in dir(template) if not attr.startswith('_')]}")

                # Test access to usage attribute
                try:
                    usage = template.usage
                    print(f"Usage attribute exists: {usage}")
                    print(f"Usage type: {type(usage)}")
                    print(f"Usage count: {len(usage) if usage else 0}")
                except AttributeError as e:
                    print(f"ERROR: {e}")
                    print("Available relationships:")
                    for attr in dir(template):
                        if not attr.startswith('_'):
                            try:
                                val = getattr(template, attr)
                                print(f"  {attr}: {type(val)}")
                            except:
                                print(f"  {attr}: <error accessing>")

            else:
                print("No templates found in database")

    except Exception as e:
        print(f"Database error: {e}")

    await db_service.close()

if __name__ == "__main__":
    asyncio.run(debug_template_usage())