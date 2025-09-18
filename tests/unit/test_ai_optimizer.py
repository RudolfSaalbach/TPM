"""
Unit tests for AIOptimizer - Testing Core Logic
Comprehensive test coverage for AI optimization functionality
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

from src.core.ai_optimizer import AIOptimizer, OptimizationSuggestion
from src.core.models import ChronosEvent, Priority, EventType, EventStatus
from src.core.analytics_engine import AnalyticsEngine


class TestAIOptimizer:
    """Test suite for AIOptimizer with 80%+ coverage"""
    
    @pytest.fixture
    def mock_analytics(self):
        """Mock analytics engine"""
        analytics = Mock(spec=AnalyticsEngine)
        analytics.get_productivity_metrics = AsyncMock(return_value={
            'total_events': 50,
            'completion_rate': 0.75,
            'average_productivity': 3.2,
            'events_per_day': 5.5
        })
        analytics.get_priority_distribution = AsyncMock(return_value={
            'URGENT': 5, 'HIGH': 15, 'MEDIUM': 25, 'LOW': 5
        })
        return analytics
    
    @pytest.fixture
    def ai_optimizer(self, mock_analytics):
        """Create AIOptimizer instance for testing"""
        return AIOptimizer(mock_analytics)
    
    @pytest.fixture
    def sample_events(self):
        """Create sample events for testing"""
        base_time = datetime(2025, 1, 15, 9, 0)
        
        return [
            ChronosEvent(
                id="event_1",
                title="Team Meeting",
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                priority=Priority.HIGH,
                event_type=EventType.MEETING,
                status=EventStatus.SCHEDULED
            ),
            ChronosEvent(
                id="event_2", 
                title="Focus Work",
                start_time=base_time + timedelta(hours=2),
                end_time=base_time + timedelta(hours=4),
                priority=Priority.URGENT,
                event_type=EventType.TASK,
                requires_focus=True
            ),
            ChronosEvent(
                id="event_3",
                title="Client Call",
                start_time=base_time + timedelta(hours=5),
                end_time=base_time + timedelta(hours=6),
                priority=Priority.MEDIUM,
                event_type=EventType.MEETING
            )
        ]
    
    @pytest.mark.asyncio
    async def test_optimize_schedule_basic(self, ai_optimizer, sample_events):
        """Test basic schedule optimization"""
        
        suggestions = await ai_optimizer.optimize_schedule(sample_events)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        
        for suggestion in suggestions:
            assert isinstance(suggestion, OptimizationSuggestion)
            assert hasattr(suggestion, 'event_id')
            assert hasattr(suggestion, 'suggestion_type')
            assert hasattr(suggestion, 'confidence')
            assert 0.0 <= suggestion.confidence <= 1.0
    
    @pytest.mark.asyncio
    async def test_priority_optimization(self, ai_optimizer, sample_events):
        """Test priority-based optimization suggestions"""
        
        suggestions = await ai_optimizer.optimize_schedule(sample_events)
        
        # Should prioritize URGENT events
        urgent_suggestions = [s for s in suggestions if 'urgent' in s.description.lower()]
        assert len(urgent_suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_conflict_detection(self, ai_optimizer):
        """Test conflict detection in overlapping events"""
        
        base_time = datetime(2025, 1, 15, 10, 0)
        
        conflicting_events = [
            ChronosEvent(
                id="conflict_1",
                title="Meeting A",
                start_time=base_time,
                end_time=base_time + timedelta(hours=2),
                priority=Priority.HIGH
            ),
            ChronosEvent(
                id="conflict_2",
                title="Meeting B", 
                start_time=base_time + timedelta(minutes=30),
                end_time=base_time + timedelta(hours=1.5),
                priority=Priority.URGENT
            )
        ]
        
        suggestions = await ai_optimizer.optimize_schedule(conflicting_events)
        
        # Should detect and suggest resolution for conflicts
        conflict_suggestions = [s for s in suggestions if 'conflict' in s.description.lower() or 'overlap' in s.description.lower()]
        assert len(conflict_suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_empty_events_list(self, ai_optimizer):
        """Test optimization with empty events list"""
        
        suggestions = await ai_optimizer.optimize_schedule([])
        
        assert isinstance(suggestions, list)
        assert len(suggestions) == 0
    
    @pytest.mark.asyncio
    async def test_suggestion_confidence_levels(self, ai_optimizer, sample_events):
        """Test that suggestions have appropriate confidence levels"""
        
        suggestions = await ai_optimizer.optimize_schedule(sample_events)
        
        # All suggestions should have confidence between 0 and 1
        for suggestion in suggestions:
            assert 0.0 <= suggestion.confidence <= 1.0
        
        # High-priority optimization should have higher confidence
        high_priority_suggestions = [s for s in suggestions if s.confidence > 0.7]
        assert len(high_priority_suggestions) > 0
    
    def test_calculate_priority_score(self, ai_optimizer):
        """Test priority score calculation"""
        
        high_priority_event = ChronosEvent(
            id="test", title="Test", priority=Priority.URGENT
        )
        low_priority_event = ChronosEvent(
            id="test2", title="Test2", priority=Priority.LOW
        )
        
        high_score = ai_optimizer._calculate_priority_score(high_priority_event)
        low_score = ai_optimizer._calculate_priority_score(low_priority_event)
        
        assert high_score > low_score
        assert high_score == 4.0  # URGENT priority
        assert low_score == 1.0   # LOW priority
    
    def test_detect_scheduling_conflicts(self, ai_optimizer):
        """Test scheduling conflict detection"""
        
        base_time = datetime(2025, 1, 15, 14, 0)
        
        events = [
            ChronosEvent(
                id="event1",
                title="Event 1",
                start_time=base_time,
                end_time=base_time + timedelta(hours=2)
            ),
            ChronosEvent(
                id="event2",
                title="Event 2",
                start_time=base_time + timedelta(minutes=30),
                end_time=base_time + timedelta(hours=2.5)
            )
        ]
        
        conflicts = ai_optimizer._detect_scheduling_conflicts(events)
        
        assert len(conflicts) > 0
        assert conflicts[0]['type'] == 'overlap'
        assert set(conflicts[0]['events']) == {'event1', 'event2'}
    
    @pytest.mark.asyncio
    async def test_error_handling(self, ai_optimizer):
        """Test error handling with invalid data"""
        
        # Test with event having None start_time
        invalid_events = [
            ChronosEvent(
                id="invalid",
                title="Invalid Event",
                start_time=None,
                end_time=None
            )
        ]
        
        # Should not crash and return empty suggestions
        suggestions = await ai_optimizer.optimize_schedule(invalid_events)
        assert isinstance(suggestions, list)
