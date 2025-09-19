"""
Event scheduling modes - Parallel vs Auto-Plan
Implements the two-mode system for handling event conflicts
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.core.models import ChronosEvent, TimeSlot
from src.core.schema_extensions import EventModeDB


class EventMode(Enum):
    """Event scheduling modes"""
    FREE = "free"  # Allow overlaps, just show warnings
    AUTO_PLAN = "auto_plan"  # Actively avoid conflicts and suggest alternatives


class ConflictResolution(Enum):
    """Conflict resolution strategies"""
    SUGGEST = "suggest"  # Suggest alternative times
    RESCHEDULE = "reschedule"  # Automatically reschedule
    IGNORE = "ignore"  # Allow conflicts


@dataclass
class EventModeConfig:
    """Configuration for event mode"""
    event_id: str
    mode: EventMode = EventMode.FREE
    auto_reschedule: bool = False
    conflict_resolution: ConflictResolution = ConflictResolution.SUGGEST
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_db_model(self) -> EventModeDB:
        """Convert to database model"""
        return EventModeDB(
            event_id=self.event_id,
            mode=self.mode.value,
            auto_reschedule=self.auto_reschedule,
            conflict_resolution=self.conflict_resolution.value,
            created_at=self.created_at,
            updated_at=self.updated_at
        )


@dataclass
class ConflictInfo:
    """Information about event conflicts"""
    conflicting_event: ChronosEvent
    overlap_start: datetime
    overlap_end: datetime
    overlap_duration: timedelta

    @property
    def overlap_minutes(self) -> int:
        """Get overlap duration in minutes"""
        return int(self.overlap_duration.total_seconds() / 60)


@dataclass
class SchedulingSuggestion:
    """Suggested alternative time slot"""
    start_time: datetime
    end_time: datetime
    score: float  # Higher is better (0.0 to 1.0)
    reason: str
    conflicts: List[ConflictInfo] = field(default_factory=list)

    @property
    def duration(self) -> timedelta:
        """Get duration of suggested slot"""
        return self.end_time - self.start_time


class EventModeService:
    """Service for managing event modes and conflict resolution"""

    def __init__(self, db_session_factory=None):
        self.db_session_factory = db_session_factory

    async def get_event_mode(self, event_id: str) -> EventModeConfig:
        """Get event mode configuration"""
        if not self.db_session_factory:
            return EventModeConfig(event_id=event_id)

        try:
            from sqlalchemy import select

            async with self.db_session_factory() as session:
                result = await session.execute(
                    select(EventModeDB).where(EventModeDB.event_id == event_id)
                )
                db_mode = result.scalar_one_or_none()

                if db_mode:
                    return EventModeConfig(
                        event_id=db_mode.event_id,
                        mode=EventMode(db_mode.mode),
                        auto_reschedule=db_mode.auto_reschedule,
                        conflict_resolution=ConflictResolution(db_mode.conflict_resolution),
                        created_at=db_mode.created_at,
                        updated_at=db_mode.updated_at
                    )
                else:
                    # Return default configuration
                    return EventModeConfig(event_id=event_id)

        except Exception as e:
            print(f"Warning: Could not get event mode: {e}")
            return EventModeConfig(event_id=event_id)

    async def set_event_mode(self, config: EventModeConfig) -> bool:
        """Set event mode configuration"""
        if not self.db_session_factory:
            return False

        try:
            from sqlalchemy import select

            async with self.db_session_factory() as session:
                # Check if configuration already exists
                result = await session.execute(
                    select(EventModeDB).where(EventModeDB.event_id == config.event_id)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing
                    existing.mode = config.mode.value
                    existing.auto_reschedule = config.auto_reschedule
                    existing.conflict_resolution = config.conflict_resolution.value
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new
                    new_config = config.to_db_model()
                    session.add(new_config)

                await session.commit()
                return True

        except Exception as e:
            print(f"Warning: Could not set event mode: {e}")
            return False

    def detect_conflicts(self, target_event: ChronosEvent,
                        existing_events: List[ChronosEvent]) -> List[ConflictInfo]:
        """Detect conflicts between target event and existing events"""
        conflicts = []

        if not target_event.start_time or not target_event.end_time:
            return conflicts

        target_start = target_event.start_time
        target_end = target_event.end_time

        for event in existing_events:
            # Skip the same event
            if event.id == target_event.id:
                continue

            # Skip events without times
            if not event.start_time or not event.end_time:
                continue

            # Check for overlap
            overlap_start = max(target_start, event.start_time)
            overlap_end = min(target_end, event.end_time)

            if overlap_start < overlap_end:
                conflict = ConflictInfo(
                    conflicting_event=event,
                    overlap_start=overlap_start,
                    overlap_end=overlap_end,
                    overlap_duration=overlap_end - overlap_start
                )
                conflicts.append(conflict)

        return conflicts

    def suggest_alternative_times(self, target_event: ChronosEvent,
                                 existing_events: List[ChronosEvent],
                                 search_days: int = 7,
                                 max_suggestions: int = 5) -> List[SchedulingSuggestion]:
        """Suggest alternative time slots for an event"""
        if not target_event.start_time or not target_event.end_time:
            return []

        duration = target_event.end_time - target_event.start_time
        suggestions = []

        # Get current time and search range
        now = datetime.now()
        search_start = max(now, target_event.start_time.replace(hour=0, minute=0, second=0))
        search_end = search_start + timedelta(days=search_days)

        # Generate potential time slots
        potential_slots = self._generate_potential_slots(
            search_start, search_end, duration, target_event
        )

        # Score each slot
        for slot_start in potential_slots:
            slot_end = slot_start + duration

            # Create temporary event for conflict checking
            temp_event = ChronosEvent(
                id=target_event.id,
                title=target_event.title,
                start_time=slot_start,
                end_time=slot_end
            )

            # Check conflicts
            conflicts = self.detect_conflicts(temp_event, existing_events)

            # Calculate score
            score = self._calculate_slot_score(
                slot_start, slot_end, conflicts, target_event
            )

            # Create suggestion
            reason = self._generate_suggestion_reason(
                slot_start, conflicts, target_event
            )

            suggestion = SchedulingSuggestion(
                start_time=slot_start,
                end_time=slot_end,
                score=score,
                reason=reason,
                conflicts=conflicts
            )

            suggestions.append(suggestion)

        # Sort by score (best first) and return top suggestions
        suggestions.sort(key=lambda s: s.score, reverse=True)
        return suggestions[:max_suggestions]

    def _generate_potential_slots(self, search_start: datetime,
                                 search_end: datetime, duration: timedelta,
                                 target_event: ChronosEvent) -> List[datetime]:
        """Generate potential time slots"""
        slots = []

        # Define working hours (could be configurable)
        work_start_hour = 9
        work_end_hour = 17

        current_date = search_start.date()
        end_date = search_end.date()

        while current_date <= end_date:
            # Skip weekends for work events (configurable later)
            if current_date.weekday() < 5:  # Monday = 0, Sunday = 6

                # Generate slots throughout the work day
                work_start = datetime.combine(current_date, datetime.min.time().replace(hour=work_start_hour))
                work_end = datetime.combine(current_date, datetime.min.time().replace(hour=work_end_hour))

                # Generate slots every 30 minutes
                current_time = work_start
                while current_time + duration <= work_end:
                    # Skip slots in the past
                    if current_time >= datetime.now():
                        slots.append(current_time)

                    current_time += timedelta(minutes=30)

            current_date += timedelta(days=1)

        return slots

    def _calculate_slot_score(self, slot_start: datetime, slot_end: datetime,
                             conflicts: List[ConflictInfo],
                             target_event: ChronosEvent) -> float:
        """Calculate score for a time slot (0.0 to 1.0, higher is better)"""
        score = 1.0

        # Penalize conflicts
        if conflicts:
            conflict_penalty = len(conflicts) * 0.3
            score -= min(conflict_penalty, 0.8)  # Max 80% penalty

        # Prefer times close to original (if specified)
        if target_event.start_time:
            original_start = target_event.start_time
            time_diff = abs((slot_start - original_start).total_seconds()) / 3600  # Hours
            time_penalty = min(time_diff * 0.05, 0.2)  # Max 20% penalty
            score -= time_penalty

        # Prefer working hours
        hour = slot_start.hour
        if 9 <= hour <= 17:
            score += 0.1
        elif 8 <= hour <= 18:
            pass  # No bonus or penalty
        else:
            score -= 0.2  # Outside normal hours

        # Prefer mid-week
        weekday = slot_start.weekday()
        if 1 <= weekday <= 3:  # Tuesday to Thursday
            score += 0.05

        # Prefer not too far in the future
        days_ahead = (slot_start.date() - datetime.now().date()).days
        if days_ahead <= 2:
            score += 0.1
        elif days_ahead >= 7:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _generate_suggestion_reason(self, slot_start: datetime,
                                   conflicts: List[ConflictInfo],
                                   target_event: ChronosEvent) -> str:
        """Generate human-readable reason for suggestion"""
        reasons = []

        if not conflicts:
            reasons.append("No conflicts")

        if target_event.start_time:
            original_start = target_event.start_time
            time_diff = slot_start - original_start

            if abs(time_diff.total_seconds()) < 3600:  # Less than 1 hour
                reasons.append("Close to original time")
            elif time_diff.days == 0:
                reasons.append("Same day")
            elif time_diff.days == 1:
                reasons.append("Next day")

        # Check if it's in working hours
        hour = slot_start.hour
        if 9 <= hour <= 17:
            reasons.append("During work hours")

        # Check weekday
        weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday = slot_start.weekday()
        if weekday < 5:
            reasons.append(f"{weekday_names[weekday]}")

        if conflicts:
            conflict_count = len(conflicts)
            reasons.append(f"{conflict_count} minor conflict{'s' if conflict_count > 1 else ''}")

        return ", ".join(reasons) if reasons else "Available slot"

    async def handle_event_scheduling(self, event: ChronosEvent,
                                    existing_events: List[ChronosEvent]) -> Dict[str, Any]:
        """Handle event scheduling based on mode"""
        mode_config = await self.get_event_mode(event.id)

        result = {
            "event": event,
            "mode": mode_config.mode.value,
            "conflicts": [],
            "suggestions": [],
            "action_taken": "none",
            "warnings": []
        }

        # Detect conflicts
        conflicts = self.detect_conflicts(event, existing_events)
        result["conflicts"] = [
            {
                "event_id": c.conflicting_event.id,
                "event_title": c.conflicting_event.title,
                "overlap_minutes": c.overlap_minutes,
                "overlap_start": c.overlap_start.isoformat(),
                "overlap_end": c.overlap_end.isoformat()
            }
            for c in conflicts
        ]

        if mode_config.mode == EventMode.FREE:
            # Free mode: just warn about conflicts
            if conflicts:
                result["warnings"].append(f"Event conflicts with {len(conflicts)} other event(s)")
            result["action_taken"] = "warning_only"

        elif mode_config.mode == EventMode.AUTO_PLAN:
            # Auto-plan mode: actively resolve conflicts
            if conflicts:
                suggestions = self.suggest_alternative_times(event, existing_events)
                result["suggestions"] = [
                    {
                        "start_time": s.start_time.isoformat(),
                        "end_time": s.end_time.isoformat(),
                        "score": s.score,
                        "reason": s.reason,
                        "conflict_count": len(s.conflicts)
                    }
                    for s in suggestions
                ]

                if mode_config.auto_reschedule and suggestions:
                    # Automatically reschedule to best suggestion
                    best_suggestion = suggestions[0]
                    if best_suggestion.score > 0.7:  # Only auto-reschedule if score is good
                        event.start_time = best_suggestion.start_time
                        event.end_time = best_suggestion.end_time
                        result["action_taken"] = "auto_rescheduled"
                        result["warnings"].append(f"Event automatically rescheduled to {best_suggestion.reason}")
                    else:
                        result["action_taken"] = "suggestions_provided"
                        result["warnings"].append("Conflicts found, suggestions provided")
                else:
                    result["action_taken"] = "suggestions_provided"
                    result["warnings"].append("Conflicts found, suggestions provided")

        return result


# Global event mode service
event_mode_service = EventModeService()