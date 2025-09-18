"""
Productivity Tracker Plugin for Chronos Engine
Tracks productivity metrics and provides insights
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

from src.core.models import ChronosEvent, Priority, EventType, EventStatus
from src.core.plugin_manager import AnalyticsPlugin


class ProductivityTrackerPlugin(AnalyticsPlugin):
    """Advanced productivity tracking and analytics plugin"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.productivity_data = {}
        self.daily_metrics = {}

    @property
    def name(self) -> str:
        return "productivity_tracker"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Tracks productivity metrics, focus time, and provides detailed analytics"

    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin"""
        self.logger.info("📊 Productivity Tracker Plugin initialized")
        self.context = context
        self.load_historical_data()
        return True

    async def cleanup(self):
        """Cleanup plugin resources"""
        self.save_productivity_data()
        self.logger.info("📊 Productivity Tracker Plugin cleaned up")

    def load_historical_data(self):
        """Load historical productivity data"""
        try:
            # In a real implementation, load from database or file
            self.productivity_data = {}
            self.daily_metrics = {}
            self.logger.debug("📊 Historical productivity data loaded")
        except Exception as e:
            self.logger.warning(f"📊 Could not load historical data: {e}")

    def save_productivity_data(self):
        """Save productivity data for persistence"""
        try:
            # In a real implementation, save to database or file
            self.logger.debug("📊 Productivity data saved")
        except Exception as e:
            self.logger.error(f"📊 Error saving productivity data: {e}")

    async def analyze_events(self, events: List[ChronosEvent]) -> Dict[str, Any]:
        """Analyze productivity metrics from events"""

        try:
            now = datetime.utcnow()
            today = now.date()

            # Filter today's events
            today_events = [
                e for e in events
                if e.start_time and e.start_time.date() == today
            ]

            # Calculate productivity metrics
            metrics = {
                "date": today.isoformat(),
                "total_events": len(today_events),
                "completed_events": len([e for e in today_events if e.status == EventStatus.COMPLETED]),
                "focus_time_hours": 0.0,
                "meeting_time_hours": 0.0,
                "task_time_hours": 0.0,
                "productivity_score": 0.0,
                "efficiency_rating": "unknown",
                "context_switches": 0,
                "deep_work_blocks": 0,
                "interruption_count": 0
            }

            # Calculate time spent by type
            for event in today_events:
                if event.duration:
                    hours = event.duration.total_seconds() / 3600

                    if event.event_type == EventType.MEETING:
                        metrics["meeting_time_hours"] += hours
                    elif event.event_type == EventType.TASK:
                        metrics["task_time_hours"] += hours
                    elif event.event_type == EventType.BLOCK:
                        metrics["focus_time_hours"] += hours

            # Calculate context switches
            sorted_events = sorted(
                [e for e in today_events if e.start_time],
                key=lambda x: x.start_time
            )

            prev_type = None
            for event in sorted_events:
                if prev_type and prev_type != event.event_type:
                    metrics["context_switches"] += 1
                prev_type = event.event_type

            # Identify deep work blocks (>90 minutes of focused work)
            current_block_duration = 0
            for event in sorted_events:
                if event.event_type in [EventType.TASK, EventType.BLOCK]:
                    if event.duration:
                        current_block_duration += event.duration.total_seconds() / 60
                        if current_block_duration >= 90:
                            metrics["deep_work_blocks"] += 1
                            current_block_duration = 0
                else:
                    current_block_duration = 0

            # Calculate overall productivity score
            completion_rate = metrics["completed_events"] / max(1, metrics["total_events"])
            focus_ratio = metrics["focus_time_hours"] / max(1, metrics["focus_time_hours"] + metrics["meeting_time_hours"])
            context_penalty = max(0, 1 - (metrics["context_switches"] * 0.1))

            metrics["productivity_score"] = round(
                (completion_rate * 0.4 + focus_ratio * 0.4 + context_penalty * 0.2) * 10, 2
            )

            # Determine efficiency rating
            if metrics["productivity_score"] >= 8:
                metrics["efficiency_rating"] = "excellent"
            elif metrics["productivity_score"] >= 6:
                metrics["efficiency_rating"] = "good"
            elif metrics["productivity_score"] >= 4:
                metrics["efficiency_rating"] = "fair"
            else:
                metrics["efficiency_rating"] = "needs_improvement"

            # Store daily metrics
            self.daily_metrics[today.isoformat()] = metrics

            self.logger.info(f"📊 Productivity analysis complete: {metrics['productivity_score']}/10")
            return metrics

        except Exception as e:
            self.logger.error(f"📊 Error analyzing productivity: {e}")
            return {"error": str(e)}

    async def generate_insights(self, events: List[ChronosEvent]) -> List[Dict[str, Any]]:
        """Generate productivity insights and recommendations"""

        try:
            insights = []
            metrics = await self.analyze_events(events)

            if "error" in metrics:
                return [{
                    "type": "error",
                    "title": "Analysis Error",
                    "message": "Could not generate productivity insights",
                    "priority": "low"
                }]

            # Insight: Low completion rate
            completion_rate = metrics["completed_events"] / max(1, metrics["total_events"])
            if completion_rate < 0.6:
                insights.append({
                    "type": "completion_rate",
                    "title": "Low Task Completion",
                    "message": f"Only {completion_rate:.1%} of tasks completed today. Consider reducing task load or breaking large tasks into smaller ones.",
                    "priority": "high",
                    "actionable": True,
                    "suggestion": "Review and prioritize your task list"
                })

            # Insight: Too many context switches
            if metrics["context_switches"] > 5:
                insights.append({
                    "type": "context_switching",
                    "title": "High Context Switching",
                    "message": f"{metrics['context_switches']} context switches detected. This can reduce productivity by up to 25%.",
                    "priority": "medium",
                    "actionable": True,
                    "suggestion": "Try batching similar activities together"
                })

            # Insight: Lack of deep work
            if metrics["deep_work_blocks"] == 0 and metrics["task_time_hours"] > 2:
                insights.append({
                    "type": "deep_work",
                    "title": "No Deep Work Blocks",
                    "message": "No focused work sessions over 90 minutes detected. Deep work is crucial for complex tasks.",
                    "priority": "high",
                    "actionable": True,
                    "suggestion": "Schedule 2-hour focused work blocks with no interruptions"
                })

            # Insight: Meeting overload
            meeting_ratio = metrics["meeting_time_hours"] / max(1, metrics["meeting_time_hours"] + metrics["task_time_hours"])
            if meeting_ratio > 0.6:
                insights.append({
                    "type": "meeting_overload",
                    "title": "Meeting Heavy Day",
                    "message": f"{meeting_ratio:.1%} of time spent in meetings. Consider declining non-essential meetings.",
                    "priority": "medium",
                    "actionable": True,
                    "suggestion": "Audit your meetings and decline those where you're not essential"
                })

            # Insight: Excellent productivity
            if metrics["productivity_score"] >= 8:
                insights.append({
                    "type": "positive_feedback",
                    "title": "Excellent Productivity!",
                    "message": f"Outstanding productivity score: {metrics['productivity_score']}/10. Keep up the great work!",
                    "priority": "low",
                    "actionable": False,
                    "suggestion": "Continue current work patterns"
                })

            # Insight: Productivity trend (if we have historical data)
            if len(self.daily_metrics) > 1:
                recent_scores = [
                    m["productivity_score"] for m in list(self.daily_metrics.values())[-7:]
                ]
                if len(recent_scores) >= 3:
                    trend = (recent_scores[-1] - recent_scores[0]) / len(recent_scores)
                    if trend > 0.5:
                        insights.append({
                            "type": "trend_positive",
                            "title": "Improving Productivity",
                            "message": f"Your productivity has been trending upward over the last {len(recent_scores)} days.",
                            "priority": "low",
                            "actionable": False,
                            "suggestion": "Continue current improvement strategies"
                        })
                    elif trend < -0.5:
                        insights.append({
                            "type": "trend_negative",
                            "title": "Declining Productivity",
                            "message": f"Your productivity has been trending downward. Consider reviewing your work patterns.",
                            "priority": "medium",
                            "actionable": True,
                            "suggestion": "Take breaks and reassess your schedule"
                        })

            self.logger.info(f"📊 Generated {len(insights)} productivity insights")
            return insights

        except Exception as e:
            self.logger.error(f"📊 Error generating insights: {e}")
            return [{
                "type": "error",
                "title": "Insight Generation Error",
                "message": f"Could not generate insights: {e}",
                "priority": "low"
            }]

    async def get_weekly_summary(self) -> Dict[str, Any]:
        """Generate weekly productivity summary"""

        try:
            now = datetime.utcnow()
            week_start = now - timedelta(days=now.weekday())

            weekly_data = {
                date: metrics for date, metrics in self.daily_metrics.items()
                if datetime.fromisoformat(date).date() >= week_start.date()
            }

            if not weekly_data:
                return {"message": "No data available for this week"}

            # Calculate weekly averages
            avg_productivity = sum(m["productivity_score"] for m in weekly_data.values()) / len(weekly_data)
            total_focus_hours = sum(m["focus_time_hours"] for m in weekly_data.values())
            total_meeting_hours = sum(m["meeting_time_hours"] for m in weekly_data.values())
            avg_context_switches = sum(m["context_switches"] for m in weekly_data.values()) / len(weekly_data)

            summary = {
                "week_start": week_start.date().isoformat(),
                "days_analyzed": len(weekly_data),
                "average_productivity_score": round(avg_productivity, 2),
                "total_focus_hours": round(total_focus_hours, 1),
                "total_meeting_hours": round(total_meeting_hours, 1),
                "average_context_switches": round(avg_context_switches, 1),
                "best_day": max(weekly_data.keys(), key=lambda d: weekly_data[d]["productivity_score"]),
                "focus_to_meeting_ratio": round(total_focus_hours / max(1, total_meeting_hours), 2)
            }

            return summary

        except Exception as e:
            self.logger.error(f"📊 Error generating weekly summary: {e}")
            return {"error": str(e)}