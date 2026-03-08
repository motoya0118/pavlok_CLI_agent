import pytest
from fastapi.testclient import TestClient

from backend.main import app, route_interactive_payload, route_slash_command


@pytest.mark.asyncio
async def test_route_slash_command_plan(monkeypatch):
    form_data = {
        "command": "/plan",
        "user_id": "U03JBULT484",
    }
    called = {}

    async def _fake_process_plan(received_form_data):
        called["form_data"] = received_form_data
        return {"status": "success"}

    monkeypatch.setattr(
        "backend.main.process_plan",
        _fake_process_plan,
    )

    result = await route_slash_command(form_data)

    assert result == {"status": "success"}
    assert called["form_data"] == form_data


@pytest.mark.asyncio
async def test_route_slash_command_help(monkeypatch):
    form_data = {
        "command": "/help",
        "user_id": "U03JBULT484",
    }
    called = {}

    async def _fake_process_help(received_form_data):
        called["form_data"] = received_form_data
        return {"status": "success"}

    monkeypatch.setattr(
        "backend.main.process_help",
        _fake_process_help,
    )

    result = await route_slash_command(form_data)

    assert result == {"status": "success"}
    assert called["form_data"] == form_data


@pytest.mark.asyncio
async def test_route_slash_command_cal(monkeypatch):
    form_data = {
        "command": "/cal",
        "user_id": "U03JBULT484",
    }
    called = {}

    async def _fake_process_cal(received_form_data):
        called["form_data"] = received_form_data
        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": "cal modal",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "cal ui"}}],
        }

    monkeypatch.setattr(
        "backend.main.process_cal",
        _fake_process_cal,
        raising=False,
    )

    result = await route_slash_command(form_data)

    assert result["status"] == "success"
    assert isinstance(result.get("blocks"), list)
    assert called["form_data"] == form_data


def test_slack_gateway_cal_returns_ui_blocks(monkeypatch):
    async def _fake_verify_slack_signature(request):
        return True

    async def _fake_process_cal(received_form_data):
        return {
            "status": "success",
            "response_type": "ephemeral",
            "text": "cal modal",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": "カロリー入力UI"}},
            ],
        }

    monkeypatch.setattr(
        "backend.main.verify_slack_signature",
        _fake_verify_slack_signature,
    )
    monkeypatch.setattr(
        "backend.main.process_cal",
        _fake_process_cal,
        raising=False,
    )

    with TestClient(app) as client:
        response = client.post(
            "/slack/gateway",
            data={
                "command": "/cal",
                "user_id": "U03JBULT484",
                "channel_id": "C_TEST",
                "trigger_id": "TRIGGER_TEST",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert isinstance(payload.get("blocks"), list)
    assert payload["blocks"][0]["type"] == "section"


@pytest.mark.asyncio
async def test_route_interactive_payload_plan_open_modal(monkeypatch):
    payload_data = {
        "type": "block_actions",
        "user": {"id": "U03JBULT484"},
        "actions": [{"action_id": "plan_open_modal"}],
    }
    called = {}

    async def _fake_process_plan_open_modal(received_payload):
        called["payload"] = received_payload
        return {"status": "success"}

    monkeypatch.setattr(
        "backend.main.process_plan_open_modal",
        _fake_process_plan_open_modal,
    )

    result = await route_interactive_payload(payload_data)

    assert result == {"status": "success"}
    assert called["payload"] == payload_data


@pytest.mark.asyncio
async def test_route_interactive_payload_plan_submit(monkeypatch):
    payload_data = {
        "type": "view_submission",
        "user": {"id": "U03JBULT484"},
        "view": {"callback_id": "plan_submit", "state": {"values": {}}},
    }
    called = {}

    async def _fake_process_plan_modal_submit(received_payload):
        called["payload"] = received_payload
        return {"response_action": "clear"}

    monkeypatch.setattr(
        "backend.main.process_plan_modal_submit",
        _fake_process_plan_modal_submit,
    )

    result = await route_interactive_payload(payload_data)

    assert result == {"response_action": "clear"}
    assert called["payload"] == payload_data


@pytest.mark.asyncio
async def test_route_interactive_payload_calorie_submit(monkeypatch):
    payload_data = {
        "type": "view_submission",
        "user": {"id": "U03JBULT484"},
        "view": {"callback_id": "calorie_submit", "state": {"values": {}}},
    }
    called = {}

    async def _fake_process_calorie_submit(received_payload):
        called["payload"] = received_payload
        return {"response_action": "clear"}

    monkeypatch.setattr(
        "backend.main.process_calorie_submit",
        _fake_process_calorie_submit,
    )

    result = await route_interactive_payload(payload_data)
    assert result == {"response_action": "clear"}
    assert called["payload"] == payload_data


@pytest.mark.asyncio
async def test_route_interactive_payload_report_read(monkeypatch):
    payload_data = {
        "type": "block_actions",
        "user": {"id": "U03JBULT484"},
        "actions": [{"action_id": "report_read"}],
    }
    called = {}

    async def _fake_process_report_read_response(received_payload):
        called["payload"] = received_payload
        return {"status": "success"}

    monkeypatch.setattr(
        "backend.main.process_report_read_response",
        _fake_process_report_read_response,
    )

    result = await route_interactive_payload(payload_data)

    assert result == {"status": "success"}
    assert called["payload"] == payload_data
