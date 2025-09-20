"""
Main Scheduler for Chronos Engine v2.1 - Clean Version
Core scheduling functionality without corrupted code
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from src.core.models import ChronosEvent, ChronosEventDB, Priority, EventStatus
from src.core.database import db_service
from src.core.calendar_client import GoogleCalendarClient
from src.core.event_parser import EventParser
from src.core.analytics_engine import AnalyticsEngine
from src.core.ai_optimizer import AIOptimizer
from src.core.timebox_engine import TimeboxEngine
from src.core.replan_engine import ReplanEngine
from src.core.notification_engine import NotificationEngine
from src.core.task_queue import TaskQueue
from src.core.plugin_manager import PluginManager
from src.core.calendar_repairer import CalendarRepairer


class ChronosScheduler:
    """Main scheduler for Chronos Engine"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.last_sync_time = None

        # Initialize components
        self.calendar_client = GoogleCalendarClient(
            config.get('calendar', {}).get('credentials_file', 'config/credentials.json'),
            config.get('calendar', {}).get('token_file', 'config/token.json')
        )

        self.event_parser = EventParser()
        self.task_queue = TaskQueue(config.get('task_queue', {}).get('max_concurrent_tasks', 5))
        self.plugins = PluginManager(config.get('plugins', {}))

        # Optional components
        self.analytics = AnalyticsEngine(config.get('analytics', {}))
        self.ai_optimizer = AIOptimizer(config.get('ai', {}))
        self.timebox = TimeboxEngine(config.get('ai', {}).get('timebox', {}))
        self.notifications = NotificationEngine(config.get('notifications', {}))

        # Calendar Repairer - must run BEFORE other enrichers
        self.calendar_repairer = CalendarRepairer(config, self.calendar_client)

        # ReplanEngine needs analytics and timebox engines
        try:
            self.replan = ReplanEngine(self.analytics, self.timebox)
        except Exception as e:
            self.logger.warning(f"Could not initialize ReplanEngine: {e}")
            self.replan = None

        self.logger.info("Chronos Scheduler initialized")

    async def start(self):
        """Start the scheduler"""
        if self.is_running:
            return

        self.logger.info("Starting Chronos Scheduler...")

        try:
            # Start components
            await self.task_queue.start()
            await self.plugins.initialize()

            # Start background tasks
            self.is_running = True

            # Schedule periodic sync
            sync_interval = self.config.get('scheduler', {}).get('sync_interval', 300)
            asyncio.create_task(self._periodic_sync(sync_interval))

            self.logger.info("Chronos Scheduler started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {e}")
            raise

    async def stop(self):
        """Stop the scheduler"""
        self.logger.info("Stopping Chronos Scheduler...")

        self.is_running = False

        try:
            await self.task_queue.stop()
            await self.plugins.cleanup()

            self.logger.info("Chronos Scheduler stopped")

        except Exception as e:
            self.logger.error(f"Error stopping scheduler: {e}")

    async def _periodic_sync(self, interval: int):
        """Periodic calendar synchronization"""
        while self.is_running:
            try:
                await self.sync_calendar()
                await asyncio.sleep(interval)
            except Exception as e:
                self.logger.error(f"Error in periodic sync: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def sync_calendar(self, days_ahead: int = 7, force_refresh: bool = False) -> Dict[str, Any]:
        """Synchronize calendar events"""
        try:
            self.logger.info(f"Starting calendar sync (days_ahead: {days_ahead})")

            # Fetch events from calendar
            events = await self.calendar_client.fetch_events(
                calendar_id='primary',
                days_ahead=days_ahead,
                max_results=250
            )

            processed_count = 0
            created_count = 0
            updated_count = 0

            # STEP 1: Calendar Repairer - repair keyword events FIRST
            repair_results = []
            if self.calendar_repairer and self.calendar_repairer.enabled:
                self.logger.info("Running Calendar Repairer before other processing...")
                try:
                    repair_results = await self.calendar_repairer.process_events(events, 'primary')
                    repaired_count = sum(1 for r in repair_results if r.patched)
                    if repaired_count > 0:
                        self.logger.info(f"Calendar Repairer processed {repaired_count} events")
                except Exception as e:
                    self.logger.error(f"Calendar Repairer failed: {e}")

            # STEP 2: Process events through normal pipeline
            for i, event_data in enumerate(events):
                try:
                    # Parse event
                    parsed_event = self.event_parser.parse_event(event_data)

                    # Apply enrichment data from CalendarRepairer if available
                    if i < len(repair_results) and repair_results[i].enrichment_data:
                        enrichment = repair_results[i].enrichment_data
                        # Merge enrichment data into parsed event
                        if 'event_type' in enrichment:
                            parsed_event.event_type = enrichment['event_type']
                        if 'tags' in enrichment:
                            parsed_event.tags.extend(enrichment['tags'])
                        if 'sub_tasks' in enrichment:
                            parsed_event.sub_tasks.extend(enrichment['sub_tasks'])

                    # Process through plugins (KeywordEnricher, command_handler, etc.)
                    processed_event = await self.plugins.process_event_through_plugins(parsed_event)

                    # Check if event was processed as command (None return = delete event)
                    if processed_event is None:
                        await self._consume_calendar_event(parsed_event)
                        processed_count += 1
                        continue

                    chronos_event = processed_event

                    # Save to database
                    async with db_service.get_session() as session:
                        existing = None
                        if chronos_event.id:
                            existing = await session.get(ChronosEventDB, chronos_event.id)

                        db_event = chronos_event.to_db_model()

                        if existing:
                            # Update existing
                            for key, value in db_event.__dict__.items():
                                if not key.startswith('_') and key != 'id':
                                    setattr(existing, key, value)
                            updated_count += 1
                        else:
                            # Create new
                            session.add(db_event)
                            created_count += 1

                        await session.commit()

                    processed_count += 1

                except Exception as e:
                    self.logger.warning(f"Error processing event {event_data.get('id', 'unknown')}: {e}")

            self.last_sync_time = datetime.utcnow()

            result = {
                'success': True,
                'events_processed': processed_count,
                'events_created': created_count,
                'events_updated': updated_count,
                'sync_time': self.last_sync_time.isoformat()
            }

            self.logger.info(f"Calendar sync completed: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Calendar sync failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'sync_time': datetime.utcnow().isoformat()
            }

    async def create_event(self, event: ChronosEvent) -> ChronosEvent:
        """Create a new event"""
        try:
            # Process through plugins
            processed_event = await self.plugins.process_event_through_plugins(event)
            if processed_event is None:
                raise ValueError("Event was consumed by plugins and cannot be created")
            event = processed_event

            # Save to database
            async with db_service.get_session() as session:
                db_event = event.to_db_model()
                session.add(db_event)
                await session.commit()

            # Sync to Google Calendar
            try:
                await self.calendar_client.create_event(event)
                self.logger.info(f"Event synced to Google Calendar: {event.title}")
            except Exception as e:
                self.logger.warning(f"Failed to sync event to Google Calendar: {e}")

            return event

        except Exception as e:
            self.logger.error(f"Failed to create event: {e}")
            raise

    async def _consume_calendar_event(self, event: ChronosEvent):
        """Remove events that were transformed into commands"""
        event_id = event.id
        calendar_identifier = event.calendar_id or 'primary'

        if event_id:
            try:
                async with db_service.get_session() as session:
                    existing = await session.get(ChronosEventDB, event_id)
                    if existing:
                        await session.delete(existing)
                        self.logger.info(f"Removed command event {event_id} from database")
                    await session.commit()
            except Exception as db_error:
                self.logger.warning(f"Failed to remove command event {event_id} from database: {db_error}")

            try:
                await self.calendar_client.delete_event(event_id, calendar_id=calendar_identifier or 'primary')
                self.logger.info(f"Removed command event {event_id} from calendar")
            except Exception as api_error:
                self.logger.warning(f"Failed to delete calendar event {event_id}: {api_error}")
        else:
            self.logger.debug("Command event without identifier received; skipping deletion")

    async def get_health_status(self) -> Dict[str, Any]:
        """Get scheduler health status"""
        return {
            "status": "healthy",
            "is_running": self.is_running,
            "timebox_enabled": self.timebox is not None,
            "replan_enabled": self.replan is not None,
            "analytics_enabled": self.analytics is not None,
            "last_sync": self.last_sync_time.isoformat() if self.last_sync_time else None
        }