#!/usr/bin/env python3
"""
SYSTEMATISCHE SCHEMA-ANALYSE: DB vs Code Erwartungen
Erfasse ALLE verfügbaren Felder komplett bevor Tests
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.database import db_service
from src.core.models import TemplateDB, ChronosEventDB
from sqlalchemy import select, inspect

async def analyze_all_schemas():
    """Systematische Analyse aller DB-Schemas vs Code-Erwartungen"""
    print("=== VOLLSTÄNDIGE SCHEMA-ANALYSE ===")

    try:
        await db_service.create_tables()

        async with db_service.get_session() as session:

            # 1. TemplateDB Schema analysieren
            print("\n1. TEMPLATE DB SCHEMA:")
            template_query = select(TemplateDB).limit(1)
            template_result = await session.execute(template_query)
            template = template_result.scalars().first()

            if template:
                db_fields = [attr for attr in dir(template) if not attr.startswith('_') and not callable(getattr(template, attr, None))]
                print(f"   DB verfügbare Felder: {sorted(db_fields)}")

                # Detailierte Feldanalyse
                for field in sorted(db_fields):
                    if field not in ['metadata', 'registry']:
                        try:
                            value = getattr(template, field)
                            print(f"   {field:20} = {type(value).__name__:15} | {str(value)[:50]}")
                        except Exception as e:
                            print(f"   {field:20} = ERROR: {e}")

            # 2. Event DB Schema analysieren
            print("\n2. EVENT DB SCHEMA:")
            event_query = select(ChronosEventDB).limit(1)
            event_result = await session.execute(event_query)
            event = event_result.scalars().first()

            if event:
                db_fields = [attr for attr in dir(event) if not attr.startswith('_') and not callable(getattr(event, attr, None))]
                print(f"   DB verfügbare Felder: {sorted(db_fields)}")

                # Detailierte Feldanalyse
                for field in sorted(db_fields):
                    if field not in ['metadata', 'registry']:
                        try:
                            value = getattr(event, field)
                            print(f"   {field:20} = {type(value).__name__:15} | {str(value)[:50]}")
                        except Exception as e:
                            print(f"   {field:20} = ERROR: {e}")

            # 3. SQLAlchemy Tabellen-Schema direkt prüfen
            print("\n3. SQLALCHEMY TABLE SCHEMAS:")
            inspector = inspect(db_service.engine)

            # Template Tabelle
            print("   TEMPLATES Tabelle:")
            template_columns = inspector.get_columns('templates')
            for col in template_columns:
                print(f"   {col['name']:20} | {str(col['type']):15} | nullable: {col['nullable']}")

            # Events Tabelle
            print("\n   EVENTS Tabelle:")
            event_columns = inspector.get_columns('events')
            for col in event_columns:
                print(f"   {col['name']:20} | {str(col['type']):15} | nullable: {col['nullable']}")

    except Exception as e:
        print(f"Schema analysis error: {e}")

    await db_service.close()

if __name__ == "__main__":
    asyncio.run(analyze_all_schemas())