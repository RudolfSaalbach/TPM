"""
Unit tests for ReplanEngine - Testing Conflict Detection & Resolution
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

from src.core.replan_engine import ReplanEngine, ReplanSuggestion, Conflict, ConflictType
from src.core.models import ChronosEvent, Priority, EventType, EventStatus
from src.core.analytics_engine import AnalyticsEngine
from src.core.timebox_engine import TimeboxEngine


class TestReplanEngine:
    """Test suite for ReplanEngine with 80%+ coverage"""
    
    @pytest.fixture
    def mock_analytics(self):
        """Mock analytics engine"""
        analytics = Mock(spec=AnalyticsEngine)
        analytics.get_productivity_metrics = AsyncMock(return_value={
            'completion_rate': 0.8,
            'average_productivity': 3.5
        })
        return analytics
    
    @pytest.fixture
    def mock_timebox(self):
        """Mock timebox engine"""
        timebox = Mock(spec=TimeboxEngine)
        timebox.find_optimal_slots = AsyncMock(return_value=[])
        return timebox
    
    @pytest.fixture
    def replan_engine(self, mock_analytics, mock_timebox):
        """Create ReplanEngine instance for testing"""
        return ReplanEngine(mock_analytics, mock_timebox)
    
    @pytest.fixture
    def overlapping_events(self):
        """Create overlapping events for conflict testing"""
        base_time = datetime(2025, 1, 15, 10, 0)
        
        return [
            ChronosEvent(
                id="overlap_1",
                title="Meeting A",
                start_time=base_time,
                end_time=base_time + timedelta(hours=2),
                priority=Priority.HIGH,
                event_type=EventType.MEETING
            ),
            ChronosEvent(
                id="overlap_2",
                title="Meeting B",
                start_time=base_time + timedelta(minutes=30),
                end_time=base_time + timedelta(hours=1.5),
                priority=Priority.URGENT,
                event_type=EventType.MEETING
            )
        ]
    
    @pytest.mark.asyncio
    async def test_detect_conflicts_overlap(self, replan_engine, overlapping_events):
        """Test detection of overlapping events"""
        
        conflicts = await replan_engine.detect_conflicts(overlapping_events)
        
        assert len(conflicts) > 0
        
        overlap_conflicts = [c for c in conflicts if c.type == ConflictType.OVERLAP]
        assert len(overlap_conflicts) > 0
        
        conflict = overlap_conflicts[0]
        assert len(conflict.events) == 2
        assert 'overlap_1' in conflict.events
        assert 'overlap_2' in conflict.events
        assert conflict.severity > 0.5  # Should be significant conflict
    
    @pytest.mark.asyncio
    async def test_generate_replan_suggestions(self, replan_engine, overlapping_events):
        """Test generation of replanning suggestions"""
        
        suggestions = await replan_engine.generate_replan_suggestions(overlapping_events)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        
        for suggestion in suggestions:
            assert isinstance(suggestion, ReplanSuggestion)
            assert suggestion.event_id in ['overlap_1', 'overlap_2']
            assert 0.0 <= suggestion.confidence <= 1.0
            assert suggestion.reason is not None
    
    @pytest.mark.asyncio
    async def test_auto_replan_conflicts(self, replan_engine, overlapping_events):
        """Test automatic conflict resolution"""
        
        result = await replan_engine.auto_replan_conflicts(overlapping_events, auto_apply=False)
        
        assert 'conflicts_detected' in result
        assert 'suggestions' in result
        assert result['conflicts_detected'] > 0
        assert len(result['suggestions']) > 0
    
    def test_events_overlap(self, replan_engine):
        """Test overlap detection logic"""
        
        base_time = datetime(2025, 1, 15, 10, 0)
        
        # Overlapping events
        event1 = ChronosEvent(
            id="e1",
            start_time=base_time,
            end_time=base_time + timedelta(hours=2)
        )
        event2 = ChronosEvent(
            id="e2",
            start_time=base_time + timedelta(hours=1),
            end_time=base_time + timedelta(hours=3)
        )
        
        assert replan_engine._events_overlap(event1, event2)
        
        # Non-overlapping events
        event3 = ChronosEvent(
            id="e3",
            start_time=base_time + timedelta(hours=3),
            end_time=base_time + timedelta(hours=4)
        )
        
        assert not replan_engine._events_overlap(event1, event3)
