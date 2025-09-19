"""
Replan Engine for Chronos - Phase 2 Feature
Intelligent rescheduling and conflict resolution
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.core.models import ChronosEvent, Priority, EventType, EventStatus, TimeSlot
from src.core.analytics_engine import AnalyticsEngine
from src.core.timebox_engine import TimeboxEngine


class ConflictType(Enum):
    OVERLAP = "overlap"
    OVERLOAD = "overload"
    PRIORITY_MISMATCH = "priority_mismatch"
    RESOURCE_CONFLICT = "resource_conflict"


@dataclass
class Conflict:
    """Represents a scheduling conflict"""
    type: ConflictType
    events: List[str]  # Event IDs
    severity: float  # 0-1 scale
    description: str
    suggested_resolution: str


@dataclass
class ReplanSuggestion:
    """Replanning suggestion"""
    event_id: str
    original_start: datetime
    original_end: datetime
    suggested_start: datetime
    suggested_end: datetime
    reason: str
    confidence: float
    impact_events: List[str]  # Other affected event IDs


class ReplanEngine:
    """Intelligent replanning and conflict resolution engine"""
    
    def __init__(self, analytics_engine: AnalyticsEngine, timebox_engine: TimeboxEngine):
        self.analytics = analytics_engine
        self.timebox = timebox_engine
        self.logger = logging.getLogger(__name__)
        
        # Replanning parameters
        self.max_replan_attempts = 5
        self.conflict_buffer = timedelta(minutes=15)
        self.replan_window_days = 14
        
        self.logger.info("Replan Engine initialized")
    
    async def detect_conflicts(
        self,
        events: List[ChronosEvent],
        target_date: Optional[datetime] = None
    ) -> List[Conflict]:
        """Detect scheduling conflicts in events"""
        
        try:
            # Filter events for analysis
            if target_date:
                filtered_events = [
                    e for e in events 
                    if e.start_time and e.start_time.date() == target_date.date()
                ]
            else:
                # Analyze next 7 days
                cutoff = datetime.utcnow() + timedelta(days=7)
                filtered_events = [
                    e for e in events 
                    if e.start_time and e.start_time <= cutoff
                ]
            
            conflicts = []
            
            # Check for overlapping events
            overlap_conflicts = self._detect_overlap_conflicts(filtered_events)
            conflicts.extend(overlap_conflicts)
            
            # Check for daily overload
            overload_conflicts = await self._detect_overload_conflicts(filtered_events)
            conflicts.extend(overload_conflicts)
            
            # Check for priority mismatches
            priority_conflicts = self._detect_priority_conflicts(filtered_events)
            conflicts.extend(priority_conflicts)
            
            self.logger.info(f"Detected {len(conflicts)} conflicts")
            return conflicts
            
        except Exception as e:
            self.logger.error(f"Failed to detect conflicts: {e}")
            return []
    
    def _detect_overlap_conflicts(self, events: List[ChronosEvent]) -> List[Conflict]:
        """Detect overlapping events"""
        
        conflicts = []
        
        # Sort events by start time
        scheduled_events = [e for e in events if e.start_time and e.end_time]
        scheduled_events.sort(key=lambda x: x.start_time)
        
        for i in range(len(scheduled_events)):
            for j in range(i + 1, len(scheduled_events)):
                event1 = scheduled_events[i]
                event2 = scheduled_events[j]
                
                if event1.conflicts_with(event2):
                    # Calculate severity based on overlap duration
                    overlap_start = max(event1.start_time, event2.start_time)
                    overlap_end = min(event1.end_time, event2.end_time)
                    overlap_duration = overlap_end - overlap_start
                    
                    severity = min(1.0, overlap_duration.total_seconds() / 3600)  # Normalize to hours
                    
                    conflicts.append(Conflict(
                        type=ConflictType.OVERLAP,
                        events=[event1.id, event2.id],
                        severity=severity,
                        description=f"Events '{event1.title}' and '{event2.title}' overlap",
                        suggested_resolution="Reschedule one of the events"
                    ))
        
        return conflicts

    async def generate_replan_suggestions(self, events: List[ChronosEvent]) -> List[ReplanSuggestion]:
        """Detect conflicts and return replanning suggestions."""

        conflicts = await self.detect_conflicts(events)
        if not conflicts:
            return []
        return await self.suggest_replanning(conflicts, events)
    
    async def _detect_overload_conflicts(self, events: List[ChronosEvent]) -> List[Conflict]:
        """Detect daily overload situations"""
        
        conflicts = []
        
        # Group events by day
        events_by_day = {}
        for event in events:
            if not event.start_time:
                continue
            
            day_key = event.start_time.date()
            if day_key not in events_by_day:
                events_by_day[day_key] = []
            events_by_day[day_key].append(event)
        
        # Check each day for overload
        for day, day_events in events_by_day.items():
            total_duration = sum([
                e.duration.total_seconds() for e in day_events 
                if e.duration
            ], 0) / 3600  # Convert to hours
            
            # Consider 10+ hours as overload
            if total_duration >= 10:
                event_ids = [e.id for e in day_events]
                
                conflicts.append(Conflict(
                    type=ConflictType.OVERLOAD,
                    events=event_ids,
                    severity=min(1.0, (total_duration - 8) / 4),  # Severity based on excess hours
                    description=f"Day {day} is overloaded with {total_duration:.1f} hours of scheduled activities",
                    suggested_resolution="Consider moving some tasks to other days or extending deadline"
                ))
        
        return conflicts
    
    def _detect_priority_conflicts(self, events: List[ChronosEvent]) -> List[Conflict]:
        """Detect priority scheduling conflicts"""
        
        conflicts = []
        
        # Find cases where low priority events are scheduled during prime time
        # and high priority events during off hours
        
        for event in events:
            if not event.start_time:
                continue
            
            hour = event.start_time.hour
            
            # Prime time: 9-12 and 14-17
            is_prime_time = (9 <= hour <= 12) or (14 <= hour <= 17)
            
            if (event.priority == Priority.LOW and is_prime_time):
                conflicts.append(Conflict(
                    type=ConflictType.PRIORITY_MISMATCH,
                    events=[event.id],
                    severity=0.6,
                    description=f"Low priority event '{event.title}' scheduled during prime time",
                    suggested_resolution="Consider moving to off-peak hours"
                ))
            
            elif (event.priority == Priority.URGENT and not is_prime_time and hour < 18):
                conflicts.append(Conflict(
                    type=ConflictType.PRIORITY_MISMATCH,
                    events=[event.id],
                    severity=0.8,
                    description=f"Urgent event '{event.title}' scheduled during off-peak time",
                    suggested_resolution="Consider moving to prime time slot"
                ))
        
        return conflicts
    
    async def suggest_replanning(
        self, 
        conflicts: List[Conflict],
        events: List[ChronosEvent]
    ) -> List[ReplanSuggestion]:
        """Generate replanning suggestions for detected conflicts"""
        
        suggestions = []
        
        try:
            for conflict in conflicts:
                if conflict.type == ConflictType.OVERLAP:
                    overlap_suggestions = await self._resolve_overlap_conflict(conflict, events)
                    suggestions.extend(overlap_suggestions)
                
                elif conflict.type == ConflictType.OVERLOAD:
                    overload_suggestions = await self._resolve_overload_conflict(conflict, events)
                    suggestions.extend(overload_suggestions)
                
                elif conflict.type == ConflictType.PRIORITY_MISMATCH:
                    priority_suggestions = await self._resolve_priority_conflict(conflict, events)
                    suggestions.extend(priority_suggestions)
            
            # Sort by confidence and impact
            suggestions.sort(key=lambda x: x.confidence, reverse=True)
            
            self.logger.info(f"Generated {len(suggestions)} replanning suggestions")
            return suggestions[:10]  # Return top 10 suggestions
            
        except Exception as e:
            self.logger.error(f"Failed to generate replanning suggestions: {e}")
            return []
    
    async def _resolve_overlap_conflict(
        self, 
        conflict: Conflict, 
        events: List[ChronosEvent]
    ) -> List[ReplanSuggestion]:
        """Resolve overlapping events conflict"""
        
        suggestions = []
        
        # Get the conflicting events
        conflicting_events = [e for e in events if e.id in conflict.events]
        
        if len(conflicting_events) < 2:
            return suggestions
        
        # Sort by priority (lower priority events get moved first)
        conflicting_events.sort(key=lambda x: x.priority.value)
        
        # Try to reschedule the lower priority event
        event_to_move = conflicting_events[0]
        stationary_events = conflicting_events[1:]
        
        # Find alternative time slot
        alternative_slot = await self._find_alternative_slot(
            event_to_move, 
            events, 
            avoid_events=stationary_events
        )
        
        if alternative_slot:
            suggestions.append(ReplanSuggestion(
                event_id=event_to_move.id,
                original_start=event_to_move.start_time,
                original_end=event_to_move.end_time,
                suggested_start=alternative_slot.start,
                suggested_end=alternative_slot.end,
                reason="Resolve scheduling conflict",
                confidence=0.8,
                impact_events=[e.id for e in stationary_events]
            ))
        
        return suggestions
    
    async def _resolve_overload_conflict(
        self, 
        conflict: Conflict, 
        events: List[ChronosEvent]
    ) -> List[ReplanSuggestion]:
        """Resolve daily overload conflict"""
        
        suggestions = []
        
        # Get overloaded events
        overloaded_events = [e for e in events if e.id in conflict.events]
        
        # Sort by flexibility and priority
        flexible_events = [e for e in overloaded_events if e.is_flexible()]
        flexible_events.sort(key=lambda x: x.priority.value)  # Move lower priority first
        
        # Try to move some flexible events to other days
        for event in flexible_events[:3]:  # Limit to 3 events to avoid over-disruption
            # Look for slots in the next 7 days
            for days_offset in range(1, 8):
                target_date = event.start_time + timedelta(days=days_offset)
                
                # Skip weekends if it's a work event
                if target_date.weekday() >= 5 and event.event_type in [EventType.MEETING, EventType.TASK]:
                    continue
                
                alternative_slot = await self._find_alternative_slot(
                    event, 
                    events, 
                    target_date=target_date
                )
                
                if alternative_slot:
                    suggestions.append(ReplanSuggestion(
                        event_id=event.id,
                        original_start=event.start_time,
                        original_end=event.end_time,
                        suggested_start=alternative_slot.start,
                        suggested_end=alternative_slot.end,
                        reason=f"Reduce daily overload by moving to {target_date.strftime('%A, %B %d')}",
                        confidence=0.7,
                        impact_events=[]
                    ))
                    break  # Found a slot, move to next event
        
        return suggestions
    
    async def _resolve_priority_conflict(
        self, 
        conflict: Conflict, 
        events: List[ChronosEvent]
    ) -> List[ReplanSuggestion]:
        """Resolve priority mismatch conflict"""
        
        suggestions = []
        
        # Get the conflicting event
        conflicting_events = [e for e in events if e.id in conflict.events]
        
        if not conflicting_events:
            return suggestions
        
        event = conflicting_events[0]
        
        # Find better time slot based on priority
        if event.priority == Priority.LOW:
            # Move to off-peak hours (early morning or late afternoon)
            preferred_hours = [8, 17, 18]
        elif event.priority in [Priority.HIGH, Priority.URGENT]:
            # Move to prime time
            preferred_hours = [9, 10, 11, 14, 15, 16]
        else:
            return suggestions
        
        alternative_slot = await self._find_alternative_slot(
            event, 
            events, 
            preferred_hours=preferred_hours
        )
        
        if alternative_slot:
            suggestions.append(ReplanSuggestion(
                event_id=event.id,
                original_start=event.start_time,
                original_end=event.end_time,
                suggested_start=alternative_slot.start,
                suggested_end=alternative_slot.end,
                reason=f"Optimize timing for {event.priority.name} priority event",
                confidence=0.75,
                impact_events=[]
            ))
        
        return suggestions
    
    async def _find_alternative_slot(
        self,
        event: ChronosEvent,
        all_events: List[ChronosEvent],
        avoid_events: Optional[List[ChronosEvent]] = None,
        target_date: Optional[datetime] = None,
        preferred_hours: Optional[List[int]] = None
    ) -> Optional[TimeSlot]:
        """Find alternative time slot for an event"""
        
        if not event.duration:
            return None
        
        # Determine search window
        if target_date:
            search_start = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
            search_end = target_date.replace(hour=18, minute=0, second=0, microsecond=0)
        else:
            # Search within next 14 days
            search_start = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
            search_end = search_start + timedelta(days=14)
        
        # Get conflicting events
        conflicting_events = avoid_events or []
        
        # Add all scheduled events as potential conflicts
        scheduled_events = [
            e for e in all_events 
            if (e.start_time and e.end_time and 
                e.id != event.id and
                search_start <= e.start_time <= search_end)
        ]
        conflicting_events.extend(scheduled_events)
        
        # Generate time slots
        current_time = search_start
        slot_duration = event.duration
        
        while current_time + slot_duration <= search_end:
            # Skip if not in working hours
            if current_time.hour < 9 or current_time.hour >= 18:
                current_time += timedelta(hours=1)
                continue
            
            # Skip weekends for work events
            if (current_time.weekday() >= 5 and 
                event.event_type in [EventType.MEETING, EventType.TASK]):
                current_time += timedelta(days=1)
                current_time = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
                continue
            
            # Check if preferred hour
            if preferred_hours and current_time.hour not in preferred_hours:
                current_time += timedelta(hours=1)
                continue
            
            # Create candidate slot
            candidate_slot = TimeSlot(current_time, current_time + slot_duration)
            
            # Check for conflicts
            has_conflict = False
            for conflict_event in conflicting_events:
                if conflict_event.get_time_slot():
                    if candidate_slot.overlaps_with(conflict_event.get_time_slot()):
                        has_conflict = True
                        break
            
            if not has_conflict:
                return candidate_slot
            
            # Move to next 30-minute slot
            current_time += timedelta(minutes=30)
        
        return None
    
    async def apply_replan_suggestion(
        self,
        suggestion: ReplanSuggestion,
        events: List[ChronosEvent]
    ) -> bool:
        """Apply a replanning suggestion to events"""
        
        try:
            # Find the event to replan
            event_to_replan = None
            for event in events:
                if event.id == suggestion.event_id:
                    event_to_replan = event
                    break
            
            if not event_to_replan:
                self.logger.warning(f"Event {suggestion.event_id} not found for replanning")
                return False
            
            # Update event times
            event_to_replan.start_time = suggestion.suggested_start
            event_to_replan.end_time = suggestion.suggested_end
            event_to_replan.status = EventStatus.RESCHEDULED
            event_to_replan.updated_at = datetime.utcnow()
            event_to_replan.version += 1
            
            # Log the change
            self.logger.info(
                f"Rescheduled event '{event_to_replan.title}' from "
                f"{suggestion.original_start} to {suggestion.suggested_start}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply replan suggestion: {e}")
            return False
    
    async def auto_replan_conflicts(
        self,
        events: List[ChronosEvent],
        auto_apply: bool = False
    ) -> Dict[str, Any]:
        """Automatically detect and resolve conflicts"""
        
        try:
            # Detect conflicts
            conflicts = await self.detect_conflicts(events)
            
            if not conflicts:
                return {
                    'conflicts_found': 0,
                    'conflicts_detected': 0,
                    'suggestions_generated': 0,
                    'suggestions_applied': 0,
                    'message': 'No conflicts detected',
                    'suggestions': []
                }
            
            # Generate suggestions
            suggestions = await self.suggest_replanning(conflicts, events)
            
            applied_count = 0
            
            if auto_apply and suggestions:
                # Apply high-confidence suggestions automatically
                for suggestion in suggestions:
                    if suggestion.confidence >= 0.8:
                        if await self.apply_replan_suggestion(suggestion, events):
                            applied_count += 1
            
            return {
                'conflicts_found': len(conflicts),
                'conflicts_detected': len(conflicts),
                'suggestions_generated': len(suggestions),
                'suggestions_applied': applied_count,
                'conflicts': [
                    {
                        'type': c.type.value,
                        'events': c.events,
                        'severity': c.severity,
                        'description': c.description,
                        'suggested_resolution': c.suggested_resolution
                    } for c in conflicts
                ],
                'suggestions': [
                    {
                        'event_id': s.event_id,
                        'original_start': s.original_start.isoformat(),
                        'suggested_start': s.suggested_start.isoformat() if s.suggested_start else None,
                        'reason': s.reason,
                        'confidence': s.confidence
                    } for s in suggestions
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Auto replan failed: {e}")
            return {
                'error': str(e),
                'conflicts_found': 0,
                'conflicts_detected': 0,
                'suggestions_generated': 0,
                'suggestions_applied': 0
            }

    def _events_overlap(self, event_a: ChronosEvent, event_b: ChronosEvent) -> bool:
        """Public helper primarily used for unit tests."""

        if not event_a.start_time or not event_a.end_time:
            return False
        if not event_b.start_time or not event_b.end_time:
            return False
        return event_a.conflicts_with(event_b)
