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
from src.core.event_parser import EventParser
from src.core.analytics_engine import AnalyticsEngine
from src.core.ai_optimizer import AIOptimizer
from src.core.timebox_engine import TimeboxEngine
from src.core.replan_engine import ReplanEngine
from src.core.notification_engine import NotificationEngine
from src.core.task_queue import TaskQueue
from src.core.plugin_manager import PluginManager
from src.core.calendar_repairer import CalendarRepairer
from src.core.calendar_source_manager import CalendarSourceManager


class ChronosScheduler:
    """Main scheduler for Chronos Engine"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.last_sync_time = None

        # Initialize unified calendar source manager
        self.source_manager = CalendarSourceManager(config)

        self.event_parser = EventParser()
        self.task_queue = TaskQueue(config.get('task_queue', {}).get('max_concurrent_tasks', 5))
        self.plugins = PluginManager(config.get('plugins', {}))

        # Optional components
        self.analytics = AnalyticsEngine(config.get('analytics', {}))
        self.ai_optimizer = AIOptimizer(config.get('ai', {}))
        self.timebox = TimeboxEngine(config.get('ai', {}).get('timebox', {}))
        self.notifications = NotificationEngine(config.get('notifications', {}))

        # Calendar Repairer - must run BEFORE other enrichers
        self.calendar_repairer = CalendarRepairer(config, self.source_manager)

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
        """Synchronize calendar events from all configured calendars"""
        try:
            self.logger.info(f"Starting unified calendar sync (days_ahead: {days_ahead})")

            # Get all calendars from source manager
            calendars = await self.source_manager.list_calendars()
            if not calendars:
                self.logger.warning("No calendars configured for sync")
                return {
                    'success': True,
                    'events_processed': 0,
                    'events_created': 0,
                    'events_updated': 0,
                    'sync_time': datetime.utcnow().isoformat()
                }

            total_processed = 0
            total_created = 0
            total_updated = 0
            adapter = self.source_manager.get_adapter()

            # Calculate time window for sync
            since = datetime.utcnow()
            until = since + timedelta(days=days_ahead)

            # Process each calendar
            for calendar in calendars:
                try:
                    self.logger.info(f"Syncing calendar: {calendar.alias} ({calendar.id})")

                    # Fetch events from this calendar
                    event_result = await adapter.list_events(
                        calendar=calendar,
                        since=since,
                        until=until
                    )

                    events = event_result.events
                    if not events:
                        self.logger.debug(f"No events found in calendar {calendar.alias}")
                        continue

                    processed_count = 0
                    created_count = 0
                    updated_count = 0

                    # STEP 1: Calendar Repairer - repair keyword events FIRST
                    repair_results = []
                    if self.calendar_repairer and self.calendar_repairer.enabled:
                        self.logger.info(f"Running Calendar Repairer for {calendar.alias}...")
                        try:
                            repair_results = await self.calendar_repairer.process_events(events, calendar)
                            repaired_count = sum(1 for r in repair_results if r.patched)
                            if repaired_count > 0:
                                self.logger.info(f"Calendar Repairer processed {repaired_count} events in {calendar.alias}")
                        except Exception as e:
                            self.logger.error(f"Calendar Repairer failed for {calendar.alias}: {e}")

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
                                await self._consume_calendar_event(parsed_event, calendar)
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
                            self.logger.warning(f"Error processing event {event_data.get('id', 'unknown')} in {calendar.alias}: {e}")

                    total_processed += processed_count
                    total_created += created_count
                    total_updated += updated_count

                    self.logger.info(f"Calendar {calendar.alias} sync: {processed_count} processed, {created_count} created, {updated_count} updated")

                except Exception as e:
                    self.logger.error(f"Error syncing calendar {calendar.alias}: {e}")
                    continue

            self.last_sync_time = datetime.utcnow()

            result = {
                'success': True,
                'events_processed': total_processed,
                'events_created': total_created,
                'events_updated': total_updated,
                'calendars_synced': len(calendars),
                'sync_time': self.last_sync_time.isoformat()
            }

            self.logger.info(f"Unified calendar sync completed: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Calendar sync failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'sync_time': datetime.utcnow().isoformat()
            }

    async def sync_events(self, incremental: bool = True, days_ahead: int = 7) -> Dict[str, Any]:
        """Sync events with optional incremental mode - compatibility wrapper for API"""
        try:
            if incremental:
                self.logger.info("Performing incremental sync")
                # For incremental sync, use a shorter time window
                return await self.sync_calendar(days_ahead=min(days_ahead, 30), force_refresh=False)
            else:
                self.logger.info("Performing full sync")
                # For full sync, use the full time window
                return await self.sync_calendar(days_ahead=days_ahead, force_refresh=True)

        except Exception as e:
            self.logger.error(f"Error in sync_events: {e}")
            return {
                'success': False,
                'events_processed': 0,
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

            # Sync to calendar backend
            try:
                # Get the appropriate calendar for this event
                calendars = await self.source_manager.list_calendars()
                target_calendar = None

                # Use event's calendar_id if specified, otherwise use first writable calendar
                if event.calendar_id:
                    target_calendar = await self.source_manager.get_calendar_by_id(event.calendar_id)

                if not target_calendar:
                    # Find first writable calendar
                    for cal in calendars:
                        if not cal.read_only:
                            target_calendar = cal
                            break

                if target_calendar:
                    adapter = self.source_manager.get_adapter()
                    # Convert ChronosEvent to normalized format for adapter
                    event_data = self._chronos_event_to_normalized(event)
                    await adapter.create_event(target_calendar, event_data)
                    self.logger.info(f"Event synced to calendar {target_calendar.alias}: {event.title}")
                else:
                    self.logger.warning(f"No writable calendar available for event: {event.title}")

            except Exception as e:
                self.logger.warning(f"Failed to sync event to calendar backend: {e}")

            return event

        except Exception as e:
            self.logger.error(f"Failed to create event: {e}")
            raise

    async def _consume_calendar_event(self, event: ChronosEvent, calendar=None):
        """Remove events that were transformed into commands"""
        event_id = event.id

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
                # Use the provided calendar or find it by calendar_id
                target_calendar = calendar
                if not target_calendar and event.calendar_id:
                    target_calendar = await self.source_manager.get_calendar_by_id(event.calendar_id)

                if not target_calendar:
                    # Fall back to first available calendar
                    calendars = await self.source_manager.list_calendars()
                    target_calendar = calendars[0] if calendars else None

                if target_calendar:
                    adapter = self.source_manager.get_adapter()
                    await adapter.delete_event(target_calendar, event_id)
                    self.logger.info(f"Removed command event {event_id} from calendar {target_calendar.alias}")
                else:
                    self.logger.warning(f"No calendar found to delete event {event_id}")

            except Exception as api_error:
                self.logger.warning(f"Failed to delete calendar event {event_id}: {api_error}")
        else:
            self.logger.debug("Command event without identifier received; skipping deletion")

    async def get_health_status(self) -> Dict[str, Any]:
        """Get scheduler health status"""
        try:
            backend_info = await self.source_manager.get_backend_info()
            connection_valid = await self.source_manager.validate_connection()
        except Exception as e:
            self.logger.warning(f"Failed to get backend info: {e}")
            backend_info = {"type": "unknown", "calendars": [], "connection_valid": False}
            connection_valid = False

        return {
            "status": "healthy" if self.is_running and connection_valid else "degraded",
            "is_running": self.is_running,
            "backend": backend_info,
            "timebox_enabled": self.timebox is not None,
            "replan_enabled": self.replan is not None,
            "analytics_enabled": self.analytics is not None,
            "last_sync": self.last_sync_time.isoformat() if self.last_sync_time else None
        }

    def _chronos_event_to_normalized(self, event: ChronosEvent) -> Dict[str, Any]:
        """Convert ChronosEvent to normalized event format for adapters"""
        return {
            'id': event.id,
            'uid': event.id,
            'summary': event.title,
            'description': event.description or '',
            'start_time': event.start_time,
            'end_time': event.end_time,
            'all_day': event.all_day,
            'timezone': event.timezone or 'UTC',
            'calendar_id': event.calendar_id,
            'rrule': event.rrule,
            'recurrence_id': event.recurrence_id
        }