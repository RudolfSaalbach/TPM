#!/usr/bin/env python3
"""
Erstelle je einen Testeintrag für jeden konfigurierten Kalender
Nutzt die bestehende CalDAV-Adapter und Source-Manager Infrastruktur
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.config.config_loader import load_config
from src.core.calendar_source_manager import CalendarSourceManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def create_test_events():
    """Erstelle für jeden Kalender einen passenden Testeintrag"""
    try:
        logger.info("=" * 60)
        logger.info("Erstelle Test-Events für alle Kalender")
        logger.info("=" * 60)

        # Konfiguration laden
        config = load_config()
        source_manager = CalendarSourceManager(config)

        # Alle Kalender abrufen
        calendars = await source_manager.list_calendars()
        if not calendars:
            logger.error("Keine Kalender gefunden!")
            return

        adapter = source_manager.get_adapter()

        # Test-Events für jeden Kalender erstellen
        for i, calendar in enumerate(calendars):
            logger.info(f"\nErstelle Event für Kalender: {calendar.alias} ({calendar.id})")

            # Basis-Zeit für Events (heute + i Tage)
            base_time = datetime.utcnow() + timedelta(days=i+1)

            # Kalender-spezifische Event-Daten
            if calendar.id == "automation":
                event_data = {
                    'summary': '🤖 Automation Test - System Check',
                    'description': 'Automatisiertes Test-Event für den Automation-Kalender.\nSystemüberwachung und -wartung.',
                    'start_time': base_time.replace(hour=9, minute=0, second=0, microsecond=0),
                    'end_time': base_time.replace(hour=10, minute=0, second=0, microsecond=0),
                    'all_day': False,
                    'calendar_id': calendar.id
                }
            elif calendar.id == "dates":
                event_data = {
                    'summary': '📅 Dates Test - Wichtiger Termin',
                    'description': 'Test-Event für den Dates-Kalender.\nWichtige Termine und Erinnerungen.',
                    'start_time': base_time.replace(hour=14, minute=30, second=0, microsecond=0),
                    'end_time': base_time.replace(hour=15, minute=30, second=0, microsecond=0),
                    'all_day': False,
                    'calendar_id': calendar.id
                }
            elif calendar.id == "special":
                event_data = {
                    'summary': '⭐ Special Test - Besonderes Event',
                    'description': 'Test-Event für den Special-Kalender.\nBesondere Anlässe und Events.',
                    'start_time': base_time.replace(hour=18, minute=0, second=0, microsecond=0),
                    'end_time': base_time.replace(hour=19, minute=0, second=0, microsecond=0),
                    'all_day': False,
                    'calendar_id': calendar.id
                }
            else:
                # Fallback für unbekannte Kalender
                event_data = {
                    'summary': f'🔧 Test Event - {calendar.alias}',
                    'description': f'Test-Event für Kalender {calendar.alias}.\nAllgemeiner Test-Eintrag.',
                    'start_time': base_time.replace(hour=12, minute=0, second=0, microsecond=0),
                    'end_time': base_time.replace(hour=13, minute=0, second=0, microsecond=0),
                    'all_day': False,
                    'calendar_id': calendar.id
                }

            try:
                # Event erstellen
                event_uid = await adapter.create_event(calendar, event_data)

                logger.info(f"✅ Event erfolgreich erstellt:")
                logger.info(f"   Kalender: {calendar.alias}")
                logger.info(f"   UID: {event_uid}")
                logger.info(f"   Titel: {event_data['summary']}")
                logger.info(f"   Zeit: {event_data['start_time'].strftime('%Y-%m-%d %H:%M')}")

            except Exception as e:
                logger.error(f"❌ Fehler beim Erstellen des Events für {calendar.alias}: {e}")

        logger.info("\n" + "=" * 60)
        logger.info("Test-Event Erstellung abgeschlossen")
        logger.info("=" * 60)

        # Verbindung schließen
        await source_manager.close()

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Test-Events: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(create_test_events())
