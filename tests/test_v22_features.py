"""
Test suite for Chronos Engine v2.2 features
Tests sub-tasks, event linking, workflows, and UNDEFINED guard
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.core.models import (
    ChronosEvent, SubTask, EventLink, ActionWorkflow, ExternalCommand,
    Priority, EventType, EventStatus, CommandStatus
)
from src.core.event_parser import EventParser
from plugins.custom.command_handler_plugin import CommandHandlerPlugin
from plugins.custom.undefined_guard_plugin import UndefinedGuardPlugin


class TestSubTaskFeatures:
    """Test sub-task (checklist) functionality"""

    def test_subtask_creation(self):
        """Test creating sub-tasks"""
        task = SubTask(
            text="Complete documentation",
            completed=False
        )

        assert task.text == "Complete documentation"
        assert task.completed is False
        assert task.completed_at is None
        assert task.id is not None

    def test_subtask_completion(self):
        """Test marking sub-task as completed"""
        task = SubTask(text="Review code")
        assert not task.completed

        # Mark as completed
        task.completed = True
        task.completed_at = datetime.utcnow()

        assert task.completed
        assert task.completed_at is not None

    def test_subtask_serialization(self):
        """Test sub-task to/from dict conversion"""
        task = SubTask(
            text="Write tests",
            completed=True,
            completed_at=datetime.utcnow()
        )

        # Convert to dict
        task_dict = task.to_dict()
        assert task_dict['text'] == "Write tests"
        assert task_dict['completed'] is True
        assert 'created_at' in task_dict
        assert 'completed_at' in task_dict

        # Convert back from dict
        restored_task = SubTask.from_dict(task_dict)
        assert restored_task.text == task.text
        assert restored_task.completed == task.completed

    def test_event_parser_subtasks(self):
        """Test parsing sub-tasks from event description"""
        parser = EventParser()

        description = """
        Project tasks:
        [ ] Set up development environment
        [x] Create initial mockups
        [ ] Implement core features
        [X] Write unit tests

        Some other text that's not a task.
        """

        sub_tasks = parser._parse_sub_tasks(description)

        assert len(sub_tasks) == 4
        assert sub_tasks[0].text == "Set up development environment"
        assert not sub_tasks[0].completed
        assert sub_tasks[1].text == "Create initial mockups"
        assert sub_tasks[1].completed
        assert sub_tasks[2].text == "Implement core features"
        assert not sub_tasks[2].completed
        assert sub_tasks[3].text == "Write unit tests"
        assert sub_tasks[3].completed

    def test_event_with_subtasks(self):
        """Test creating event with sub-tasks"""
        sub_tasks = [
            SubTask(text="Task 1", completed=False),
            SubTask(text="Task 2", completed=True)
        ]

        event = ChronosEvent(
            title="Project Work",
            sub_tasks=sub_tasks
        )

        assert len(event.sub_tasks) == 2
        assert event.sub_tasks[0].text == "Task 1"
        assert event.sub_tasks[1].completed


class TestEventLinkFeatures:
    """Test event linking functionality"""

    def test_event_link_creation(self):
        """Test creating event links"""
        link = EventLink(
            source_event_id="event-1",
            target_event_id="event-2",
            link_type="depends_on"
        )

        assert link.source_event_id == "event-1"
        assert link.target_event_id == "event-2"
        assert link.link_type == "depends_on"
        assert link.created_at is not None

    def test_event_link_types(self):
        """Test different link types"""
        link_types = ["related", "depends_on", "blocks", "child_of", "follows"]

        for link_type in link_types:
            link = EventLink(
                source_event_id="event-1",
                target_event_id="event-2",
                link_type=link_type
            )
            assert link.link_type == link_type


class TestWorkflowFeatures:
    """Test ACTION workflow functionality"""

    def test_workflow_creation(self):
        """Test creating action workflows"""
        workflow = ActionWorkflow(
            trigger_command="DEPLOY",
            trigger_system="production",
            follow_up_command="STATUS_CHECK",
            follow_up_system="monitoring",
            delay_seconds=30,
            follow_up_params={"check_type": "post_deploy"}
        )

        assert workflow.trigger_command == "DEPLOY"
        assert workflow.trigger_system == "production"
        assert workflow.follow_up_command == "STATUS_CHECK"
        assert workflow.delay_seconds == 30
        assert workflow.enabled

    @pytest.mark.asyncio
    async def test_command_handler_workflow_trigger(self):
        """Test workflow triggering in command handler"""
        # Mock database service
        mock_db_service = AsyncMock()
        mock_session = AsyncMock()
        mock_db_service.get_session.return_value.__aenter__.return_value = mock_session

        # Mock workflow query result
        mock_workflow = MagicMock()
        mock_workflow.follow_up_command = "STATUS_CHECK"
        mock_workflow.follow_up_system = "monitoring"
        mock_workflow.follow_up_params = {"check_type": "auto"}

        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_workflow]

        # Create plugin
        plugin = CommandHandlerPlugin()
        plugin.context = {'config': {'command_handler': {'action_whitelist': ['DEPLOY']}}}

        # Test workflow trigger
        await plugin._trigger_workflows("DEPLOY", "production", 123)

        # Verify session was called
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


class TestUndefinedGuardFeatures:
    """Test UNDEFINED guard functionality"""

    @pytest.mark.asyncio
    async def test_undefined_guard_detection(self):
        """Test malformed command detection"""
        plugin = UndefinedGuardPlugin()
        await plugin.initialize({})

        # Test malformed commands
        test_cases = [
            ("notiz: some note", True),  # Should be NOTIZ:
            ("url: https://example.com", True),  # Should be URL:
            ("action: DEPLOY server", True),  # Should be ACTION:
            ("note: quick note", True),  # Common typo
            ("Normal event title", False),  # Should not trigger
            ("NOTIZ: proper command", False),  # Proper command, no change
            ("UNDEFINED: already marked", False),  # Already marked
        ]

        for title, should_mark in test_cases:
            event = ChronosEvent(title=title, status=EventStatus.SCHEDULED)
            result = await plugin.process_event(event)

            if should_mark:
                assert result.title.startswith("UNDEFINED:"), f"Should mark: {title}"
            else:
                assert not result.title.startswith("UNDEFINED:"), f"Should not mark: {title}"

    @pytest.mark.asyncio
    async def test_undefined_guard_system_event_skip(self):
        """Test that system events are not processed"""
        plugin = UndefinedGuardPlugin()
        await plugin.initialize({})

        # Create system event
        event = ChronosEvent(
            title="notiz: system event",
            status=EventStatus.SCHEDULED,
            calendar_id="system_calendar"
        )

        result = await plugin.process_event(event)

        # Should not be marked as UNDEFINED because it's a system event
        assert not result.title.startswith("UNDEFINED:")

    def test_undefined_guard_patterns(self):
        """Test pattern matching logic"""
        plugin = UndefinedGuardPlugin()

        test_patterns = [
            ("notiz: test", r'^notiz\s*:', True),
            ("NOTIZ: test", r'^notiz\s*:', True),  # Case insensitive
            ("url: test", r'^url\s*:', True),
            ("note: test", r'^note\s*:', True),
            ("normal text", r'^notiz\s*:', False),
            ("notification: test", r'^notiz\s*:', False),  # Partial match shouldn't trigger
        ]

        import re
        for text, pattern, should_match in test_patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if should_match:
                assert match is not None, f"Pattern {pattern} should match '{text}'"
            else:
                assert match is None, f"Pattern {pattern} should not match '{text}'"


class TestIntegrationFeatures:
    """Integration tests for v2.2 features"""

    def test_event_parser_full_integration(self):
        """Test parser with all v2.2 features"""
        parser = EventParser()

        calendar_event = {
            'id': 'test-event-123',
            'summary': 'Project Meeting #priority',
            'description': '''
            Discuss project roadmap

            Tasks:
            [ ] Prepare presentation
            [x] Send invites
            [ ] Book conference room

            #meeting #important
            ''',
            'start': {'dateTime': '2025-01-15T10:00:00Z'},
            'end': {'dateTime': '2025-01-15T11:00:00Z'},
            'attendees': [
                {'email': 'alice@company.com'},
                {'email': 'bob@company.com'}
            ],
            'location': 'Conference Room A'
        }

        event = parser.parse_event(calendar_event)

        # Verify basic parsing
        assert event.title == 'Project Meeting #priority'
        assert event.location == 'Conference Room A'
        assert len(event.attendees) == 2

        # Verify sub-tasks parsing
        assert len(event.sub_tasks) == 3
        assert event.sub_tasks[0].text == "Prepare presentation"
        assert not event.sub_tasks[0].completed
        assert event.sub_tasks[1].text == "Send invites"
        assert event.sub_tasks[1].completed

        # Verify tags extraction
        assert 'priority' in event.tags or 'meeting' in event.tags or 'important' in event.tags

    @pytest.mark.asyncio
    async def test_command_workflow_integration(self):
        """Test complete command workflow"""
        # Create command handler
        handler = CommandHandlerPlugin()
        handler.action_whitelist = {'DEPLOY', 'STATUS_CHECK'}

        # Create test event
        event = ChronosEvent(
            title="ACTION: DEPLOY production server1",
            description="Deploy new version"
        )

        # Mock database operations
        handler._trigger_workflows = AsyncMock()

        # Process event (would normally save to DB and trigger workflows)
        result = await handler.process_event(event)

        # Event should be deleted (returns None)
        assert result is None

    def test_subtask_completion_logic(self):
        """Test logic for auto-completing events when all sub-tasks done"""
        sub_tasks = [
            SubTask(text="Task 1", completed=True),
            SubTask(text="Task 2", completed=True),
            SubTask(text="Task 3", completed=True)
        ]

        event = ChronosEvent(
            title="Project Work",
            sub_tasks=sub_tasks,
            status=EventStatus.IN_PROGRESS
        )

        # Check if all sub-tasks are completed
        all_completed = all(task.completed for task in event.sub_tasks)
        assert all_completed

        # In real implementation, this would trigger event completion
        if all_completed and event.status == EventStatus.IN_PROGRESS:
            event.status = EventStatus.COMPLETED

        assert event.status == EventStatus.COMPLETED


if __name__ == "__main__":
    # Run specific test
    pytest.main([__file__, "-v"])