"""
Analytics Engine for Chronos v2.1 - Database Integration
Replaces all in-memory storage with SQLite persistence
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import select, func, and_

from src.core.models import ChronosEvent, AnalyticsData, AnalyticsDataDB, ChronosEventDB, Priority, EventType, EventStatus
from src.core.database import db_service


class AnalyticsEngine:
    """Database-powered analytics engine - NO MORE IN-MEMORY"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Analytics Engine initialized with database persistence")
    
    async def track_event(self, event: ChronosEvent) -> None:
        """Track event for analytics in database"""
        
        try:
            # Calculate event metrics
            metrics = self._calculate_event_metrics(event)
            
            # Create analytics data
            analytics_data = AnalyticsData(
                event_id=event.id,
                date=event.start_time or datetime.utcnow(),
                metrics=metrics
            )
            
            # Store in database
            async with db_service.get_session() as session:
                # Check if analytics data already exists
                result = await session.execute(
                    select(AnalyticsDataDB).where(AnalyticsDataDB.event_id == event.id)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing
                    existing.metrics = metrics
                    existing.date = analytics_data.date
                else:
                    # Create new
                    session.add(analytics_data.to_db_model())
                
                await session.commit()
            
            self.logger.debug(f"Tracked event analytics: {event.title}")
            
        except Exception as e:
            self.logger.error(f"Failed to track event analytics: {e}")
    
    def _calculate_event_metrics(self, event: ChronosEvent) -> Dict[str, float]:
        """Calculate metrics for an event"""
        
        metrics = {}
        
        # Duration metrics
        if event.duration:
            metrics['duration_hours'] = event.duration.total_seconds() / 3600
            metrics['duration_minutes'] = event.duration.total_seconds() / 60
        
        # Priority scoring
        priority_scores = {
            Priority.LOW: 1.0,
            Priority.MEDIUM: 2.0,
            Priority.HIGH: 3.0,
            Priority.URGENT: 4.0
        }
        metrics['priority_score'] = priority_scores.get(event.priority, 2.0)
        
        # Type scoring
        type_scores = {
            EventType.MEETING: 2.0,
            EventType.TASK: 3.0,
            EventType.APPOINTMENT: 1.5,
            EventType.REMINDER: 1.0,
            EventType.BLOCK: 2.5
        }
        metrics['type_score'] = type_scores.get(event.event_type, 2.0)
        
        # Status progress
        status_progress = {
            EventStatus.SCHEDULED: 0.0,
            EventStatus.IN_PROGRESS: 0.5,
            EventStatus.COMPLETED: 1.0,
            EventStatus.CANCELLED: -0.5,
            EventStatus.RESCHEDULED: 0.0
        }
        metrics['status_progress'] = status_progress.get(event.status, 0.0)
        
        # AI-derived metrics
        if event.productivity_score is not None:
            metrics['productivity_score'] = event.productivity_score
        if event.completion_rate is not None:
            metrics['completion_rate'] = event.completion_rate
        if event.stress_level is not None:
            metrics['stress_level'] = event.stress_level
        
        # Focus metrics
        metrics['requires_focus'] = 1.0 if event.requires_focus else 0.0
        metrics['flexible_timing'] = 1.0 if event.flexible_timing else 0.0
        
        return metrics
    
    async def get_productivity_metrics(self, days_back: int = 30) -> Dict[str, float]:
        """Get productivity metrics from database"""
        
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        async with db_service.get_session() as session:
            # Get events in date range
            result = await session.execute(
                select(ChronosEventDB).where(
                    and_(
                        ChronosEventDB.start_time >= start_date,
                        ChronosEventDB.start_time <= datetime.utcnow()
                    )
                )
            )
            events = result.scalars().all()
            
            # Get analytics data for these events
            event_ids = [event.id for event in events]
            analytics_result = await session.execute(
                select(AnalyticsDataDB).where(AnalyticsDataDB.event_id.in_(event_ids))
            )
            analytics_data = analytics_result.scalars().all()
            
            # Calculate metrics
            total_events = len(events)
            if total_events == 0:
                return self._empty_metrics()
            
            completed_events = len([e for e in events if e.status == EventStatus.COMPLETED.value])
            completion_rate = completed_events / total_events
            
            # Calculate total hours
            total_minutes = sum([
                (e.end_time - e.start_time).total_seconds() / 60 
                for e in events 
                if e.start_time and e.end_time
            ])
            total_hours = total_minutes / 60
            
            # Average productivity from analytics data
            productivity_scores = [
                data.metrics.get('productivity_score', 0) 
                for data in analytics_data 
                if data.metrics.get('productivity_score') is not None
            ]
            avg_productivity = sum(productivity_scores) / len(productivity_scores) if productivity_scores else 0.0
            
            # Events per day
            events_per_day = total_events / days_back
            
            return {
                'total_events': total_events,
                'completed_events': completed_events,
                'completion_rate': completion_rate,
                'total_hours': total_hours,
                'average_productivity': avg_productivity,
                'events_per_day': events_per_day
            }
    
    async def get_priority_distribution(self, days_back: int = 7) -> Dict[str, int]:
        """Get priority distribution from database"""
        
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        async with db_service.get_session() as session:
            result = await session.execute(
                select(ChronosEventDB.priority, func.count(ChronosEventDB.id))
                .where(ChronosEventDB.start_time >= start_date)
                .group_by(ChronosEventDB.priority)
            )
            
            distribution = {priority.name: 0 for priority in Priority}
            for priority, count in result.all():
                distribution[priority] = count
            
            return distribution
    
    async def get_time_distribution(self, days_back: int = 7) -> Dict[str, float]:
        """Get hourly time distribution from database"""
        
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        async with db_service.get_session() as session:
            result = await session.execute(
                select(ChronosEventDB).where(
                    and_(
                        ChronosEventDB.start_time >= start_date,
                        ChronosEventDB.start_time.isnot(None),
                        ChronosEventDB.end_time.isnot(None)
                    )
                )
            )
            events = result.scalars().all()
            
            # Initialize hourly distribution
            time_distribution = {str(hour): 0.0 for hour in range(24)}
            
            # Calculate time spent per hour
            for event in events:
                if event.start_time and event.end_time:
                    duration_hours = (event.end_time - event.start_time).total_seconds() / 3600
                    start_hour = str(event.start_time.hour)
                    time_distribution[start_hour] += duration_hours
            
            return time_distribution
    
    async def generate_insights(self, days_back: int = 30) -> List[str]:
        """Generate insights from analytics data in database"""
        
        insights = []
        
        try:
            # Get productivity metrics
            metrics = await self.get_productivity_metrics(days_back)
            
            # Completion rate insights
            completion_rate = metrics.get('completion_rate', 0)
            if completion_rate < 0.6:
                insights.append(f"Low completion rate ({completion_rate:.1%}). Consider breaking down large tasks.")
            elif completion_rate > 0.8:
                insights.append(f"Excellent completion rate ({completion_rate:.1%})! Keep up the great work.")
            
            # Workload insights
            events_per_day = metrics.get('events_per_day', 0)
            if events_per_day > 8:
                insights.append(f"High event density ({events_per_day:.1f}/day). Consider consolidating meetings.")
            elif events_per_day < 3:
                insights.append(f"Light schedule ({events_per_day:.1f}/day). Good opportunity for strategic work.")
            
            # Time insights
            total_hours = metrics.get('total_hours', 0)
            weekly_hours = total_hours * 7 / days_back
            if weekly_hours > 50:
                insights.append(f"High time commitment ({weekly_hours:.1f}h/week). Ensure work-life balance.")
            
            return insights
            
        except Exception as e:
            self.logger.error(f"Failed to generate insights: {e}")
            return ["Analytics insights temporarily unavailable."]
    
    def _empty_metrics(self) -> Dict[str, float]:
        """Return empty metrics structure"""
        return {
            'total_events': 0,
            'completed_events': 0,
            'completion_rate': 0.0,
            'total_hours': 0.0,
            'average_productivity': 0.0,
            'events_per_day': 0.0
        }
