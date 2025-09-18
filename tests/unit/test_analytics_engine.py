"""
Unit tests for AnalyticsEngine - Testing Data Analysis Logic
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from src.core.analytics_engine import AnalyticsEngine
from src.core.models import ChronosEvent, AnalyticsData, Priority, EventType, EventStatus


class TestAnalyticsEngine:
    """Test suite for AnalyticsEngine with 80%+ coverage"""
    
    @pytest.fixture
    def analytics_engine(self):
        """Create AnalyticsEngine instance for testing"""
        return AnalyticsEngine()
    
    @pytest.fixture
    def sample_events(self):
        """Create sample events for analytics testing"""
        base_time = datetime(2025, 1, 1, 9, 0)
        
        return [
            ChronosEvent(
                id="analytics_1",
                title="Completed Task",
                start_time=base_time,
                end_time=base_time + timedelta(hours=2),
                priority=Priority.HIGH,
                event_type=EventType.TASK,
                status=EventStatus.COMPLETED,
                productivity_score=4.2
            ),
            ChronosEvent(
                id="analytics_2",
                title="In Progress Meeting",
                start_time=base_time + timedelta(days=1),
                end_time=base_time + timedelta(days=1, hours=1),
                priority=Priority.MEDIUM,
                event_type=EventType.MEETING,
                status=EventStatus.IN_PROGRESS,
                productivity_score=3.8
            )
        ]
    
    @pytest.mark.asyncio
    async def test_track_event(self, analytics_engine):
        """Test event tracking functionality"""
        
        event = ChronosEvent(
            id="track_test",
            title="Test Event",
            start_time=datetime(2025, 1, 15, 10, 0),
            end_time=datetime(2025, 1, 15, 11, 0),
            priority=Priority.HIGH,
            productivity_score=4.0
        )
        
        # Mock database session
        with patch('src.core.analytics_engine.db_service.get_session') as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            await analytics_engine.track_event(event)
            
            # Should attempt to store analytics data
            mock_session.assert_called_once()
    
    def test_calculate_event_metrics(self, analytics_engine):
        """Test event metrics calculation"""
        
        event = ChronosEvent(
            id="metrics_test",
            title="Test Event",
            start_time=datetime(2025, 1, 15, 10, 0),
            end_time=datetime(2025, 1, 15, 12, 0),  # 2 hours
            priority=Priority.HIGH,
            event_type=EventType.TASK,
            status=EventStatus.COMPLETED,
            productivity_score=4.5,
            requires_focus=True
        )
        
        metrics = analytics_engine._calculate_event_metrics(event)
        
        # Verify duration metrics
        assert 'duration_hours' in metrics
        assert metrics['duration_hours'] == 2.0
        assert 'duration_minutes' in metrics
        assert metrics['duration_minutes'] == 120.0
        
        # Verify priority scoring
        assert 'priority_score' in metrics
        assert metrics['priority_score'] == 3.0  # HIGH priority
        
        # Verify type scoring
        assert 'type_score' in metrics
        assert metrics['type_score'] == 3.0  # TASK type
        
        # Verify status progress
        assert 'status_progress' in metrics
        assert metrics['status_progress'] == 1.0  # COMPLETED
        
        # Verify AI metrics
        assert 'productivity_score' in metrics
        assert metrics['productivity_score'] == 4.5
        
        # Verify focus metrics
        assert 'requires_focus' in metrics
        assert metrics['requires_focus'] == 1.0
    
    @pytest.mark.asyncio
    async def test_get_productivity_metrics(self, analytics_engine):
        """Test productivity metrics calculation"""
        
        # Mock database queries
        with patch('src.core.analytics_engine.db_service.get_session') as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Mock query results
            mock_events = [
                Mock(
                    id="1",
                    status=EventStatus.COMPLETED.value,
                    start_time=datetime(2025, 1, 1, 9, 0),
                    end_time=datetime(2025, 1, 1, 11, 0)
                ),
                Mock(
                    id="2", 
                    status=EventStatus.SCHEDULED.value,
                    start_time=datetime(2025, 1, 2, 10, 0),
                    end_time=datetime(2025, 1, 2, 12, 0)
                )
            ]
            
            mock_analytics = [
                Mock(metrics={'productivity_score': 4.0}),
                Mock(metrics={'productivity_score': 3.5})
            ]
            
            # Configure mock returns
            mock_result = AsyncMock()
            mock_result.scalars.return_value.all.return_value = mock_events
            mock_session_instance.execute.return_value = mock_result
            
            # Second execute call for analytics data
            mock_analytics_result = AsyncMock()
            mock_analytics_result.scalars.return_value.all.return_value = mock_analytics
            mock_session_instance.execute.side_effect = [mock_result, mock_analytics_result]
            
            metrics = await analytics_engine.get_productivity_metrics(30)
            
            # Verify metrics structure
            assert 'total_events' in metrics
            assert 'completed_events' in metrics
            assert 'completion_rate' in metrics
            assert 'total_hours' in metrics
            assert 'average_productivity' in metrics
            assert 'events_per_day' in metrics
            
            # Verify calculations
            assert metrics['total_events'] == 2
            assert metrics['completed_events'] == 1
            assert metrics['completion_rate'] == 0.5  # 1/2
    
    def test_priority_score_mapping(self, analytics_engine):
        """Test priority score mapping is correct"""
        
        priority_events = [
            (Priority.LOW, 1.0),
            (Priority.MEDIUM, 2.0),
            (Priority.HIGH, 3.0),
            (Priority.URGENT, 4.0)
        ]
        
        for priority, expected_score in priority_events:
            event = ChronosEvent(
                id="test",
                title="Test",
                priority=priority
            )
            
            metrics = analytics_engine._calculate_event_metrics(event)
            assert metrics['priority_score'] == expected_score
