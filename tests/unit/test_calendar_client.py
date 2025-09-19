"""Unit tests for the GoogleCalendarClient abstraction."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.calendar_client import GoogleCalendarClient


@pytest.fixture
def credential_files(tmp_path):
    credentials = tmp_path / "credentials.json"
    token = tmp_path / "token.json"
    return credentials, token


def test_detect_auth_mode_defaults_to_mock(credential_files):
    credentials, token = credential_files

    client = GoogleCalendarClient(str(credentials), str(token))

    assert client.auth_mode == "mock"


def test_detect_auth_mode_service_account(credential_files):
    credentials, token = credential_files
    credentials.write_text(json.dumps({"type": "service_account"}))

    client = GoogleCalendarClient(str(credentials), str(token))

    assert client.auth_mode == "service_account"


@pytest.mark.asyncio
async def test_authenticate_uses_mock_when_google_unavailable(monkeypatch, credential_files):
    credentials, token = credential_files
    client = GoogleCalendarClient(str(credentials), str(token))

    monkeypatch.setattr("src.core.calendar_client.GOOGLE_AVAILABLE", False)
    mock_auth = AsyncMock(return_value=True)
    monkeypatch.setattr(client, "_authenticate_mock", mock_auth)

    assert await client.authenticate() is True
    mock_auth.assert_awaited_once()


def test_format_event_for_api_handles_datetimes(credential_files):
    credentials, token = credential_files
    client = GoogleCalendarClient(str(credentials), str(token))

    start = datetime.now(timezone.utc)
    end = start + timedelta(hours=2)
    payload = {
        "title": "Demo",
        "description": "Walkthrough",
        "location": "HQ",
        "start_time": start,
        "end_time": end,
        "attendees": ["user@example.com"],
    }

    formatted = client._format_event_for_api(payload)

    assert formatted["summary"] == "Demo"
    assert formatted["start"]["dateTime"].startswith(start.isoformat())
    assert formatted["attendees"] == [{"email": "user@example.com"}]


@pytest.mark.asyncio
async def test_health_check_reports_unhealthy_on_auth_failure(monkeypatch, credential_files):
    credentials, token = credential_files
    client = GoogleCalendarClient(str(credentials), str(token))

    async def fake_authenticate():
        return False

    monkeypatch.setattr(client, "authenticate", fake_authenticate)

    result = await client.health_check()

    assert result["status"] == "unhealthy"
    assert result["error"] == "Authentication failed"


@pytest.mark.asyncio
async def test_health_check_returns_details_for_success(monkeypatch, credential_files):
    credentials, token = credential_files
    client = GoogleCalendarClient(str(credentials), str(token))

    fake_service = MagicMock()
    fake_service.calendarList.return_value.list.return_value.execute.return_value = {"items": []}
    monkeypatch.setattr(client, "_test_connection", AsyncMock())
    monkeypatch.setattr(client, "authenticate", AsyncMock(return_value=True))
    client.service = fake_service

    result = await client.health_check()

    assert result["status"] == "healthy"
    assert result["auth_mode"] == client.auth_mode
