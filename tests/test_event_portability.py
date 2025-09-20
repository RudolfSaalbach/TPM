"""
Tests for Event Data Portability features (Export/Import)
Validates all functional requirements FR-1.1 through FR-3.1
"""

import json
import pytest
import uuid
from datetime import datetime, timedelta
from httpx import AsyncClient
from fastapi import status

from src.core.models import ChronosEventDB, EventLinkDB, SubTask
from src.core.database import db_service


class TestEventPortability:
    """Test suite for event export/import functionality"""

    @pytest.fixture
    async def test_event_data(self):
        """Create test event data for portability tests"""
        now = datetime.utcnow()

        # Create test event with comprehensive data
        event_data = {
            "id": str(uuid.uuid4()),
            "title": "Test Event for Export",
            "description": "A comprehensive test event with all possible fields",
            "start_time": now,
            "end_time": now + timedelta(hours=2),
            "start_utc": now,
            "end_utc": now + timedelta(hours=2),
            "all_day_date": None,
            "priority": "HIGH",
            "event_type": "MEETING",
            "status": "SCHEDULED",
            "calendar_id": "test-calendar",
            "attendees": ["test@example.com", "user2@example.com"],
            "location": "Conference Room A",
            "tags": ["important", "project-alpha"],
            "sub_tasks": [
                {
                    "id": str(uuid.uuid4()),
                    "text": "Prepare presentation",
                    "completed": False,
                    "created_at": now.isoformat(),
                    "completed_at": None
                },
                {
                    "id": str(uuid.uuid4()),
                    "text": "Send meeting agenda",
                    "completed": True,
                    "created_at": (now - timedelta(days=1)).isoformat(),
                    "completed_at": now.isoformat()
                }
            ],
            "estimated_duration": timedelta(hours=2),
            "actual_duration": None,
            "preparation_time": timedelta(minutes=15),
            "buffer_time": timedelta(minutes=10),
            "productivity_score": 8.5,
            "completion_rate": 0.75,
            "stress_level": 3.2,
            "min_duration": timedelta(minutes=30),
            "max_duration": timedelta(hours=3),
            "flexible_timing": True,
            "requires_focus": True,
            "created_at": now - timedelta(days=7),
            "updated_at": now - timedelta(hours=1)
        }

        return event_data

    @pytest.fixture
    async def create_test_event_in_db(self, test_event_data):
        """Create a test event in the database"""
        async with db_service.get_session() as session:
            event = ChronosEventDB(
                id=test_event_data["id"],
                title=test_event_data["title"],
                description=test_event_data["description"],
                start_time=test_event_data["start_time"],
                end_time=test_event_data["end_time"],
                start_utc=test_event_data["start_utc"],
                end_utc=test_event_data["end_utc"],
                all_day_date=test_event_data["all_day_date"],
                priority=test_event_data["priority"],
                event_type=test_event_data["event_type"],
                status=test_event_data["status"],
                calendar_id=test_event_data["calendar_id"],
                attendees=test_event_data["attendees"],
                location=test_event_data["location"],
                tags=test_event_data["tags"],
                sub_tasks=test_event_data["sub_tasks"],
                estimated_duration=test_event_data["estimated_duration"],
                actual_duration=test_event_data["actual_duration"],
                preparation_time=test_event_data["preparation_time"],
                buffer_time=test_event_data["buffer_time"],
                productivity_score=test_event_data["productivity_score"],
                completion_rate=test_event_data["completion_rate"],
                stress_level=test_event_data["stress_level"],
                min_duration=test_event_data["min_duration"],
                max_duration=test_event_data["max_duration"],
                flexible_timing=test_event_data["flexible_timing"],
                requires_focus=test_event_data["requires_focus"],
                created_at=test_event_data["created_at"],
                updated_at=test_event_data["updated_at"]
            )

            session.add(event)
            await session.commit()
            return event

    @pytest.fixture
    async def create_event_links(self, create_test_event_in_db):
        """Create test event links"""
        source_event = create_test_event_in_db

        # Create a second event for linking
        target_event_id = str(uuid.uuid4())
        async with db_service.get_session() as session:
            target_event = ChronosEventDB(
                id=target_event_id,
                title="Target Event",
                description="Event that depends on the source event",
                priority="MEDIUM",
                event_type="TASK",
                status="SCHEDULED"
            )
            session.add(target_event)

            # Create event link
            link = EventLinkDB(
                source_event_id=source_event.id,
                target_event_id=target_event_id,
                link_type="depends_on",
                created_at=datetime.utcnow(),
                created_by="test"
            )
            session.add(link)
            await session.commit()

            return [link]

    @pytest.mark.asyncio
    async def test_export_single_event_success(self, client: AsyncClient, create_test_event_in_db, create_event_links):
        """Test FR-1.1: Export einzelner Events"""
        event = create_test_event_in_db
        links = create_event_links

        headers = {"Authorization": "Bearer test-api-key"}
        response = await client.get(f"/events/{event.id}/export", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        export_data = response.json()

        # Validate export structure (FR-1.2: JSON format)
        assert "format_version" in export_data
        assert "export_timestamp" in export_data
        assert "events" in export_data
        assert "event_links" in export_data
        assert len(export_data["events"]) == 1

        # Validate completeness of data (FR-1.3)
        exported_event = export_data["events"][0]
        assert exported_event["id"] == event.id
        assert exported_event["title"] == event.title
        assert exported_event["description"] == event.description
        assert exported_event["priority"] == event.priority
        assert exported_event["event_type"] == event.event_type
        assert exported_event["status"] == event.status
        assert exported_event["attendees"] == event.attendees
        assert exported_event["location"] == event.location
        assert exported_event["tags"] == event.tags
        assert exported_event["sub_tasks"] == event.sub_tasks

        # Validate event links are included
        assert len(export_data["event_links"]) == 1
        assert export_data["event_links"][0]["source_event_id"] == event.id

    @pytest.mark.asyncio
    async def test_export_event_not_found(self, client: AsyncClient):
        """Test export with non-existent event ID"""
        non_existent_id = str(uuid.uuid4())
        headers = {"Authorization": "Bearer test-api-key"}

        response = await client.get(f"/events/{non_existent_id}/export", headers=headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_export_without_authentication(self, client: AsyncClient, create_test_event_in_db):
        """Test FR-3.1: API key authentication requirement"""
        event = create_test_event_in_db

        # Test without any headers
        response = await client.get(f"/events/{event.id}/export")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # Test with invalid API key
        headers = {"Authorization": "Bearer invalid-key"}
        response = await client.get(f"/events/{event.id}/export", headers=headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_import_single_event_success(self, client: AsyncClient, test_event_data):
        """Test FR-2.1: Import via JSON - single event"""
        # Prepare import data
        import_data = {
            "format_version": "1.0",
            "events": [{
                "id": test_event_data["id"],
                "title": test_event_data["title"],
                "description": test_event_data["description"],
                "start_time": test_event_data["start_time"].isoformat(),
                "end_time": test_event_data["end_time"].isoformat(),
                "priority": test_event_data["priority"],
                "event_type": test_event_data["event_type"],
                "status": test_event_data["status"],
                "calendar_id": test_event_data["calendar_id"],
                "attendees": test_event_data["attendees"],
                "location": test_event_data["location"],
                "tags": test_event_data["tags"],
                "sub_tasks": test_event_data["sub_tasks"],
                "estimated_duration": test_event_data["estimated_duration"].total_seconds(),
                "preparation_time": test_event_data["preparation_time"].total_seconds(),
                "buffer_time": test_event_data["buffer_time"].total_seconds(),
                "min_duration": test_event_data["min_duration"].total_seconds(),
                "max_duration": test_event_data["max_duration"].total_seconds(),
                "flexible_timing": test_event_data["flexible_timing"],
                "requires_focus": test_event_data["requires_focus"]
            }],
            "event_links": []
        }

        headers = {"Authorization": "Bearer test-api-key"}
        response = await client.post("/events/import", json=import_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Validate import response (FR-2.5: Creation of new events)
        assert result["success"] is True
        assert result["imported_events"] == 1
        assert result["imported_links"] == 0
        assert len(result["created_event_ids"]) == 1
        assert len(result["id_mappings"]) == 1

        # Verify new event was created with different ID
        new_event_id = result["created_event_ids"][0]
        assert new_event_id != test_event_data["id"]  # FR-2.5: New events, not overwrite

    @pytest.mark.asyncio
    async def test_import_multiple_events_success(self, client: AsyncClient):
        """Test FR-2.2: Massenimport"""
        import_data = {
            "format_version": "1.0",
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Event 1",
                    "priority": "HIGH",
                    "event_type": "MEETING"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Event 2",
                    "priority": "MEDIUM",
                    "event_type": "TASK"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Event 3",
                    "priority": "LOW",
                    "event_type": "REMINDER"
                }
            ],
            "event_links": []
        }

        headers = {"Authorization": "Bearer test-api-key"}
        response = await client.post("/events/import", json=import_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        assert result["success"] is True
        assert result["imported_events"] == 3
        assert len(result["created_event_ids"]) == 3

    @pytest.mark.asyncio
    async def test_import_with_event_links(self, client: AsyncClient):
        """Test FR-2.6: Wiederherstellung von Relationen"""
        event1_id = str(uuid.uuid4())
        event2_id = str(uuid.uuid4())

        import_data = {
            "format_version": "1.0",
            "events": [
                {
                    "id": event1_id,
                    "title": "Source Event",
                    "priority": "HIGH"
                },
                {
                    "id": event2_id,
                    "title": "Target Event",
                    "priority": "MEDIUM"
                }
            ],
            "event_links": [
                {
                    "id": 1,
                    "source_event_id": event1_id,
                    "target_event_id": event2_id,
                    "link_type": "depends_on",
                    "created_by": "test"
                }
            ]
        }

        headers = {"Authorization": "Bearer test-api-key"}
        response = await client.post("/events/import", json=import_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        assert result["success"] is True
        assert result["imported_events"] == 2
        assert result["imported_links"] == 1

        # Verify ID mappings are maintained for links
        assert len(result["id_mappings"]) == 2

    @pytest.mark.asyncio
    async def test_import_validation_errors(self, client: AsyncClient):
        """Test FR-2.7: Datenvalidierung"""
        headers = {"Authorization": "Bearer test-api-key"}

        # Test invalid JSON structure
        response = await client.post("/events/import", json="invalid", headers=headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Test missing events array
        response = await client.post("/events/import", json={"format_version": "1.0"}, headers=headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Test empty events array
        response = await client.post("/events/import", json={"events": []}, headers=headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Test invalid event structure
        invalid_data = {
            "events": [
                {"invalid": "event"}  # Missing required title field
            ]
        }
        response = await client.post("/events/import", json=invalid_data, headers=headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_import_transactional_rollback(self, client: AsyncClient):
        """Test FR-2.4: Transaktionale Verarbeitung - Alles-oder-nichts"""
        import_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Valid Event",
                    "priority": "HIGH"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Invalid Event",
                    "start_time": "invalid-date-format",  # This should cause failure
                    "priority": "HIGH"
                }
            ]
        }

        headers = {"Authorization": "Bearer test-api-key"}
        response = await client.post("/events/import", json=import_data, headers=headers)

        # Should fail due to invalid date
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Verify no events were created (rollback occurred)
        async with db_service.get_session() as session:
            # Check that neither event exists in database
            for event_data in import_data["events"]:
                existing = await session.get(ChronosEventDB, event_data["id"])
                assert existing is None

    @pytest.mark.asyncio
    async def test_roundtrip_export_import(self, client: AsyncClient, create_test_event_in_db, create_event_links):
        """Test roundtrip: Export → Import functionality (FR-2.3: Formatkonsistenz)"""
        original_event = create_test_event_in_db
        links = create_event_links

        headers = {"Authorization": "Bearer test-api-key"}

        # Step 1: Export the event
        export_response = await client.get(f"/events/{original_event.id}/export", headers=headers)
        assert export_response.status_code == status.HTTP_200_OK
        export_data = export_response.json()

        # Step 2: Import the exported data
        import_response = await client.post("/events/import", json=export_data, headers=headers)
        assert import_response.status_code == status.HTTP_200_OK
        import_result = import_response.json()

        # Step 3: Verify successful import
        assert import_result["success"] is True
        assert import_result["imported_events"] == 1
        assert import_result["imported_links"] == 1

        # Step 4: Export the imported event and compare
        new_event_id = import_result["created_event_ids"][0]
        roundtrip_response = await client.get(f"/events/{new_event_id}/export", headers=headers)
        assert roundtrip_response.status_code == status.HTTP_200_OK
        roundtrip_data = roundtrip_response.json()

        # Compare key fields (excluding IDs and timestamps)
        original_exported = export_data["events"][0]
        roundtrip_exported = roundtrip_data["events"][0]

        comparable_fields = [
            "title", "description", "priority", "event_type", "status",
            "attendees", "location", "tags", "sub_tasks", "flexible_timing", "requires_focus"
        ]

        for field in comparable_fields:
            assert original_exported[field] == roundtrip_exported[field], f"Field {field} differs after roundtrip"

    @pytest.mark.asyncio
    async def test_import_without_authentication(self, client: AsyncClient):
        """Test FR-3.1: API key authentication requirement for import"""
        import_data = {
            "events": [{"title": "Test Event"}]
        }

        # Test without any headers
        response = await client.post("/events/import", json=import_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # Test with invalid API key
        headers = {"Authorization": "Bearer invalid-key"}
        response = await client.post("/events/import", json=import_data, headers=headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_export_format_completeness(self, client: AsyncClient, create_test_event_in_db):
        """Comprehensive test for export format completeness (FR-1.3)"""
        event = create_test_event_in_db
        headers = {"Authorization": "Bearer test-api-key"}

        response = await client.get(f"/events/{event.id}/export", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        export_data = response.json()
        exported_event = export_data["events"][0]

        # Test all possible fields are present in export
        expected_fields = [
            "id", "title", "description", "start_time", "end_time", "start_utc", "end_utc",
            "all_day_date", "priority", "event_type", "status", "calendar_id", "attendees",
            "location", "tags", "sub_tasks", "estimated_duration", "actual_duration",
            "preparation_time", "buffer_time", "productivity_score", "completion_rate",
            "stress_level", "min_duration", "max_duration", "flexible_timing",
            "requires_focus", "created_at", "updated_at"
        ]

        for field in expected_fields:
            assert field in exported_event, f"Required field {field} missing from export"

    @pytest.mark.asyncio
    async def test_import_preserves_sub_tasks(self, client: AsyncClient):
        """Test that sub-tasks are properly preserved during import (FR-2.6)"""
        sub_tasks = [
            {
                "id": str(uuid.uuid4()),
                "text": "Task 1",
                "completed": False,
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": None
            },
            {
                "id": str(uuid.uuid4()),
                "text": "Task 2",
                "completed": True,
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat()
            }
        ]

        import_data = {
            "events": [{
                "id": str(uuid.uuid4()),
                "title": "Event with Sub-tasks",
                "sub_tasks": sub_tasks
            }],
            "event_links": []
        }

        headers = {"Authorization": "Bearer test-api-key"}
        response = await client.post("/events/import", json=import_data, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()

        # Verify import was successful
        assert result["imported_events"] == 1
        new_event_id = result["created_event_ids"][0]

        # Verify sub-tasks were preserved by exporting the event
        export_response = await client.get(f"/events/{new_event_id}/export", headers=headers)
        export_data = export_response.json()
        imported_sub_tasks = export_data["events"][0]["sub_tasks"]

        assert len(imported_sub_tasks) == 2
        assert imported_sub_tasks[0]["text"] == "Task 1"
        assert imported_sub_tasks[0]["completed"] is False
        assert imported_sub_tasks[1]["text"] == "Task 2"
        assert imported_sub_tasks[1]["completed"] is True