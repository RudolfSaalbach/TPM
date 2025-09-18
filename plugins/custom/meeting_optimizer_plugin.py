"""
Meeting Optimizer Plugin for Chronos Engine
Analyzes and optimizes meeting schedules and efficiency
"""

import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Any, Optional, Tuple
import re

from src.core.models import ChronosEvent, Priority, EventType, EventStatus
from src.core.plugin_manager import SchedulingPlugin


class MeetingOptimizerPlugin(SchedulingPlugin):
    """Intelligent meeting optimization and scheduling plugin"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.meeting_patterns = {}
        self.efficiency_rules = {
            "max_daily_meetings": 6,
            "min_break_between_meetings": 15,  # minutes
            "max_consecutive_meetings": 3,
            "ideal_meeting_duration": 30,  # minutes
            "focus_time_blocks": [
                (time(9, 0), time(11, 0)),   # Morning focus
                (time(14, 0), time(16, 0))   # Afternoon focus
            ],
            "no_meeting_times": [
                (time(12, 0), time(13, 0))   # Lunch break
            ]
        }

    @property
    def name(self) -> str:
        return "meeting_optimizer"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Optimizes meeting schedules for maximum productivity and efficiency"

    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin"""
        self.logger.info("📅 Meeting Optimizer Plugin initialized")
        self.context = context

        # Load custom rules from context if provided
        if "meeting_rules" in context:
            self.efficiency_rules.update(context["meeting_rules"])

        return True

    async def cleanup(self):
        """Cleanup plugin resources"""
        self.logger.info("📅 Meeting Optimizer Plugin cleaned up")

    def analyze_meeting_efficiency(self, meeting: ChronosEvent) -> Dict[str, Any]:
        """Analyze a single meeting for efficiency metrics"""

        analysis = {
            "event_id": meeting.id,
            "title": meeting.title,
            "efficiency_score": 5.0,  # Out of 10
            "issues": [],
            "suggestions": []
        }

        try:
            # Check duration
            if meeting.duration:
                duration_minutes = meeting.duration.total_seconds() / 60

                if duration_minutes > 60:
                    analysis["issues"].append("Long meeting (>60 minutes)")
                    analysis["suggestions"].append("Consider breaking into multiple shorter sessions")
                    analysis["efficiency_score"] -= 1.0
                elif duration_minutes > 90:
                    analysis["issues"].append("Very long meeting (>90 minutes)")
                    analysis["efficiency_score"] -= 2.0

                if duration_minutes % 15 != 0:
                    analysis["issues"].append("Non-standard duration (not in 15-minute increments)")
                    analysis["suggestions"].append("Standardize to 15, 30, 45, or 60 minutes")
                    analysis["efficiency_score"] -= 0.5

            # Check attendee count
            attendee_count = len(meeting.attendees)
            if attendee_count > 8:
                analysis["issues"].append(f"Large meeting ({attendee_count} attendees)")
                analysis["suggestions"].append("Consider if all attendees are necessary")
                analysis["efficiency_score"] -= 1.0
            elif attendee_count > 12:
                analysis["issues"].append(f"Very large meeting ({attendee_count} attendees)")
                analysis["efficiency_score"] -= 2.0

            # Check if meeting has agenda (inferred from description)
            if not meeting.description or len(meeting.description.strip()) < 10:
                analysis["issues"].append("No apparent agenda")
                analysis["suggestions"].append("Add detailed agenda to description")
                analysis["efficiency_score"] -= 1.0

            # Check timing
            if meeting.start_time:
                meeting_time = meeting.start_time.time()

                # Check if during lunch
                for start_time, end_time in self.efficiency_rules["no_meeting_times"]:
                    if start_time <= meeting_time <= end_time:
                        analysis["issues"].append("Scheduled during lunch break")
                        analysis["suggestions"].append("Reschedule outside of lunch hours")
                        analysis["efficiency_score"] -= 1.5

                # Check if during focus time
                for start_time, end_time in self.efficiency_rules["focus_time_blocks"]:
                    if start_time <= meeting_time <= end_time:
                        analysis["issues"].append("Scheduled during prime focus time")
                        analysis["suggestions"].append("Consider moving to less productive hours")
                        analysis["efficiency_score"] -= 0.5

                # Early or late meetings
                if meeting_time < time(8, 0):
                    analysis["issues"].append("Very early meeting")
                    analysis["efficiency_score"] -= 0.5
                elif meeting_time > time(17, 0):
                    analysis["issues"].append("Late meeting")
                    analysis["efficiency_score"] -= 0.5

            # Check meeting type from title
            title_lower = meeting.title.lower()
            meeting_type = self.classify_meeting_type(title_lower)

            if meeting_type == "status_update" and attendee_count > 4:
                analysis["issues"].append("Status meeting with too many attendees")
                analysis["suggestions"].append("Consider async status updates or smaller groups")
                analysis["efficiency_score"] -= 1.0

            if meeting_type == "brainstorm" and attendee_count > 6:
                analysis["issues"].append("Brainstorming session too large")
                analysis["suggestions"].append("Limit brainstorming to 4-6 people for best results")
                analysis["efficiency_score"] -= 0.5

            # Normalize score
            analysis["efficiency_score"] = max(0, min(10, analysis["efficiency_score"]))

            return analysis

        except Exception as e:
            self.logger.error(f"📅 Error analyzing meeting {meeting.id}: {e}")
            analysis["issues"].append("Analysis error occurred")
            return analysis

    def classify_meeting_type(self, title: str) -> str:
        """Classify meeting type based on title keywords"""

        if any(word in title for word in ["standup", "daily", "sync", "check-in"]):
            return "status_update"
        elif any(word in title for word in ["brainstorm", "ideation", "planning", "strategy"]):
            return "brainstorm"
        elif any(word in title for word in ["review", "retrospective", "post-mortem"]):
            return "review"
        elif any(word in title for word in ["training", "workshop", "tutorial"]):
            return "learning"
        elif any(word in title for word in ["interview", "candidate", "hiring"]):
            return "interview"
        elif any(word in title for word in ["1:1", "one-on-one", "1-1"]):
            return "one_on_one"
        elif any(word in title for word in ["all-hands", "town-hall", "company"]):
            return "company_wide"
        else:
            return "general"

    async def suggest_schedule(
        self,
        events: List[ChronosEvent],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate meeting optimization suggestions"""

        try:
            suggestions = []
            now = datetime.utcnow()
            today = now.date()

            # Get today's meetings
            meetings = [
                e for e in events
                if e.event_type == EventType.MEETING and
                   e.start_time and e.start_time.date() == today
            ]

            if not meetings:
                return suggestions

            # Sort meetings by start time
            meetings.sort(key=lambda x: x.start_time or now)

            # Check daily meeting limit
            if len(meetings) > self.efficiency_rules["max_daily_meetings"]:
                suggestions.append({
                    "type": "meeting_overload",
                    "priority": "high",
                    "title": "Too Many Meetings",
                    "suggestion": f"You have {len(meetings)} meetings today (limit: {self.efficiency_rules['max_daily_meetings']}). Consider rescheduling or declining non-essential meetings.",
                    "confidence": 0.9,
                    "plugin_name": self.name,
                    "affected_events": [m.id for m in meetings[self.efficiency_rules["max_daily_meetings"]:]]
                })

            # Check for back-to-back meetings
            consecutive_count = 0
            for i in range(len(meetings) - 1):
                current = meetings[i]
                next_meeting = meetings[i + 1]

                if current.end_time and next_meeting.start_time:
                    gap = (next_meeting.start_time - current.end_time).total_seconds() / 60

                    if gap < self.efficiency_rules["min_break_between_meetings"]:
                        consecutive_count += 1

                        if consecutive_count == 1:  # First back-to-back meeting
                            suggestions.append({
                                "type": "meeting_breaks",
                                "priority": "medium",
                                "title": "Back-to-Back Meetings",
                                "suggestion": f"You have meetings with less than {self.efficiency_rules['min_break_between_meetings']} minutes between them. Consider adding buffer time.",
                                "confidence": 0.8,
                                "plugin_name": self.name,
                                "affected_events": [current.id, next_meeting.id]
                            })

            # Check for meetings during focus time
            focus_time_meetings = []
            for meeting in meetings:
                if meeting.start_time:
                    meeting_time = meeting.start_time.time()
                    for start_time, end_time in self.efficiency_rules["focus_time_blocks"]:
                        if start_time <= meeting_time <= end_time:
                            focus_time_meetings.append(meeting)
                            break

            if focus_time_meetings:
                suggestions.append({
                    "type": "focus_time_protection",
                    "priority": "medium",
                    "title": "Meetings During Focus Time",
                    "suggestion": f"{len(focus_time_meetings)} meetings scheduled during prime focus hours. Consider protecting 9-11 AM and 2-4 PM for deep work.",
                    "confidence": 0.7,
                    "plugin_name": self.name,
                    "affected_events": [m.id for m in focus_time_meetings]
                })

            # Analyze individual meeting efficiency
            inefficient_meetings = []
            for meeting in meetings:
                analysis = self.analyze_meeting_efficiency(meeting)
                if analysis["efficiency_score"] < 6.0:
                    inefficient_meetings.append({
                        "meeting": meeting,
                        "analysis": analysis
                    })

            if inefficient_meetings:
                meeting_titles = [m["meeting"].title for m in inefficient_meetings[:3]]
                suggestions.append({
                    "type": "meeting_efficiency",
                    "priority": "medium",
                    "title": "Inefficient Meetings Detected",
                    "suggestion": f"Some meetings may be inefficient: {', '.join(meeting_titles)}. Review agendas, attendees, and durations.",
                    "confidence": 0.8,
                    "plugin_name": self.name,
                    "affected_events": [m["meeting"].id for m in inefficient_meetings],
                    "details": [m["analysis"] for m in inefficient_meetings]
                })

            # Suggest meeting-free periods
            work_hours = 8  # Assume 8-hour workday
            meeting_hours = sum(
                (m.duration.total_seconds() / 3600) if m.duration else 0.5
                for m in meetings
            )

            meeting_ratio = meeting_hours / work_hours
            if meeting_ratio > 0.5:
                suggestions.append({
                    "type": "meeting_free_time",
                    "priority": "high",
                    "title": "Need Meeting-Free Time",
                    "suggestion": f"Meetings occupy {meeting_ratio:.1%} of your day. Consider blocking 2-4 hours for uninterrupted work.",
                    "confidence": 0.9,
                    "plugin_name": self.name,
                    "affected_events": []
                })

            # Pattern analysis for recurring meetings
            recurring_patterns = self.analyze_recurring_patterns(meetings)
            if recurring_patterns:
                suggestions.extend(recurring_patterns)

            self.logger.info(f"📅 Generated {len(suggestions)} meeting optimization suggestions")
            return suggestions

        except Exception as e:
            self.logger.error(f"📅 Error generating meeting suggestions: {e}")
            return [{
                "type": "error",
                "priority": "low",
                "title": "Meeting Analysis Error",
                "suggestion": "Could not analyze meetings. Please check plugin configuration.",
                "confidence": 0.1,
                "plugin_name": self.name
            }]

    def analyze_recurring_patterns(self, meetings: List[ChronosEvent]) -> List[Dict[str, Any]]:
        """Analyze patterns in recurring meetings"""

        suggestions = []

        try:
            # Group meetings by similar titles (potential recurring meetings)
            meeting_groups = {}
            for meeting in meetings:
                # Simple pattern matching - group by first 3 words
                title_words = meeting.title.lower().split()[:3]
                key = " ".join(title_words)

                if key not in meeting_groups:
                    meeting_groups[key] = []
                meeting_groups[key].append(meeting)

            # Analyze groups with multiple meetings
            for group_name, group_meetings in meeting_groups.items():
                if len(group_meetings) >= 2:  # Potential recurring meeting

                    # Check if all meetings have same duration
                    durations = [m.duration for m in group_meetings if m.duration]
                    if len(set(durations)) > 1:
                        suggestions.append({
                            "type": "recurring_consistency",
                            "priority": "low",
                            "title": f"Inconsistent Duration: {group_name.title()}",
                            "suggestion": "Recurring meetings have inconsistent durations. Consider standardizing.",
                            "confidence": 0.6,
                            "plugin_name": self.name,
                            "affected_events": [m.id for m in group_meetings]
                        })

            return suggestions

        except Exception as e:
            self.logger.error(f"📅 Error analyzing recurring patterns: {e}")
            return []

    async def optimize_meeting_schedule(
        self,
        meetings: List[ChronosEvent],
        constraints: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Suggest optimal meeting schedule reorganization"""

        try:
            optimizations = []

            # Sort meetings by priority and flexibility
            flexible_meetings = [
                m for m in meetings
                if m.priority in [Priority.LOW, Priority.MEDIUM] and
                   len(m.attendees) <= 4  # Smaller meetings are more flexible
            ]

            # Suggest batching meetings
            if len(flexible_meetings) >= 3:
                optimizations.append({
                    "type": "meeting_batching",
                    "title": "Batch Similar Meetings",
                    "description": f"Consider grouping {len(flexible_meetings)} flexible meetings together to create larger blocks of uninterrupted time.",
                    "suggested_times": [
                        "Morning batch: 10:00-12:00",
                        "Afternoon batch: 15:00-17:00"
                    ],
                    "affected_meetings": [m.id for m in flexible_meetings],
                    "estimated_focus_time_gained": "2-3 hours"
                })

            return optimizations

        except Exception as e:
            self.logger.error(f"📅 Error optimizing meeting schedule: {e}")
            return []