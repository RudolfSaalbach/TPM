"""
Wellness Monitor Plugin for Chronos Engine
Monitors work-life balance and suggests wellness improvements
"""

import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Any, Optional
from enum import Enum

from src.core.models import ChronosEvent, Priority, EventType, EventStatus
from src.core.plugin_manager import EventPlugin


class WellnessMetric(Enum):
    """Wellness metric types"""
    WORK_LIFE_BALANCE = "work_life_balance"
    BREAK_FREQUENCY = "break_frequency"
    OVERWORK_DETECTION = "overwork_detection"
    STRESS_INDICATORS = "stress_indicators"
    RECOVERY_TIME = "recovery_time"


class WellnessMonitorPlugin(EventPlugin):
    """Monitor and promote healthy work habits and wellness"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.wellness_rules = {
            "max_daily_work_hours": 8,
            "min_break_duration": 15,  # minutes
            "max_continuous_work": 90,  # minutes without break
            "lunch_break_duration": 60,  # minutes
            "end_of_workday": time(18, 0),
            "start_of_workday": time(9, 0),
            "weekend_work_limit": 2,  # hours per weekend day
            "max_weekly_hours": 45
        }
        self.daily_metrics = {}
        self.wellness_alerts = []

    @property
    def name(self) -> str:
        return "wellness_monitor"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Monitors work-life balance and promotes healthy work habits"

    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin"""
        self.logger.info("🌱 Wellness Monitor Plugin initialized")
        self.context = context

        # Load custom wellness rules from context
        if "wellness_rules" in context:
            self.wellness_rules.update(context["wellness_rules"])

        return True

    async def cleanup(self):
        """Cleanup plugin resources"""
        self.logger.info("🌱 Wellness Monitor Plugin cleaned up")

    async def process_event(self, event: ChronosEvent) -> ChronosEvent:
        """Process an event and add wellness-related insights"""

        try:
            # Add wellness tags based on event characteristics
            if event.start_time:
                event_time = event.start_time.time()

                # Tag late work events
                if event_time > self.wellness_rules["end_of_workday"]:
                    if "late_work" not in event.tags:
                        event.tags.append("late_work")

                # Tag early work events
                if event_time < self.wellness_rules["start_of_workday"]:
                    if "early_work" not in event.tags:
                        event.tags.append("early_work")

                # Tag weekend work
                if event.start_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
                    if "weekend_work" not in event.tags:
                        event.tags.append("weekend_work")

                # Tag lunch break conflicts
                lunch_start = time(12, 0)
                lunch_end = time(13, 0)
                if lunch_start <= event_time <= lunch_end and event.event_type != EventType.REMINDER:
                    if "lunch_conflict" not in event.tags:
                        event.tags.append("lunch_conflict")

            # Detect stress indicators in event titles/descriptions
            stress_keywords = [
                "urgent", "asap", "emergency", "critical", "deadline",
                "crisis", "fire", "escalation", "blocker"
            ]

            text_to_check = f"{event.title} {event.description or ''}".lower()
            if any(keyword in text_to_check for keyword in stress_keywords):
                if "stress_indicator" not in event.tags:
                    event.tags.append("stress_indicator")

            # Add wellness score
            wellness_score = self.calculate_event_wellness_score(event)
            if not hasattr(event, 'wellness_score'):
                event.wellness_score = wellness_score

            return event

        except Exception as e:
            self.logger.error(f"🌱 Error processing event {event.id}: {e}")
            return event

    def calculate_event_wellness_score(self, event: ChronosEvent) -> float:
        """Calculate wellness score for an individual event (1-10 scale)"""

        score = 7.0  # Neutral baseline

        try:
            if event.start_time:
                event_time = event.start_time.time()

                # Penalize late work
                if event_time > self.wellness_rules["end_of_workday"]:
                    hours_late = (event_time.hour - self.wellness_rules["end_of_workday"].hour)
                    score -= min(3.0, hours_late * 0.5)

                # Penalize early work
                if event_time < self.wellness_rules["start_of_workday"]:
                    hours_early = (self.wellness_rules["start_of_workday"].hour - event_time.hour)
                    score -= min(2.0, hours_early * 0.3)

                # Penalize weekend work
                if event.start_time.weekday() >= 5:
                    score -= 2.0

                # Penalize lunch conflicts
                if time(12, 0) <= event_time <= time(13, 0):
                    score -= 1.5

            # Penalize stress indicators
            if "stress_indicator" in event.tags:
                score -= 1.0

            # Penalize very long events
            if event.duration and event.duration.total_seconds() > 7200:  # > 2 hours
                score -= 1.0

            # Bonus for breaks and personal time
            if event.event_type == EventType.REMINDER and "break" in event.title.lower():
                score += 1.0

            return max(1.0, min(10.0, score))

        except Exception as e:
            self.logger.error(f"🌱 Error calculating wellness score: {e}")
            return 5.0

    async def analyze_daily_wellness(self, events: List[ChronosEvent]) -> Dict[str, Any]:
        """Analyze daily wellness metrics"""

        try:
            now = datetime.utcnow()
            today = now.date()

            # Filter today's work events
            work_events = [
                e for e in events
                if e.start_time and e.start_time.date() == today and
                   e.event_type in [EventType.MEETING, EventType.TASK, EventType.BLOCK]
            ]

            metrics = {
                "date": today.isoformat(),
                "total_work_hours": 0.0,
                "break_count": 0,
                "longest_work_stretch": 0,  # minutes
                "late_work_events": 0,
                "weekend_work_hours": 0.0,
                "stress_events": 0,
                "wellness_score": 7.0,
                "issues": [],
                "recommendations": []
            }

            # Calculate total work hours
            total_work_minutes = 0
            for event in work_events:
                if event.duration:
                    total_work_minutes += event.duration.total_seconds() / 60

            metrics["total_work_hours"] = round(total_work_minutes / 60, 1)

            # Count breaks
            break_events = [
                e for e in events
                if e.start_time and e.start_time.date() == today and
                   ("break" in e.title.lower() or e.event_type == EventType.REMINDER)
            ]
            metrics["break_count"] = len(break_events)

            # Calculate longest work stretch
            sorted_events = sorted(
                [e for e in work_events if e.start_time and e.end_time],
                key=lambda x: x.start_time
            )

            current_stretch = 0
            max_stretch = 0
            last_end_time = None

            for event in sorted_events:
                if last_end_time and (event.start_time - last_end_time).total_seconds() > 900:  # 15 min break
                    max_stretch = max(max_stretch, current_stretch)
                    current_stretch = 0

                if event.duration:
                    current_stretch += event.duration.total_seconds() / 60

                last_end_time = event.end_time

            metrics["longest_work_stretch"] = max(max_stretch, current_stretch)

            # Count late work and stress events
            for event in work_events:
                if "late_work" in event.tags:
                    metrics["late_work_events"] += 1

                if "stress_indicator" in event.tags:
                    metrics["stress_events"] += 1

                if "weekend_work" in event.tags and event.duration:
                    metrics["weekend_work_hours"] += event.duration.total_seconds() / 3600

            # Calculate overall wellness score
            score = 10.0

            # Work hours impact
            if metrics["total_work_hours"] > self.wellness_rules["max_daily_work_hours"]:
                excess_hours = metrics["total_work_hours"] - self.wellness_rules["max_daily_work_hours"]
                score -= min(4.0, excess_hours * 0.5)
                metrics["issues"].append(f"Worked {excess_hours:.1f} hours over limit")
                metrics["recommendations"].append("Consider delegating or postponing non-urgent tasks")

            # Break frequency impact
            expected_breaks = max(1, int(metrics["total_work_hours"] / 2))  # One break every 2 hours
            if metrics["break_count"] < expected_breaks:
                score -= 1.0
                metrics["issues"].append("Insufficient breaks")
                metrics["recommendations"].append("Schedule regular 15-minute breaks every 2 hours")

            # Continuous work impact
            if metrics["longest_work_stretch"] > self.wellness_rules["max_continuous_work"]:
                score -= 2.0
                metrics["issues"].append(f"Worked {metrics['longest_work_stretch']:.0f} minutes without break")
                metrics["recommendations"].append("Take breaks every 90 minutes to maintain focus")

            # Late work impact
            if metrics["late_work_events"] > 0:
                score -= min(2.0, metrics["late_work_events"] * 0.5)
                metrics["issues"].append(f"{metrics['late_work_events']} late work sessions")
                metrics["recommendations"].append("Establish clear work-end boundaries")

            # Stress indicators impact
            if metrics["stress_events"] > 2:
                score -= 1.5
                metrics["issues"].append("High stress day detected")
                metrics["recommendations"].append("Consider stress management techniques and workload review")

            metrics["wellness_score"] = max(1.0, min(10.0, score))

            # Store daily metrics
            self.daily_metrics[today.isoformat()] = metrics

            return metrics

        except Exception as e:
            self.logger.error(f"🌱 Error analyzing daily wellness: {e}")
            return {"error": str(e)}

    async def generate_wellness_alerts(self, events: List[ChronosEvent]) -> List[Dict[str, Any]]:
        """Generate wellness alerts and recommendations"""

        try:
            alerts = []
            metrics = await self.analyze_daily_wellness(events)

            if "error" in metrics:
                return []

            # High-priority alerts
            if metrics["wellness_score"] < 4.0:
                alerts.append({
                    "type": "wellness_critical",
                    "priority": "high",
                    "title": "Wellness Alert: Critical",
                    "message": f"Daily wellness score: {metrics['wellness_score']:.1f}/10. Immediate attention needed.",
                    "recommendations": metrics["recommendations"][:2],
                    "urgency": "immediate"
                })

            # Overwork detection
            if metrics["total_work_hours"] > self.wellness_rules["max_daily_work_hours"] + 2:
                alerts.append({
                    "type": "overwork_warning",
                    "priority": "high",
                    "title": "Overwork Warning",
                    "message": f"Worked {metrics['total_work_hours']} hours today. Risk of burnout.",
                    "recommendations": ["Stop working and rest", "Review workload distribution"],
                    "urgency": "immediate"
                })

            # Break reminders
            if metrics["longest_work_stretch"] > 120:  # 2 hours
                alerts.append({
                    "type": "break_reminder",
                    "priority": "medium",
                    "title": "Break Needed",
                    "message": f"Working for {metrics['longest_work_stretch']:.0f} minutes without break.",
                    "recommendations": ["Take a 15-minute break now", "Stand up and stretch"],
                    "urgency": "soon"
                })

            # Work-life balance
            if metrics["late_work_events"] >= 3:
                alerts.append({
                    "type": "work_life_balance",
                    "priority": "medium",
                    "title": "Work-Life Balance",
                    "message": "Multiple late work sessions detected today.",
                    "recommendations": ["Set firm work-end boundaries", "Review task prioritization"],
                    "urgency": "today"
                })

            # Stress management
            if metrics["stress_events"] >= 3:
                alerts.append({
                    "type": "stress_management",
                    "priority": "medium",
                    "title": "High Stress Day",
                    "message": f"{metrics['stress_events']} high-stress events detected.",
                    "recommendations": ["Practice deep breathing", "Consider postponing non-urgent tasks"],
                    "urgency": "today"
                })

            # Positive reinforcement
            if metrics["wellness_score"] >= 8.0:
                alerts.append({
                    "type": "positive_wellness",
                    "priority": "low",
                    "title": "Great Wellness Day!",
                    "message": f"Excellent wellness score: {metrics['wellness_score']:.1f}/10",
                    "recommendations": ["Keep up the healthy work habits!"],
                    "urgency": "none"
                })

            # Weekly pattern alerts
            if len(self.daily_metrics) >= 5:  # Have at least 5 days of data
                weekly_alerts = self.analyze_weekly_wellness_patterns()
                alerts.extend(weekly_alerts)

            self.logger.info(f"🌱 Generated {len(alerts)} wellness alerts")
            return alerts

        except Exception as e:
            self.logger.error(f"🌱 Error generating wellness alerts: {e}")
            return []

    def analyze_weekly_wellness_patterns(self) -> List[Dict[str, Any]]:
        """Analyze wellness patterns over the week"""

        try:
            alerts = []
            recent_days = list(self.daily_metrics.values())[-7:]  # Last 7 days

            if len(recent_days) < 5:
                return alerts

            # Calculate weekly averages
            avg_daily_hours = sum(d["total_work_hours"] for d in recent_days) / len(recent_days)
            avg_wellness_score = sum(d["wellness_score"] for d in recent_days) / len(recent_days)
            total_weekly_hours = sum(d["total_work_hours"] for d in recent_days)

            # Weekly overwork pattern
            if avg_daily_hours > self.wellness_rules["max_daily_work_hours"]:
                alerts.append({
                    "type": "weekly_overwork",
                    "priority": "high",
                    "title": "Weekly Overwork Pattern",
                    "message": f"Averaging {avg_daily_hours:.1f} hours/day this week (limit: {self.wellness_rules['max_daily_work_hours']}).",
                    "recommendations": ["Review weekly workload", "Consider delegating tasks"],
                    "urgency": "this_week"
                })

            # Declining wellness trend
            if len(recent_days) >= 3:
                recent_scores = [d["wellness_score"] for d in recent_days[-3:]]
                if all(recent_scores[i] > recent_scores[i+1] for i in range(len(recent_scores)-1)):
                    alerts.append({
                        "type": "declining_wellness",
                        "priority": "medium",
                        "title": "Declining Wellness Trend",
                        "message": "Wellness scores have been declining over the past 3 days.",
                        "recommendations": ["Take a longer break", "Review work patterns"],
                        "urgency": "today"
                    })

            return alerts

        except Exception as e:
            self.logger.error(f"🌱 Error analyzing weekly patterns: {e}")
            return []