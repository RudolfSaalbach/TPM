"""
Main Scheduler for Chronos Engine v2.1 - Enhanced with Full Calendar Sync
Updated to support unlimited calendar synchronization for free accounts
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_

from src.core.models import ChronosEvent, ChronosEventDB, Priority, EventStatus
from src.core.database import db_service
from src.core.calendar_client import GoogleCalendarClient
from src.core.event_parser import EventParser
from src.core.calendar_sync import FullCalendarSync  # NEW: Complete sync engine
from src.core.analytics_engine import AnalyticsEngine
from src.core.ai_optimizer import AIOptimizer
from src.core.timebox_engine import TimeboxEngine
from src.core.replan_engine import ReplanEngine
from src.core.notification_engine import NotificationEngine
from src.core.task_queue import TaskQueue
from src.core.plugin_manager import PluginManager


class ChronosScheduler:
    """Enhanced scheduler with complete calendar synchronization"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components - ALL use database now
        self.calendar_client = GoogleCalendarClient(
            credentials_file=config.get('calendar', {}).get('credentials_file', 'config/credentials.json'),
            token_file=config.get('calendar', {}).get('token_file', 'config/token.json')
        )
        
        self.event_parser = EventParser()
        
        # NEW: Full calendar sync engine
        self.full_sync = FullCalendarSync(self.calendar_client, self.event_parser)
        
        self.analytics = AnalyticsEngine()  # Database-enabled
        self.ai_optimizer = AIOptimizer(self.analytics)
        self.timebox = TimeboxEngine(self.analytics)
        self.replan = ReplanEngine(self.analytics, self.timebox)
        self.notifications = NotificationEngine(config.get('notifications', {}))
        self.task_queue = TaskQueue()  # Database-enabled
        self.plugins = PluginManager()
        
        # Enhanced sync control
        self.sync_interval = config.get('scheduler', {}).get('sync_interval', 300)
        self.full_sync_interval = config.get('scheduler', {}).get('full_sync_interval_hours', 24) * 3600  # Daily full sync
        self.last_full_sync = None
        self.is_running = False
        self.sync_task = None
        
        self.logger.info("Enhanced Chronos Scheduler initialized with complete sync capability")
    
    async def start(self):
        """Start the scheduler with database initialization"""
        if self.is_running:
            return
        
        # Initialize database
        await db_service.create_tables()
        
        # Start components
        await self.task_queue.start()
        await self.plugins.load_plugins()
        
        # Perform initial full sync if needed
        await self._check_and_perform_full_sync()
        
        # Start sync loop
        self.is_running = True
        self.sync_task = asyncio.create_task(self._enhanced_sync_loop())
        
        self.logger.info("Enhanced Chronos Scheduler started")
    
    async def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        
        await self.task_queue.stop()
        await db_service.close()
        
        self.logger.info("Enhanced Chronos Scheduler stopped")
    
    async def _enhanced_sync_loop(self):
        """Enhanced synchronization loop with full and incremental sync"""
        while self.is_running:
            try:
                # Check if full sync is needed
                await self._check_and_perform_full_sync()
                
                # Perform incremental sync
                await self.sync_calendar_incremental()
                
                await asyncio.sleep(self.sync_interval)
                
            except Exception as e:
                self.logger.error(f"Error in enhanced sync loop: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    async def _check_and_perform_full_sync(self):
        """Check if full sync is needed and perform it"""
        
        now = datetime.utcnow()
        
        # Check if full sync is needed
        needs_full_sync = (
            self.last_full_sync is None or
            (now - self.last_full_sync).total_seconds() >= self.full_sync_interval
        )
        
        if needs_full_sync:
            self.logger.info("⏰ Full sync scheduled - starting complete calendar synchronization")
            
            # Add full sync as background task
            await self.task_queue.add_task(
                name="Complete Calendar Sync",
                function="full_calendar_sync",
                priority=self.task_queue.TaskPriority.HIGH
            )
            
            self.last_full_sync = now
    
    async def sync_calendar_complete(self) -> Dict[str, Any]:
        """Perform complete calendar synchronization - UNLIMITED RANGE"""
        
        self.logger.info("🚀 Starting COMPLETE calendar synchronization...")
        
        try:
            # Use the full sync engine
            sync_stats = await self.full_sync.perform_complete_sync()
            
            # Update analytics for all synchronized events
            if sync_stats.get('events_fetched', 0) > 0:
                await self._update_analytics_for_all_events()
            
            self.logger.info(f"✅ Complete sync finished: {sync_stats}")
            return sync_stats
            
        except Exception as e:
            self.logger.error(f"❌ Complete calendar sync failed: {e}")
            return {'error': str(e)}
    
    async def sync_calendar_incremental(self, days_back: int = 7, days_ahead: int = 365) -> Dict[str, Any]:
        """Perform incremental calendar sync (quota-efficient)"""
        
        try:
            # Use incremental sync for recent changes
            sync_stats = await self.full_sync.sync_incremental(days_back, days_ahead)
            
            # Update analytics for synchronized events
            if sync_stats.get('events_fetched', 0) > 0:
                await self._update_analytics_for_recent_events(days_back, days_ahead)
            
            self.logger.debug(f"📈 Incremental sync: {sync_stats.get('events_fetched', 0)} events")
            return sync_stats
            
        except Exception as e:
            self.logger.error(f"❌ Incremental calendar sync failed: {e}")
            return {'error': str(e)}
    
    async def _update_analytics_for_all_events(self):
        """Update analytics for all events in database"""
        
        async with db_service.get_session() as session:
            result = await session.execute(select(ChronosEventDB))
            db_events = result.scalars().all()
            
            for db_event in db_events:
                event = db_event.to_domain_model()
                await self.analytics.track_event(event)
    
    async def _update_analytics_for_recent_events(self, days_back: int, days_ahead: int):
        """Update analytics for recent events"""
        
        now = datetime.utcnow()
        start_time = now - timedelta(days=days_back)
        end_time = now + timedelta(days=days_ahead)
        
        async with db_service.get_session() as session:
            result = await session.execute(
                select(ChronosEventDB).where(
                    and_(
                        ChronosEventDB.start_time >= start_time,
                        ChronosEventDB.start_time <= end_time
                    )
                )
            )
            db_events = result.scalars().all()
            
            for db_event in db_events:
                event = db_event.to_domain_model()
                await self.analytics.track_event(event)
    
    # Keep existing methods but enhance them
    async def sync_calendar(self, force_full: bool = False) -> Dict[str, int]:
        """Legacy sync method - now uses enhanced sync"""
        
        if force_full:
            return await self.sync_calendar_complete()
        else:
            return await self.sync_calendar_incremental()
    
    async def get_events(
        self, 
        start_date: Optional[datetime] = None, 
        end_date: Optional[datetime] = None,
        status_filter: Optional[EventStatus] = None
    ) -> List[ChronosEvent]:
        """Get events from database with filters - UNLIMITED RANGE SUPPORT"""
        
        async with db_service.get_session() as session:
            query = select(ChronosEventDB)
            
            # Apply filters
            conditions = []
            if start_date:
                conditions.append(ChronosEventDB.start_time >= start_date)
            if end_date:
                conditions.append(ChronosEventDB.end_time <= end_date)
            if status_filter:
                conditions.append(ChronosEventDB.status == status_filter.value)
            
            if conditions:
                query = query.where(and_(*conditions))
            
            query = query.order_by(ChronosEventDB.start_time)
            result = await session.execute(query)
            db_events = result.scalars().all()
            
            # Convert to domain models
            return [db_event.to_domain_model() for db_event in db_events]
    
    async def get_events_in_year(self, year: int) -> List[ChronosEvent]:
        """Get all events for a specific year"""
        
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)
        
        return await self.get_events(start_date, end_date)
    
    async def find_events_by_keyword(self, keyword: str) -> List[ChronosEvent]:
        """Find events containing specific keywords"""
        
        async with db_service.get_session() as session:
            query = select(ChronosEventDB).where(
                or_(
                    ChronosEventDB.title.contains(keyword),
                    ChronosEventDB.description.contains(keyword)
                )
            )
            
            result = await session.execute(query)
            db_events = result.scalars().all()
            
            return [db_event.to_domain_model() for db_event in db_events]
    
    async def get_training_events(self, future_only: bool = True) -> List[ChronosEvent]:
        """Get all training/education events (example for your use case)"""
        
        keywords = ['training', 'schulung', 'course', 'workshop', 'seminar', 'education']
        
        async with db_service.get_session() as session:
            conditions = []
            
            # Search in title and description
            for keyword in keywords:
                conditions.extend([
                    ChronosEventDB.title.ilike(f'%{keyword}%'),
                    ChronosEventDB.description.ilike(f'%{keyword}%')
                ])
            
            query = select(ChronosEventDB).where(or_(*conditions))
            
            # Filter future events if requested
            if future_only:
                query = query.where(ChronosEventDB.start_time >= datetime.utcnow())
            
            query = query.order_by(ChronosEventDB.start_time)
            result = await session.execute(query)
            db_events = result.scalars().all()
            
            return [db_event.to_domain_model() for db_event in db_events]
    
    # Enhanced existing methods
    async def create_event(self, event: ChronosEvent) -> ChronosEvent:
        """Create new event in database and Google Calendar"""
        
        # Store in database first
        async with db_service.get_session() as session:
            db_event = event.to_db_model()
            session.add(db_event)
            await session.commit()
        
        # Sync to Google Calendar
        try:
            await self.calendar_client.create_event(event# === FILE: ./src/core/calendar_sync.py ===
"""
Complete Calendar Synchronization Engine for Chronos v2.1
Optimized for free Google accounts with unlimited sync range
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Set, Tuple
from sqlalchemy import select, and_, or_

from src.core.models import ChronosEvent, ChronosEventDB, EventStatus
from src.core.database import db_service
from src.core.calendar_client import GoogleCalendarClient
from src.core.event_parser import EventParser


class QuotaManager:
    """Manages API quota for free Google accounts"""
    
    def __init__(self, daily_limit: int = 100000, requests_per_minute: int = 250):
        self.daily_limit = daily_limit
        self.requests_per_minute = requests_per_minute
        self.daily_requests = 0
        self.minute_requests = 0
        self.last_reset = datetime.utcnow()
        self.last_minute_reset = datetime.utcnow()
        
        self.logger = logging.getLogger(__name__)
    
    async def can_make_request(self) -> bool:
        """Check if we can make another API request within quota"""
        now = datetime.utcnow()
        
        # Reset daily counter
        if (now - self.last_reset).days >= 1:
            self.daily_requests = 0
            self.last_reset = now
        
        # Reset minute counter
        if (now - self.last_minute_reset).total_seconds() >= 60:
            self.minute_requests = 0
            self.last_minute_reset = now
        
        # Check limits
        if self.daily_requests >= self.daily_limit:
            self.logger.warning(f"⚠️ Daily quota limit reached ({self.daily_limit})")
            return False
        
        if self.minute_requests >= self.requests_per_minute:
            self.logger.debug(f"⏱️ Rate limit reached, waiting...")
            await asyncio.sleep(60)  # Wait for minute reset
            return await self.can_make_request()
        
        return True
    
    def record_request(self):
        """Record an API request"""
        self.daily_requests += 1
        self.minute_requests += 1
    
    def get_quota_status(self) -> Dict[str, Any]:
        """Get current quota status"""
        return {
            'daily_requests': self.daily_requests,
            'daily_limit': self.daily_limit,
            'daily_remaining': self.daily_limit - self.daily_requests,
            'minute_requests': self.minute_requests,
            'minute_limit': self.requests_per_minute
        }


class FullCalendarSync:
    """Complete calendar synchronization with unlimited range"""
    
    def __init__(
        self, 
        calendar_client: GoogleCalendarClient,
        event_parser: EventParser
    ):
        self.calendar_client = calendar_client
        self.event_parser = event_parser
        self.quota_manager = QuotaManager()
        self.logger = logging.getLogger(__name__)
        
        # Sync configuration for complete coverage
        self.batch_size = 2500  # Max events per API call
        self.sync_chunk_months = 12  # Process 1 year at a time
        self.max_future_years = 10  # Sync up to 10 years in future
        self.max_past_years = 10   # Sync up to 10 years in past
        
        self.logger.info("Full Calendar Sync initialized for unlimited range")
    
    async def perform_complete_sync(self) -> Dict[str, Any]:
        """Perform complete calendar synchronization - past and future"""
        
        self.logger.info("🔄 Starting complete calendar synchronization...")
        
        stats = {
            'events_fetched': 0,
            'events_created': 0,
            'events_updated': 0,
            'events_deleted': 0,
            'api_requests': 0,
            'sync_ranges': [],
            'errors': []
        }
        
        try:
            # Authenticate first
            if not await self.calendar_client.authenticate():
                raise Exception("Calendar authentication failed")
            
            # Get sync ranges
            sync_ranges = self._calculate_sync_ranges()
            stats['sync_ranges'] = [
                {
                    'start': r[0].isoformat(),
                    'end': r[1].isoformat(),
                    'description': r[2]
                } 
                for r in sync_ranges
            ]
            
            self.logger.info(f"📅 Syncing {len(sync_ranges)} time ranges")
            
            # Sync each range
            for start_time, end_time, description in sync_ranges:
                range_stats = await self._sync_time_range(start_time, end_time, description)
                
                # Aggregate stats
                stats['events_fetched'] += range_stats['events_fetched']
                stats['events_created'] += range_stats['events_created']
                stats['events_updated'] += range_stats['events_updated']
                stats['api_requests'] += range_stats['api_requests']
                
                if range_stats['errors']:
                    stats['errors'].extend(range_stats['errors'])
            
            # Cleanup deleted events
            cleanup_stats = await self._cleanup_deleted_events()
            stats['events_deleted'] = cleanup_stats['events_deleted']
            
            # Update quota info
            stats['quota_status'] = self.quota_manager.get_quota_status()
            
            self.logger.info(f"✅ Complete sync finished: {stats['events_fetched']} events processed")
            
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Complete sync failed: {e}")
            stats['errors'].append(str(e))
            return stats
    
    def _calculate_sync_ranges(self) -> List[Tuple[datetime, datetime, str]]:
        """Calculate time ranges for complete sync"""
        
        ranges = []
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        
        # Past ranges (going backwards)
        for year_offset in range(self.max_past_years):
            range_start = now.replace(
                year=now.year - year_offset - 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )
            range_end = now.replace(
                year=now.year - year_offset,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )
            
            ranges.append((
                range_start,
                range_end,
                f"Past Year {year_offset + 1} ({range_start.year})"
            ))
        
        # Current year
        current_year_start = now.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )
        current_year_end = now.replace(
            year=now.year + 1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )
        
        ranges.append((
            current_year_start,
            current_year_end,
            f"Current Year ({now.year})"
        ))
        
        # Future ranges
        for year_offset in range(1, self.max_future_years + 1):
            range_start = now.replace(
                year=now.year + year_offset,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )
            range_end = now.replace(
                year=now.year + year_offset + 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )
            
            ranges.append((
                range_start,
                range_end,
                f"Future Year {year_offset} ({range_start.year})"
            ))
        
        # Sort by start time
        ranges.sort(key=lambda x: x[0])
        
        return ranges
    
    async def _sync_time_range(
        self, 
        start_time: datetime, 
        end_time: datetime, 
        description: str
    ) -> Dict[str, Any]:
        """Sync a specific time range"""
        
        self.logger.info(f"📅 Syncing {description}: {start_time.date()} to {end_time.date()}")
        
        stats = {
            'events_fetched': 0,
            'events_created': 0,
            'events_updated': 0,
            'api_requests': 0,
            'errors': []
        }
        
        try:
            # Check quota before making request
            if not await self.quota_manager.can_make_request():
                raise Exception(f"Quota exceeded for range {description}")
            
            # Fetch events from Google Calendar
            calendar_events = await self._fetch_events_in_range(
                start_time, 
                end_time
            )
            
            stats['events_fetched'] = len(calendar_events)
            stats['api_requests'] += 1
            
            if not calendar_events:
                self.logger.debug(f"📭 No events found in {description}")
                return stats
            
            # Parse events
            parsed_events = self.event_parser.parse_events_batch(calendar_events)
            
            # Store/update in database
            async with db_service.get_session() as session:
                for event in parsed_events:
                    # Check if event exists
                    result = await session.execute(
                        select(ChronosEventDB).where(ChronosEventDB.id == event.id)
                    )
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        # Update existing event
                        updated = False
                        for key, value in event.to_db_model().__dict__.items():
                            if not key.startswith('_') and key not in ['id', 'created_at']:
                                if getattr(existing, key) != value:
                                    setattr(existing, key, value)
                                    updated = True
                        
                        if updated:
                            existing.updated_at = datetime.utcnow()
                            stats['events_updated'] += 1
                    else:
                        # Create new event
                        session.add(event.to_db_model())
                        stats['events_created'] += 1
                
                await session.commit()
            
            self.logger.debug(f"✅ {description}: {stats['events_created']} created, {stats['events_updated']} updated")
            
            return stats
            
        except Exception as e:
            error_msg = f"Error syncing {description}: {e}"
            self.logger.error(f"❌ {error_msg}")
            stats['errors'].append(error_msg)
            return stats
    
    async def _fetch_events_in_range(
        self, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch events from Google Calendar in specific range"""
        
        try:
            # Record quota usage
            self.quota_manager.record_request()
            
            # Make API call with extended range
            events_result = self.calendar_client.service.events().list(
                calendarId='primary',
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                maxResults=self.batch_size,
                singleEvents=True,
                orderBy='startTime',
                fields='items(id,summary,description,start,end,attendees,location,status,created,updated,recurrence)'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Handle pagination if there are more events
            page_token = events_result.get('nextPageToken')
            while page_token and len(events) < 10000:  # Reasonable limit per range
                
                if not await self.quota_manager.can_make_request():
                    self.logger.warning("⚠️ Quota limit reached during pagination")
                    break
                
                self.quota_manager.record_request()
                
                next_page = self.calendar_client.service.events().list(
                    calendarId='primary',
                    timeMin=start_time.isoformat(),
                    timeMax=end_time.isoformat(),
                    maxResults=self.batch_size,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token,
                    fields='items(id,summary,description,start,end,attendees,location,status,created,updated,recurrence)'
                ).execute()
                
                events.extend(next_page.get('items', []))
                page_token = next_page.get('nextPageToken')
            
            return events
            
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch events in range: {e}")
            raise
    
    async def _cleanup_deleted_events(self) -> Dict[str, Any]:
        """Remove events from local DB that no longer exist in Google Calendar"""
        
        self.logger.info("🧹 Cleaning up deleted events...")
        
        stats = {'events_deleted': 0}
        
        try:
            # Get all local event IDs
            async with db_service.get_session() as session:
                result = await session.execute(
                    select(ChronosEventDB.id, ChronosEventDB.updated_at)
                )
                local_events = {row[0]: row[1] for row in result.all()}
            
            if not local_events:
                return stats
            
            # Sample check - verify a subset of events still exist
            # (Full verification would use too much quota)
            sample_ids = list(local_events.keys())[:100]  # Check first 100
            
            for event_id in sample_ids:
                if not await self.quota_manager.can_make_request():
                    break
                
                try:
                    self.quota_manager.record_request()
                    
                    # Try to get event from Google Calendar
                    self.calendar_client.service.events().get(
                        calendarId='primary',
                        eventId=event_id
                    ).execute()
                    
                except Exception:
                    # Event not found - delete from local DB
                    async with db_service.get_session() as session:
                        result = await session.execute(
                            select(ChronosEventDB).where(ChronosEventDB.id == event_id)
                        )
                        event_to_delete = result.scalar_one_or_none()
                        
                        if event_to_delete:
                            await session.delete(event_to_delete)
                            await session.commit()
                            stats['events_deleted'] += 1
                            
                            self.logger.debug(f"🗑️ Removed deleted event: {event_id}")
            
            self.logger.info(f"🧹 Cleanup complete: {stats['events_deleted']} events removed")
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Cleanup failed: {e}")
            return stats
    
    async def sync_incremental(self, days_back: int = 7, days_ahead: int = 365) -> Dict[str, Any]:
        """Incremental sync for recent changes (quota-efficient)"""
        
        self.logger.info(f"🔄 Incremental sync: {days_back} days back, {days_ahead} days ahead")
        
        try:
            now = datetime.utcnow().replace(tzinfo=timezone.utc)
            start_time = now - timedelta(days=days_back)
            end_time = now + timedelta(days=days_ahead)
            
            return await self._sync_time_range(
                start_time,
                end_time,
                f"Incremental ({days_back}d back, {days_ahead}d ahead)"
            )
            
        except Exception as e:
            self.logger.error(f"❌ Incremental sync failed: {e}")
            return {'error': str(e)}
    
    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics"""
        
        async with db_service.get_session() as session:
            # Count total events
            total_result = await session.execute(select(ChronosEventDB))
            total_events = len(total_result.scalars().all())
            
            # Count by status
            completed_result = await session.execute(
                select(ChronosEventDB).where(ChronosEventDB.status == EventStatus.COMPLETED.value)
            )
            completed_events = len(completed_result.scalars().all())
            
            # Get date range
            date_result = await session.execute(
                select(
                    ChronosEventDB.start_time
                ).where(
                    ChronosEventDB.start_time.isnot(None)
                ).order_by(ChronosEventDB.start_time)
            )
            dates = [row[0] for row in date_result.all()]
            
            earliest_date = dates[0] if dates else None
            latest_date = dates[-1] if dates else None
        
        return {
            'total_events': total_events,
            'completed_events': completed_events,
            'completion_rate': completed_events / total_events if total_events > 0 else 0,
            'earliest_event': earliest_date.isoformat() if earliest_date else None,
            'latest_event': latest_date.isoformat() if latest_date else None,
            'quota_status': self.quota_manager.get_quota_status(),
            'sync_coverage': {
                'past_years': self.max_past_years,
                'future_years': self.max_future_years
            }
        }
