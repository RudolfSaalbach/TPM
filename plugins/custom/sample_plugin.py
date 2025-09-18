"""
Sample Plugin for Chronos Engine - COMPLETE WORKING IMPLEMENTATION
Demonstrates event processing and scheduling suggestions
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

from src.core.models import ChronosEvent, Priority, EventType
from src.core.plugin_manager import EventPlugin, SchedulingPlugin


class SampleEventPlugin(EventPlugin):
    """Sample event processing plugin - COMPLETE IMPLEMENTATION"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @property
    def name(self) -> str:
        return "sample_event_plugin"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Sample plugin that demonstrates event processing and tagging"
    
    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin"""
        self.logger.info("🔌 Sample Event Plugin initialized")
        self.context = context
        return True
    
    async def cleanup(self):
        """Cleanup plugin resources"""
        self.logger.info("🔌 Sample Event Plugin cleaned up")
    
    async def process_event(self, event: ChronosEvent) -> ChronosEvent:
        """Process an event - Add sample enhancements"""
        
        try:
            # Add sample tag if not present
            if "processed" not in event.tags:
                event.tags.append("processed")
            
            # Enhance event based on title keywords
            title_lower = event.title.lower()
            
            # Auto-detect meeting types
            if any(keyword in title_lower for keyword in ["meeting", "call", "sync", "standup"]):
                if event.event_type != EventType.MEETING:
                    event.event_type = EventType.MEETING
                if "meeting" not in event.tags:
                    event.tags.append("meeting")
            
            # Auto-detect urgent items
            if any(keyword in title_lower for keyword in ["urgent", "asap", "emergency"]):
                if event.priority != Priority.URGENT:
                    event.priority = Priority.URGENT
                if "urgent" not in event.tags:
                    event.tags.append("urgent")
            
            # Add time-based tags
            if event.start_time:
                hour = event.start_time.hour
                if hour < 10:
                    event.tags.append("morning")
                elif hour < 14:
                    event.tags.append("midday") 
                elif hour < 18:
                    event.tags.append("afternoon")
                else:
                    event.tags.append("evening")
            
            # Estimate preparation time based on event type
            if event.event_type == EventType.MEETING:
                event.preparation_time = timedelta(minutes=10)
                event.buffer_time = timedelta(minutes=5)
            elif event.event_type == EventType.TASK:
                event.preparation_time = timedelta(minutes=5)
                event.buffer_time = timedelta(minutes=15)
            
            # Add sample productivity score
            if event.productivity_score is None:
                # Simple scoring based on priority and type
                score = 3.0  # Default
                
                if event.priority == Priority.URGENT:
                    score += 1.0
                elif event.priority == Priority.HIGH:
                    score += 0.5
                elif event.priority == Priority.LOW:
                    score -= 0.5
                
                if event.event_type == EventType.BLOCK:
                    score += 0.5
                elif event.event_type == EventType.MEETING and len(event.attendees) > 5:
                    score -= 0.5  # Large meetings less productive
                
                event.productivity_score = min(5.0, max(1.0, score))
            
            self.logger.debug(f"🔌 Processed event: {event.title} (tags: {event.tags})")
            return event
            
        except Exception as e:
            self.logger.error(f"🔌 Error processing event {event.title}: {e}")
            return event  # Return original event if processing fails


class SampleSchedulingPlugin(SchedulingPlugin):
    """Sample scheduling plugin - COMPLETE IMPLEMENTATION"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @property
    def name(self) -> str:
        return "sample_scheduling_plugin"
    
    @property 
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Sample plugin that provides intelligent scheduling suggestions"
    
    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin"""
        self.logger.info("🔌 Sample Scheduling Plugin initialized")
        self.context = context
        return True
    
    async def cleanup(self):
        """Cleanup plugin resources"""
        self.logger.info("🔌 Sample Scheduling Plugin cleaned up")
    
    async def suggest_schedule(
        self, 
        events: List[ChronosEvent],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate scheduling suggestions"""
        
        try:
            suggestions = []
            
            # Analyze current events
            now = datetime.utcnow()
            today_events = [
                e for e in events 
                if e.start_time and e.start_time.date() == now.date()
            ]
            
            # Suggest morning focus blocks
            morning_meetings = [
                e for e in today_events
                if e.start_time and 8 <= e.start_time.hour <= 11 and e.event_type == EventType.MEETING
            ]
            
            if len(morning_meetings) > 2:
                suggestions.append({
                    "type": "schedule_optimization",
                    "priority": "medium",
                    "title": "Morning Meeting Overload",
                    "suggestion": f"You have {len(morning_meetings)} meetings scheduled for this morning. Consider moving some to the afternoon to preserve focus time.",
                    "confidence": 0.8,
                    "plugin_name": self.name,
                    "affected_events": [e.id for e in morning_meetings]
                })
            
            # Suggest lunch breaks
            lunch_time_events = [
                e for e in today_events
                if e.start_time and 12 <= e.start_time.hour <= 13
            ]
            
            if len(lunch_time_events) > 1:
                suggestions.append({
                    "type": "wellness",
                    "priority": "low",
                    "title": "Lunch Break Conflict",
                    "suggestion": "You have events scheduled during typical lunch hours. Consider protecting 12:00-13:00 for a proper break.",
                    "confidence": 0.6,
                    "plugin_name": self.name,
                    "affected_events": [e.id for e in lunch_time_events]
                })
            
            # Suggest batching similar events
            meetings = [e for e in today_events if e.event_type == EventType.MEETING]
            tasks = [e for e in today_events if e.event_type == EventType.TASK]
            
            if len(meetings) >= 3 and len(tasks) >= 2:
                # Check if meetings and tasks are interleaved
                events_sorted = sorted(today_events, key=lambda x: x.start_time or now)
                
                context_switches = 0
                prev_type = None
                for event in events_sorted:
                    if prev_type and prev_type != event.event_type:
                        context_switches += 1
                    prev_type = event.event_type
                
                if context_switches > 4:
                    suggestions.append({
                        "type": "batching",
                        "priority": "high",
                        "title": "Context Switching",
                        "suggestion": f"You have {context_switches} context switches between meetings and tasks today. Consider batching similar activities together.",
                        "confidence": 0.9,
                        "plugin_name": self.name,
                        "affected_events": [e.id for e in events_sorted]
                    })
            
            # Suggest end-of-day planning
            late_events = [
                e for e in today_events
                if e.start_time and e.start_time.hour >= 17
            ]
            
            if len(late_events) > 0:
                urgent_late = [e for e in late_events if e.priority == Priority.URGENT]
                if not urgent_late:  # Only non-urgent events
                    suggestions.append({
                        "type": "work_life_balance",
                        "priority": "medium",
                        "title": "Late Day Schedule",
                        "suggestion": f"You have {len(late_events)} non-urgent events after 5 PM. Consider rescheduling to preserve work-life balance.",
                        "confidence": 0.7,
                        "plugin_name": self.name,
                        "affected_events": [e.id for e in late_events]
                    })
            
            # Suggest focus time blocks
            if len(tasks) > 0 and len(meetings) > 2:
                focus_needed = sum(
                    (e.duration.total_seconds() / 3600) if e.duration else 1
                    for e in tasks
                )
                
                if focus_needed > 2:  # More than 2 hours of task work
                    suggestions.append({
                        "type": "focus_time",
                        "priority": "high", 
                        "title": "Focus Time Needed",
                        "suggestion": f"You need {focus_needed:.1f} hours for task work today. Consider blocking 2-hour focus sessions between meetings.",
                        "confidence": 0.85,
                        "plugin_name": self.name,
                        "affected_events": [e.id for e in tasks]
                    })
            
            self.logger.info(f"🔌 Generated {len(suggestions)} scheduling suggestions")
            return suggestions
            
        except Exception as e:
            self.logger.error(f"🔌 Error generating suggestions: {e}")
            return [{
                "type": "error",
                "priority": "low",
                "title": "Plugin Error",
                "suggestion": "Scheduling plugin encountered an error. Suggestions temporarily unavailable.",
                "confidence": 0.1,
                "plugin_name": self.name
            }]
