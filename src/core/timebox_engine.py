"""
Timebox Engine for Chronos - Phase 2 Feature
Advanced time blocking and scheduling optimization
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from src.core.models import ChronosEvent, Priority, EventType, TimeSlot, WorkingHours
from src.core.analytics_engine import AnalyticsEngine


@dataclass
class TimeboxSuggestion:
    """Timebox scheduling suggestion"""
    event_id: str
    suggested_start: datetime
    suggested_end: datetime
    confidence: float
    reason: str
    blocked_slots: List[TimeSlot]


class TimeboxEngine:
    """Advanced timeboxing and scheduling engine"""
    
    def __init__(self, analytics_engine: AnalyticsEngine):
        self.analytics = analytics_engine
        self.logger = logging.getLogger(__name__)
        self.working_hours = WorkingHours()
        
        # Timeboxing configuration
        self.min_block_size = timedelta(minutes=15)
        self.max_block_size = timedelta(hours=4)
        self.buffer_time = timedelta(minutes=10)
        self.focus_block_min = timedelta(hours=2)
        
        self.logger.info("Timebox Engine initialized")
    
    async def create_timeboxes(
        self, 
        events: List[ChronosEvent],
        target_date: datetime,
        strategy: str = 'priority_first'
    ) -> List[TimeboxSuggestion]:
        """Create optimized timeboxes for unscheduled events"""
        
        try:
            # Filter unscheduled or flexible events
            unscheduled = [
                e for e in events 
                if not e.start_time or e.is_flexible()
            ]
            
            if not unscheduled:
                return []
            
            # Get existing schedule for the day
            scheduled = [
                e for e in events 
                if (e.start_time and 
                    e.start_time.date() == target_date.date() and
                    not e.is_flexible())
            ]
            
            # Generate available time slots
            available_slots = self._generate_available_slots(scheduled, target_date)
            
            # Apply scheduling strategy
            if strategy == 'priority_first':
                suggestions = await self._schedule_by_priority(unscheduled, available_slots)
            elif strategy == 'duration_first':
                suggestions = await self._schedule_by_duration(unscheduled, available_slots)
            elif strategy == 'energy_optimal':
                suggestions = await self._schedule_by_energy(unscheduled, available_slots)
            else:
                suggestions = await self._schedule_by_priority(unscheduled, available_slots)
            
            self.logger.info(f"Created {len(suggestions)} timebox suggestions")
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Failed to create timeboxes: {e}")
            return []
    
    def _generate_available_slots(
        self, 
        scheduled_events: List[ChronosEvent],
        target_date: datetime
    ) -> List[TimeSlot]:
        """Generate available time slots for a day"""
        
        # Create working day boundaries
        day_start = target_date.replace(
            hour=self.working_hours.start_hour, 
            minute=0, 
            second=0, 
            microsecond=0
        )
        day_end = target_date.replace(
            hour=self.working_hours.end_hour, 
            minute=0, 
            second=0, 
            microsecond=0
        )
        
        # Create break time
        break_start = target_date.replace(
            hour=self.working_hours.break_start, 
            minute=0, 
            second=0, 
            microsecond=0
        )
        break_end = target_date.replace(
            hour=self.working_hours.break_end, 
            minute=0, 
            second=0, 
            microsecond=0
        )
        
        # Collect all blocked times
        blocked_slots = []
        
        # Add scheduled events
        for event in scheduled_events:
            if event.start_time and event.end_time:
                blocked_slots.append(TimeSlot(
                    event.start_time - self.buffer_time,  # Add buffer
                    event.end_time + self.buffer_time
                ))
        
        # Add break time
        blocked_slots.append(TimeSlot(break_start, break_end))
        
        # Sort blocked slots by start time
        blocked_slots.sort(key=lambda x: x.start)
        
        # Generate available slots between blocked slots
        available_slots = []
        current_time = day_start
        
        for blocked in blocked_slots:
            # Add slot before this blocked time
            if current_time < blocked.start:
                available_slots.append(TimeSlot(current_time, blocked.start))
            
            # Move past this blocked time
            current_time = max(current_time, blocked.end)
        
        # Add final slot after last blocked time
        if current_time < day_end:
            available_slots.append(TimeSlot(current_time, day_end))
        
        # Filter out slots that are too small
        available_slots = [
            slot for slot in available_slots 
            if slot.duration >= self.min_block_size
        ]
        
        return available_slots
    
    async def _schedule_by_priority(
        self, 
        events: List[ChronosEvent],
        available_slots: List[TimeSlot]
    ) -> List[TimeboxSuggestion]:
        """Schedule events by priority order"""
        
        suggestions = []
        
        # Sort events by priority (urgent first)
        events_by_priority = sorted(
            events, 
            key=lambda x: x.priority.value, 
            reverse=True
        )
        
        remaining_slots = available_slots.copy()
        
        for event in events_by_priority:
            duration = event.estimated_duration or timedelta(hours=1)
            
            # Find best fitting slot
            best_slot = self._find_best_slot(duration, remaining_slots)
            
            if best_slot:
                # Create suggestion
                suggestions.append(TimeboxSuggestion(
                    event_id=event.id,
                    suggested_start=best_slot.start,
                    suggested_end=best_slot.start + duration,
                    confidence=0.8,
                    reason=f"Scheduled by priority ({event.priority.name})",
                    blocked_slots=[best_slot]
                ))
                
                # Update remaining slots
                remaining_slots = self._subtract_slot_from_slots(
                    TimeSlot(best_slot.start, best_slot.start + duration),
                    remaining_slots
                )
        
        return suggestions
    
    async def _schedule_by_duration(
        self, 
        events: List[ChronosEvent],
        available_slots: List[TimeSlot]
    ) -> List[TimeboxSuggestion]:
        """Schedule events by duration (longest first)"""
        
        suggestions = []
        
        # Sort events by duration (longest first)
        events_by_duration = sorted(
            events,
            key=lambda x: x.estimated_duration or timedelta(hours=1),
            reverse=True
        )
        
        remaining_slots = available_slots.copy()
        
        for event in events_by_duration:
            duration = event.estimated_duration or timedelta(hours=1)
            
            # Find best fitting slot
            best_slot = self._find_best_slot(duration, remaining_slots)
            
            if best_slot:
                suggestions.append(TimeboxSuggestion(
                    event_id=event.id,
                    suggested_start=best_slot.start,
                    suggested_end=best_slot.start + duration,
                    confidence=0.7,
                    reason="Scheduled by duration (longest first)",
                    blocked_slots=[best_slot]
                ))
                
                # Update remaining slots
                remaining_slots = self._subtract_slot_from_slots(
                    TimeSlot(best_slot.start, best_slot.start + duration),
                    remaining_slots
                )
        
        return suggestions
    
    async def _schedule_by_energy(
        self, 
        events: List[ChronosEvent],
        available_slots: List[TimeSlot]
    ) -> List[TimeboxSuggestion]:
        """Schedule events by energy requirements (high-energy tasks first)"""
        
        suggestions = []
        
        # Get productivity patterns
        time_distribution = await self.analytics.get_time_distribution()
        
        # Sort events by energy requirements
        def energy_score(event):
            base_score = event.priority.value
            if event.event_type == EventType.BLOCK:
                base_score += 2  # Focus blocks need high energy
            elif event.event_type == EventType.TASK:
                base_score += 1
            return base_score
        
        events_by_energy = sorted(events, key=energy_score, reverse=True)
        remaining_slots = available_slots.copy()
        
        # Find peak energy hours
        peak_hours = sorted(
            time_distribution.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:3] if time_distribution else [(10, 1.0), (14, 0.8), (16, 0.6)]
        
        for event in events_by_energy:
            duration = event.estimated_duration or timedelta(hours=1)
            
            # Prefer peak hours for high-energy tasks
            if energy_score(event) >= 4:  # High-energy task
                best_slot = self._find_slot_in_preferred_hours(
                    duration, remaining_slots, [h for h, _ in peak_hours]
                )
            else:
                best_slot = self._find_best_slot(duration, remaining_slots)
            
            if best_slot:
                suggestions.append(TimeboxSuggestion(
                    event_id=event.id,
                    suggested_start=best_slot.start,
                    suggested_end=best_slot.start + duration,
                    confidence=0.85,
                    reason="Scheduled by energy level optimization",
                    blocked_slots=[best_slot]
                ))
                
                # Update remaining slots
                remaining_slots = self._subtract_slot_from_slots(
                    TimeSlot(best_slot.start, best_slot.start + duration),
                    remaining_slots
                )
        
        return suggestions
    
    def _find_best_slot(
        self, 
        duration: timedelta,
        available_slots: List[TimeSlot]
    ) -> Optional[TimeSlot]:
        """Find best fitting slot for given duration"""
        
        # Find slots that can fit the duration
        fitting_slots = [
            slot for slot in available_slots 
            if slot.duration >= duration
        ]
        
        if not fitting_slots:
            return None
        
        # Prefer slot that wastes least time
        best_slot = min(fitting_slots, key=lambda x: x.duration)
        return best_slot
    
    def _find_slot_in_preferred_hours(
        self,
        duration: timedelta,
        available_slots: List[TimeSlot],
        preferred_hours: List[int]
    ) -> Optional[TimeSlot]:
        """Find slot within preferred hours"""
        
        # Filter slots that start in preferred hours
        preferred_slots = [
            slot for slot in available_slots
            if slot.start.hour in preferred_hours and slot.duration >= duration
        ]
        
        if preferred_slots:
            return min(preferred_slots, key=lambda x: x.duration)
        
        # Fall back to any available slot
        return self._find_best_slot(duration, available_slots)
    
    def _subtract_slot_from_slots(
        self,
        used_slot: TimeSlot,
        available_slots: List[TimeSlot]
    ) -> List[TimeSlot]:
        """Remove used slot from available slots"""
        
        new_slots = []
        
        for slot in available_slots:
            if not slot.overlaps_with(used_slot):
                # No overlap, keep the slot
                new_slots.append(slot)
            else:
                # Split the slot if needed
                # Before used slot
                if slot.start < used_slot.start:
                    before_slot = TimeSlot(slot.start, used_slot.start)
                    if before_slot.duration >= self.min_block_size:
                        new_slots.append(before_slot)
                
                # After used slot
                if slot.end > used_slot.end:
                    after_slot = TimeSlot(used_slot.end, slot.end)
                    if after_slot.duration >= self.min_block_size:
                        new_slots.append(after_slot)
        
        return new_slots
    
    async def suggest_focus_blocks(
        self,
        events: List[ChronosEvent],
        target_date: datetime,
        min_duration: timedelta = None
    ) -> List[TimeboxSuggestion]:
        """Suggest dedicated focus time blocks"""
        
        if not min_duration:
            min_duration = self.focus_block_min
        
        try:
            # Find tasks that need focus time
            focus_tasks = [
                e for e in events 
                if (e.event_type == EventType.TASK and
                    e.priority in [Priority.HIGH, Priority.URGENT] and
                    (e.estimated_duration or timedelta(hours=1)) >= timedelta(minutes=45))
            ]
            
            if not focus_tasks:
                return []
            
            # Get existing schedule
            scheduled = [
                e for e in events 
                if (e.start_time and 
                    e.start_time.date() == target_date.date() and
                    not e.is_flexible())
            ]
            
            # Find long available slots
            available_slots = self._generate_available_slots(scheduled, target_date)
            focus_slots = [
                slot for slot in available_slots 
                if slot.duration >= min_duration
            ]
            
            suggestions = []
            
            for slot in focus_slots:
                # Create focus block suggestion
                suggestions.append(TimeboxSuggestion(
                    event_id=f"focus_block_{slot.start.hour}",
                    suggested_start=slot.start,
                    suggested_end=min(slot.end, slot.start + timedelta(hours=3)),
                    confidence=0.9,
                    reason=f"Dedicated focus block ({slot.duration.total_seconds() / 3600:.1f}h available)",
                    blocked_slots=[slot]
                ))
            
            return suggestions[:2]  # Maximum 2 focus blocks per day
            
        except Exception as e:
            self.logger.error(f"Failed to suggest focus blocks: {e}")
            return []
    
    async def optimize_day_structure(
        self,
        events: List[ChronosEvent],
        target_date: datetime
    ) -> Dict[str, Any]:
        """Optimize the overall structure of a day"""
        
        try:
            # Analyze current day structure
            day_events = [
                e for e in events 
                if e.start_time and e.start_time.date() == target_date.date()
            ]
            
            if not day_events:
                return {"message": "No events found for this day"}
            
            # Calculate metrics
            total_scheduled_time = sum([
                e.duration.total_seconds() for e in day_events 
                if e.duration
            ], 0) / 3600  # Convert to hours
            
            meeting_count = len([e for e in day_events if e.event_type == EventType.MEETING])
            task_count = len([e for e in day_events if e.event_type == EventType.TASK])
            
            # Find gaps and potential issues
            day_events_sorted = sorted(day_events, key=lambda x: x.start_time)
            gaps = []
            
            for i in range(len(day_events_sorted) - 1):
                current = day_events_sorted[i]
                next_event = day_events_sorted[i + 1]
                
                if current.end_time and next_event.start_time:
                    gap_duration = next_event.start_time - current.end_time
                    if gap_duration > timedelta(minutes=30):
                        gaps.append({
                            'start': current.end_time,
                            'end': next_event.start_time,
                            'duration_minutes': gap_duration.total_seconds() / 60
                        })
            
            # Generate recommendations
            recommendations = []
            
            if total_scheduled_time > 10:
                recommendations.append("Day is heavily scheduled (>10 hours). Consider moving some tasks.")
            
            if meeting_count > 5:
                recommendations.append(f"High meeting density ({meeting_count} meetings). Consider consolidating.")
            
            if len(gaps) > 3:
                recommendations.append("Many small gaps between events. Consider grouping similar activities.")
            
            for gap in gaps:
                if gap['duration_minutes'] > 60:
                    recommendations.append(
                        f"Long gap available from {gap['start'].strftime('%H:%M')} to {gap['end'].strftime('%H:%M')} "
                        f"({gap['duration_minutes']:.0f} minutes) - good for focus work."
                    )
            
            return {
                'date': target_date.date().isoformat(),
                'total_events': len(day_events),
                'total_scheduled_hours': round(total_scheduled_time, 1),
                'meeting_count': meeting_count,
                'task_count': task_count,
                'gaps': gaps,
                'recommendations': recommendations
            }
            
        except Exception as e:
            self.logger.error(f"Failed to optimize day structure: {e}")
            return {'error': str(e)}
