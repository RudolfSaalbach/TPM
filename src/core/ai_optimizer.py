"""
AI Optimizer for Chronos - Phase 2 Feature
Provides intelligent scheduling recommendations
"""

import inspect
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from src.core.models import ChronosEvent, Priority, EventType, TimeSlot, WorkingHours
from src.core.analytics_engine import AnalyticsEngine


@dataclass
class OptimizationSuggestion:
    """Optimization suggestion from AI"""
    suggestion_type: str  # 'reschedule', 'merge', 'split', 'prioritize', 'conflict'
    event_id: str
    original_time: Optional[datetime]
    suggested_time: Optional[datetime]
    description: str
    confidence: float
    impact_score: float

    @property
    def type(self) -> str:
        """Backward compatible alias used by older code paths."""
        return self.suggestion_type

    @property
    def reason(self) -> str:
        """Alias maintained for compatibility with previous API."""
        return self.description


class AIOptimizer:
    """AI-powered schedule optimization engine"""
    
    def __init__(self, analytics_engine: AnalyticsEngine):
        self.analytics = analytics_engine
        self.logger = logging.getLogger(__name__)
        
        # Optimization parameters
        self.working_hours = WorkingHours()
        self.optimization_weights = {
            'priority': 0.4,
            'productivity_pattern': 0.3,
            'time_preference': 0.2,
            'conflict_avoidance': 0.1
        }
        
        self.logger.info("AI Optimizer initialized")
    
    async def optimize_schedule(
        self,
        events: List[ChronosEvent],
        optimization_window_days: int = 7
    ) -> List[OptimizationSuggestion]:
        """Generate optimization suggestions for a list of events"""

        if not events:
            return []

        suggestions: List[OptimizationSuggestion] = []

        try:
            # Get productivity metrics for context
            productivity_metrics = await self._resolve_async(
                self.analytics.get_productivity_metrics()
            ) or {}

            raw_time_distribution = await self._resolve_async(
                self.analytics.get_time_distribution()
            )

            if isinstance(raw_time_distribution, dict) and raw_time_distribution:
                time_distribution = {
                    int(hour): float(value)
                    for hour, value in raw_time_distribution.items()
                }
            else:
                time_distribution = {
                    hour: 1.0 if self.working_hours.start_hour <= hour <= self.working_hours.end_hour else 0.2
                    for hour in range(24)
                }

            # Generate different types of suggestions
            reschedule_suggestions = await self._suggest_reschedules(
                events, time_distribution, optimization_window_days
            )
            suggestions.extend(reschedule_suggestions)

            merge_suggestions = await self._suggest_merges(events)
            suggestions.extend(merge_suggestions)

            priority_suggestions = await self._suggest_priority_adjustments(
                events, productivity_metrics
            )
            suggestions.extend(priority_suggestions)

            # Detect conflicts and create follow-up suggestions
            conflicts = self._detect_scheduling_conflicts(events)
            event_map = {event.id: event for event in events}
            for conflict in conflicts:
                conflict_ids = conflict['events']
                candidates = [event_map[eid] for eid in conflict_ids if eid in event_map]
                if len(candidates) < 2:
                    continue

                # Move the lowest priority event first
                target_event = min(candidates, key=lambda e: e.priority.value)
                other_events = [eid for eid in conflict_ids if eid != target_event.id]
                description = (
                    f"Resolve conflict with {' and '.join(other_events)}"
                    if other_events else "Resolve scheduling conflict"
                )

                suggestions.append(OptimizationSuggestion(
                    suggestion_type='conflict',
                    event_id=target_event.id,
                    original_time=target_event.start_time,
                    suggested_time=None,
                    description=description,
                    confidence=max(0.5, 0.6 * conflict['severity'] + 0.2),
                    impact_score=5.0 * conflict['severity']
                ))

            # Sort by impact score
            suggestions.sort(key=lambda x: x.impact_score, reverse=True)

            self.logger.info(f"Generated {len(suggestions)} optimization suggestions")
            return suggestions[:10]  # Return top 10 suggestions
            
        except Exception as e:
            self.logger.error(f"Failed to optimize schedule: {e}")
            return []
    
    async def _suggest_reschedules(
        self,
        events: List[ChronosEvent],
        time_distribution: Dict[int, float],
        window_days: int
    ) -> List[OptimizationSuggestion]:
        """Suggest event reschedules based on productivity patterns"""

        suggestions = []

        if not time_distribution:
            return suggestions

        # Find peak productivity hours
        peak_hours = sorted(
            time_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        if not peak_hours:
            return suggestions

        peak_hour_set = {hour for hour, _ in peak_hours}
        
        for event in events:
            if not event.is_flexible() or not event.start_time:
                continue
            
            current_hour = event.start_time.hour
            
            # Suggest moving high priority tasks to peak hours
            if (event.priority in [Priority.HIGH, Priority.URGENT] and
                current_hour not in peak_hour_set):
                
                # Find best peak hour slot
                best_hour = peak_hours[0][0]  # Top peak hour
                
                # Calculate suggested time
                suggested_start = event.start_time.replace(
                    hour=best_hour, 
                    minute=0, 
                    second=0, 
                    microsecond=0
                )
                
                # Ensure it's within working hours
                if (self.working_hours.start_hour <= best_hour <= self.working_hours.end_hour):
                    suggestions.append(OptimizationSuggestion(
                        suggestion_type='reschedule',
                        event_id=event.id,
                        original_time=event.start_time,
                        suggested_time=suggested_start,
                        description=f"Move high-priority task to peak productivity hour ({best_hour}:00)",
                        confidence=0.8,
                        impact_score=3.0 * event.priority.value
                    ))
        
        return suggestions

    async def _resolve_async(self, value: Any) -> Any:
        """Await a value if required and return the resolved result."""

        if inspect.isawaitable(value):
            return await value
        return value
    
    async def _suggest_merges(self, events: List[ChronosEvent]) -> List[OptimizationSuggestion]:
        """Suggest merging similar events"""
        
        suggestions = []
        
        # Group events by type and day
        events_by_day = {}
        for event in events:
            if not event.start_time:
                continue
            
            day_key = event.start_time.date()
            if day_key not in events_by_day:
                events_by_day[day_key] = []
            events_by_day[day_key].append(event)
        
        # Look for merge opportunities within each day
        for day, day_events in events_by_day.items():
            # Group by event type
            by_type = {}
            for event in day_events:
                if event.event_type not in by_type:
                    by_type[event.event_type] = []
                by_type[event.event_type].append(event)
            
            # Suggest merging short meetings
            if EventType.MEETING in by_type:
                meetings = by_type[EventType.MEETING]
                short_meetings = [
                    m for m in meetings 
                    if m.duration and m.duration <= timedelta(minutes=30)
                ]
                
                if len(short_meetings) >= 3:
                    # Suggest merging into a single longer meeting
                    earliest_meeting = min(short_meetings, key=lambda x: x.start_time)
                    
                    suggestions.append(OptimizationSuggestion(
                        suggestion_type='merge',
                        event_id=earliest_meeting.id,
                        original_time=earliest_meeting.start_time,
                        suggested_time=earliest_meeting.start_time,
                        description=f"Consider merging {len(short_meetings)} short meetings into one session",
                        confidence=0.6,
                        impact_score=2.0
                    ))
        
        return suggestions

    def _calculate_priority_score(self, event: ChronosEvent) -> float:
        """Score the event based on its priority enum."""

        priority_scores = {
            Priority.LOW: 1.0,
            Priority.MEDIUM: 2.0,
            Priority.HIGH: 3.0,
            Priority.URGENT: 4.0,
        }
        return priority_scores.get(event.priority, 2.0)

    def _detect_scheduling_conflicts(self, events: List[ChronosEvent]) -> List[Dict[str, Any]]:
        """Return overlap conflicts between events."""

        scheduled = [
            event for event in events
            if event.start_time and event.end_time
        ]
        scheduled.sort(key=lambda e: e.start_time)

        conflicts: List[Dict[str, Any]] = []

        for index, base_event in enumerate(scheduled):
            for other_event in scheduled[index + 1:]:
                if base_event.conflicts_with(other_event):
                    overlap_start = max(base_event.start_time, other_event.start_time)
                    overlap_end = min(base_event.end_time, other_event.end_time)
                    overlap_duration = max(timedelta(), overlap_end - overlap_start)

                    severity = min(1.0, overlap_duration.total_seconds() / 3600)
                    conflicts.append({
                        'type': 'overlap',
                        'events': [base_event.id, other_event.id],
                        'severity': severity
                    })

        return conflicts
    
    async def _suggest_priority_adjustments(
        self, 
        events: List[ChronosEvent],
        productivity_metrics: Dict[str, float]
    ) -> List[OptimizationSuggestion]:
        """Suggest priority adjustments based on completion patterns"""
        
        suggestions = []
        
        # If completion rate is low, suggest reducing low-priority tasks
        if productivity_metrics.get('completion_rate', 0) < 0.7:
            low_priority_events = [
                e for e in events 
                if e.priority == Priority.LOW and e.is_flexible()
            ]
            
            for event in low_priority_events[:3]:  # Top 3 candidates
                suggestions.append(OptimizationSuggestion(
                    suggestion_type='prioritize',
                    event_id=event.id,
                    original_time=event.start_time,
                    suggested_time=None,
                    description="Consider postponing or delegating low-priority tasks to focus on completion",
                    confidence=0.7,
                    impact_score=1.5
                ))
        
        # Suggest promoting urgent tasks
        urgent_tasks = [e for e in events if e.priority == Priority.URGENT]
        for event in urgent_tasks:
            if not event.start_time:
                continue

            now = datetime.utcnow()
            if event.start_time > now + timedelta(days=1):
                suggestions.append(OptimizationSuggestion(
                    suggestion_type='prioritize',
                    event_id=event.id,
                    original_time=event.start_time,
                    suggested_time=now + timedelta(hours=2),
                    description="Urgent task scheduled far in future - consider moving earlier",
                    confidence=0.9,
                    impact_score=4.0
                ))
            elif event.start_time < now:
                suggestions.append(OptimizationSuggestion(
                    suggestion_type='prioritize',
                    event_id=event.id,
                    original_time=event.start_time,
                    suggested_time=now,
                    description="Urgent task is overdue - address immediately",
                    confidence=0.95,
                    impact_score=4.5
                ))

        return suggestions
    
    async def find_optimal_time_slot(
        self, 
        event: ChronosEvent,
        existing_events: List[ChronosEvent],
        preference_start: datetime,
        preference_end: datetime
    ) -> Optional[TimeSlot]:
        """Find optimal time slot for an event"""
        
        try:
            # Get productivity patterns
            time_distribution = await self.analytics.get_time_distribution()
            
            # Generate potential time slots
            potential_slots = self._generate_time_slots(
                preference_start, preference_end, event.duration or timedelta(hours=1)
            )
            
            # Score each slot
            scored_slots = []
            for slot in potential_slots:
                score = await self._score_time_slot(
                    slot, event, existing_events, time_distribution
                )
                scored_slots.append((slot, score))
            
            # Return best slot
            if scored_slots:
                best_slot, _ = max(scored_slots, key=lambda x: x[1])
                return best_slot
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to find optimal time slot: {e}")
            return None
    
    def _generate_time_slots(
        self, 
        start: datetime, 
        end: datetime, 
        duration: timedelta
    ) -> List[TimeSlot]:
        """Generate possible time slots within a period"""
        
        slots = []
        current = start
        
        while current + duration <= end:
            # Check if within working hours
            if (self.working_hours.start_hour <= current.hour <= self.working_hours.end_hour and
                current.weekday() in self.working_hours.working_days):
                
                slots.append(TimeSlot(current, current + duration))
            
            current += timedelta(minutes=30)  # 30-minute increments
        
        return slots
    
    async def _score_time_slot(
        self, 
        slot: TimeSlot,
        event: ChronosEvent,
        existing_events: List[ChronosEvent],
        time_distribution: Dict[int, float]
    ) -> float:
        """Score a time slot for an event"""
        
        score = 0.0
        
        # Productivity pattern score (0-1)
        hour = slot.start.hour
        max_productivity = max(time_distribution.values()) if time_distribution else 1
        productivity_score = time_distribution.get(hour, 0) / max_productivity if max_productivity > 0 else 0.5
        score += productivity_score * self.optimization_weights['productivity_pattern']
        
        # Priority alignment score (0-1)
        priority_score = 0.5  # Default
        if event.priority == Priority.URGENT and 9 <= hour <= 11:  # Morning for urgent
            priority_score = 1.0
        elif event.priority == Priority.HIGH and 9 <= hour <= 15:  # Core hours for high
            priority_score = 0.8
        elif event.priority == Priority.MEDIUM and 10 <= hour <= 16:  # Extended core for medium
            priority_score = 0.6
        elif event.priority == Priority.LOW and (hour >= 16 or hour <= 9):  # Off-peak for low
            priority_score = 0.4
        
        score += priority_score * self.optimization_weights['priority']
        
        # Conflict avoidance score (0-1)
        conflict_score = 1.0
        for existing in existing_events:
            existing_slot = existing.get_time_slot()
            if existing_slot and slot.overlaps_with(existing_slot):
                conflict_score = 0.0
                break
        
        score += conflict_score * self.optimization_weights['conflict_avoidance']
        
        # Time preference score (0-1)
        preference_score = 1.0  # Could be enhanced with user preferences
        score += preference_score * self.optimization_weights['time_preference']
        
        return score
    
    async def suggest_break_times(
        self, 
        events: List[ChronosEvent],
        target_date: datetime
    ) -> List[TimeSlot]:
        """Suggest optimal break times between events"""
        
        # Filter events for target date
        day_events = [
            e for e in events 
            if e.start_time and e.start_time.date() == target_date.date()
        ]
        
        if not day_events:
            return []
        
        # Sort events by start time
        day_events.sort(key=lambda x: x.start_time)
        
        # Find gaps between events
        break_slots = []
        
        for i in range(len(day_events) - 1):
            current_event = day_events[i]
            next_event = day_events[i + 1]
            
            if current_event.end_time and next_event.start_time:
                gap_duration = next_event.start_time - current_event.end_time
                
                # Suggest breaks for gaps longer than 30 minutes
                if gap_duration >= timedelta(minutes=30):
                    break_start = current_event.end_time
                    break_end = min(
                        current_event.end_time + timedelta(minutes=15),
                        next_event.start_time - timedelta(minutes=5)
                    )
                    
                    if break_end > break_start:
                        break_slots.append(TimeSlot(break_start, break_end))
        
        return break_slots
    
    async def calculate_workload_balance(
        self, 
        events: List[ChronosEvent],
        days: int = 7
    ) -> Dict[str, float]:
        """Calculate workload balance metrics"""
        
        try:
            # Group events by day
            daily_workload = {}
            cutoff_date = datetime.utcnow()
            
            for event in events:
                if (not event.start_time or 
                    event.start_time < cutoff_date or
                    event.start_time > cutoff_date + timedelta(days=days)):
                    continue
                
                day_key = event.start_time.date()
                if day_key not in daily_workload:
                    daily_workload[day_key] = {
                        'total_duration': timedelta(),
                        'event_count': 0,
                        'priority_sum': 0
                    }
                
                daily_workload[day_key]['event_count'] += 1
                daily_workload[day_key]['priority_sum'] += event.priority.value
                
                if event.duration:
                    daily_workload[day_key]['total_duration'] += event.duration
            
            # Calculate balance metrics
            if not daily_workload:
                return {
                    'average_daily_hours': 0.0,
                    'workload_variance': 0.0,
                    'balance_score': 1.0,
                    'overloaded_days': 0,
                    'underloaded_days': 0
                }
            
            daily_hours = [
                workload['total_duration'].total_seconds() / 3600
                for workload in daily_workload.values()
            ]
            
            avg_hours = sum(daily_hours) / len(daily_hours)
            variance = sum((h - avg_hours) ** 2 for h in daily_hours) / len(daily_hours)
            
            # Count problematic days
            overloaded_days = len([h for h in daily_hours if h > 10])  # > 10 hours
            underloaded_days = len([h for h in daily_hours if h < 2])   # < 2 hours
            
            # Balance score (0-1, higher is better)
            max_variance = 16  # Assume max variance of 4 hours squared
            balance_score = max(0, 1 - (variance / max_variance))
            
            return {
                'average_daily_hours': avg_hours,
                'workload_variance': variance,
                'balance_score': balance_score,
                'overloaded_days': overloaded_days,
                'underloaded_days': underloaded_days,
                'total_scheduled_days': len(daily_workload)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to calculate workload balance: {e}")
            return {}
