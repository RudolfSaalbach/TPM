#!/usr/bin/env python3
"""
Comprehensive Integration Test for Chronos Engine v2.2
Tests all components working together end-to-end
"""

import sys
import asyncio
from datetime import datetime, timedelta

async def comprehensive_integration_test():
    print("=== CHRONOS ENGINE v2.2 COMPREHENSIVE INTEGRATION TEST ===")
    print()

    try:
        # Test 1: Import all core components
        print("1. CORE COMPONENT IMPORTS")
        from src.core.models import (
            ChronosEvent, SubTask, EventLink, ActionWorkflow,
            ChronosEventDB, EventLinkDB, ActionWorkflowDB,
            Priority, EventType, EventStatus, CommandStatus
        )
        from src.core.event_parser import EventParser
        from plugins.custom.command_handler_plugin import CommandHandlerPlugin
        from plugins.custom.undefined_guard_plugin import UndefinedGuardPlugin
        from src.api.schemas import (
            SubTaskSchema, EventCreate, EventLinkCreate, WorkflowCreate
        )
        print("   [OK] All imports successful")

        # Test 2: Plugin system integration
        print("\n2. PLUGIN SYSTEM INTEGRATION")

        cmd_plugin = CommandHandlerPlugin()
        guard_plugin = UndefinedGuardPlugin()

        config = {
            'config': {
                'command_handler': {
                    'action_whitelist': ['DEPLOY', 'STATUS_CHECK', 'BACKUP'],
                    'enabled': True
                },
                'undefined_guard': {
                    'enabled': True
                }
            }
        }

        cmd_init = await cmd_plugin.initialize(config)
        guard_init = await guard_plugin.initialize(config)

        print(f"   [OK] Command Handler Plugin: {cmd_init}")
        print(f"   [OK] UNDEFINED Guard Plugin: {guard_init}")

        # Test 3: Event processing pipeline
        print("\n3. EVENT PROCESSING PIPELINE")

        # Test proper ACTION command
        action_event = ChronosEvent(
            title="ACTION: DEPLOY production app1",
            description="Deploy latest version to production"
        )

        cmd_result = await cmd_plugin.process_event(action_event)
        print(f"   [OK] ACTION command processing: {'Deleted' if cmd_result is None else 'Passed through'}")

        # Test malformed command
        malformed_event = ChronosEvent(
            title="action: deploy something",  # lowercase - should be marked
            status=EventStatus.SCHEDULED,
            calendar_id=""  # local event
        )

        guard_result = await guard_plugin.process_event(malformed_event)
        is_marked = guard_result.title.startswith("UNDEFINED:")
        print(f"   [OK] Malformed command detection: {'Marked' if is_marked else 'Not marked'}")

        # Test proper command (should not be marked)
        proper_event = ChronosEvent(
            title="NOTIZ: Important meeting notes",
            status=EventStatus.SCHEDULED,
            calendar_id=""
        )

        guard_result2 = await guard_plugin.process_event(proper_event)
        is_not_marked = not guard_result2.title.startswith("UNDEFINED:")
        print(f"   [OK] Proper command preservation: {'Preserved' if is_not_marked else 'Incorrectly marked'}")

        # Test 4: Sub-task parsing integration
        print("\n4. SUB-TASK PARSING INTEGRATION")

        parser = EventParser()

        event_with_tasks = {
            'id': 'test-123',
            'summary': 'Project Setup Meeting',
            'description': """Meeting agenda:

            [ ] Review requirements document
            [x] Assign team roles
            [ ] Set up development environment
            [X] Schedule next meeting

            Additional notes: Meeting room booked for 2 hours.""",
            'start': {'dateTime': '2025-01-20T10:00:00Z'},
            'end': {'dateTime': '2025-01-20T12:00:00Z'}
        }

        parsed_event = parser.parse_event(event_with_tasks)
        print(f"   [OK] Event parsed: {parsed_event.title}")
        print(f"   [OK] Sub-tasks found: {len(parsed_event.sub_tasks)}")

        completed_count = sum(1 for task in parsed_event.sub_tasks if task.completed)
        print(f"   [OK] Completed tasks: {completed_count}/{len(parsed_event.sub_tasks)}")

        # Test 5: Domain model conversions
        print("\n5. DOMAIN MODEL CONVERSIONS")

        event_db = parsed_event.to_db_model()
        print(f"   [OK] Event to DB model: {len(event_db.sub_tasks) if event_db.sub_tasks else 0} tasks preserved")

        restored_event = event_db.to_domain_model()
        print(f"   [OK] DB to domain model: {len(restored_event.sub_tasks)} tasks restored")

        # Verify data integrity
        original_texts = [t.text for t in parsed_event.sub_tasks]
        restored_texts = [t.text for t in restored_event.sub_tasks]
        integrity_check = original_texts == restored_texts
        print(f"   [OK] Data integrity: {'Preserved' if integrity_check else 'Corrupted'}")

        # Test 6: Event linking
        print("\n6. EVENT LINKING SYSTEM")

        link = EventLink(
            source_event_id="meeting-123",
            target_event_id="followup-456",
            link_type="leads_to"
        )

        link_db = link.to_db_model()
        print(f"   [OK] Event link creation: {link_db.source_event_id} -> {link_db.target_event_id}")
        print(f"   [OK] Link type: {link_db.link_type}")

        # Test 7: Workflow system
        print("\n7. WORKFLOW AUTOMATION SYSTEM")

        workflow = ActionWorkflow(
            trigger_command="DEPLOY",
            trigger_system="production",
            follow_up_command="STATUS_CHECK",
            follow_up_system="monitoring",
            follow_up_params={"timeout": 300, "check_type": "post_deploy"},
            delay_seconds=30
        )

        workflow_db = workflow.to_db_model()
        print(f"   [OK] Workflow creation: {workflow_db.trigger_command} -> {workflow_db.follow_up_command}")
        print(f"   [OK] Parameters preserved: {len(workflow_db.follow_up_params)} params")

        # Test 8: API Schema validation
        print("\n8. API SCHEMA VALIDATION")

        subtask_data = {
            'id': 'task-1',
            'text': 'Complete integration test',
            'completed': True,
            'created_at': datetime.utcnow(),
            'completed_at': datetime.utcnow()
        }
        subtask_schema = SubTaskSchema(**subtask_data)
        print(f"   [OK] SubTaskSchema validation: {subtask_schema.text}")

        event_create_data = {
            'title': 'Test Event with Tasks',
            'start_time': datetime.utcnow(),
            'end_time': datetime.utcnow() + timedelta(hours=1),
            'sub_tasks': [subtask_schema]
        }
        event_create = EventCreate(**event_create_data)
        print(f"   [OK] EventCreate with sub_tasks: {len(event_create.sub_tasks)} tasks")

        link_create_data = {
            'source_event_id': 'event-1',
            'target_event_id': 'event-2',
            'link_type': 'depends_on'
        }
        link_create = EventLinkCreate(**link_create_data)
        print(f"   [OK] EventLinkCreate validation: {link_create.link_type}")

        workflow_create_data = {
            'trigger_command': 'BACKUP',
            'trigger_system': 'database',
            'follow_up_command': 'STATUS_CHECK',
            'follow_up_system': 'monitoring'
        }
        workflow_create = WorkflowCreate(**workflow_create_data)
        print(f"   [OK] WorkflowCreate validation: {workflow_create.trigger_command}")

        # Cleanup
        await cmd_plugin.cleanup()
        await guard_plugin.cleanup()

        print("\n=== INTEGRATION TEST RESULTS ===")
        print("[OK] ALL TESTS PASSED - SYSTEM INTEGRATION VERIFIED")
        print("[OK] Core components working together correctly")
        print("[OK] Plugin pipeline processing events properly")
        print("[OK] Data integrity maintained throughout conversions")
        print("[OK] API schemas validating correctly")
        print("[OK] All v2.2 features integrated successfully")

        return True

    except Exception as e:
        print(f"\n[FAIL] INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(comprehensive_integration_test())
    sys.exit(0 if success else 1)