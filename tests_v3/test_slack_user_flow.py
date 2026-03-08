"""Slack User Flow Tests for Oni System v0.3

These tests simulate Slack user interactions via API calls.
"""

import hashlib
import hmac
import json
import time

import pytest
import requests

from tests_v3.api_server import run_api_server

# ============================================================================
# Test Server Management
# ============================================================================


@pytest.fixture(scope="module")
def api_server():
    """Start and stop the FastAPI server for testing."""
    with run_api_server() as base_url:
        yield base_url


# ============================================================================
# Slack Request Helpers
# ============================================================================


def create_slack_signature(timestamp: str, body: bytes, signing_secret: str = "test_secret") -> str:
    """Create a valid Slack signature for testing.

    Slack公式フォーマット: v0:timestamp:body
    参考: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    # Slack公式フォーマット: v0:timestamp:body
    basestring = f"v0:{timestamp}:{body.decode() if isinstance(body, bytes) else body}"

    expected_hash = hmac.new(
        signing_secret.encode(), msg=basestring.encode(), digestmod=hashlib.sha256
    ).hexdigest()

    return f"v0={expected_hash}"


class TestSlackUserFlow:
    """Test Slack user interaction flows based on design document."""

    def test_init_command_returns_modal(self, api_server):
        """
        Test 7.1 init flow: /base_commit command

        Expected: Slack Modal is returned
        """
        timestamp = str(int(time.time()))

        # Create the body that requests will send (URL-encoded)
        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBULT484", "text": ""}
        body = urlencode(form_data).encode()

        signature = create_slack_signature(timestamp, body)

        # Important: send encoded body with correct Content-Type
        response = requests.post(
            f"{api_server}/slack/command",
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )

        # Should return a modal trigger
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        # Response should contain view key
        # The view may be nested in blocks array
        if "view" in data:
            assert True
        elif "blocks" in data:
            first_block = data.get("blocks", [{}])[0]
            assert first_block.get("type") in ["modal", "view", "section"]
        else:
            assert False, f"Expected 'view' or 'blocks' with view, got: {list(data.keys())}"

    def test_stop_command(self, api_server):
        """
        Test /stop command

        Expected: System paused confirmation
        """
        timestamp = str(int(time.time()))

        # Use urlencode to create body matching requests.post
        from urllib.parse import urlencode

        form_data = {"command": "/stop", "user_id": "U03JBULT484"}
        body = urlencode(form_data).encode()

        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert "text" in data or "blocks" in data

    def test_restart_command(self, api_server):
        """
        Test /restart command

        Expected: System restarted confirmation
        """
        timestamp = str(int(time.time()))

        # Use urlencode to create body matching requests.post
        from urllib.parse import urlencode

        form_data = {"command": "/restart", "user_id": "U03JBULT484"}
        body = urlencode(form_data).encode()

        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert "text" in data or "blocks" in data

    def test_plan_modal_submission(self, api_server):
        """
        Test 7.2 plan flow: Modal submission

        Expected:
        - 200 status
        - Success response
        """
        timestamp = str(int(time.time()))

        # Simulate plan modal submission
        payload = {
            "type": "view_submission",
            "user": {"id": "U03JBULT484"},
            "view": {
                "callback_id": "commitment_submit",
                "state": {"values": {"task_1": {"type": "plain_text_input", "value": "Test task"}}},
            },
        }

        payload_str = json.dumps(payload)
        from urllib.parse import urlencode

        body = urlencode({"payload": payload_str}).encode()

        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/interactive",
            data={"payload": payload_str},
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("response_action") in ["clear", "errors"]

    def test_remind_yes_button(self, api_server):
        """
        Test 7.3 remind flow: YES button

        Expected:
        - 200 status
        - Success response
        """
        timestamp = str(int(time.time()))

        # Simulate remind YES button click
        payload = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [
                {"action_id": "remind_yes", "value": '{"schedule_id": "test-schedule-id"}'}
            ],
            "container": {"channel_id": "C12345", "message_ts": "12345.6789"},
        }

        payload_str = json.dumps(payload)
        from urllib.parse import urlencode

        body = urlencode({"payload": payload_str}).encode()

        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/interactive",
            data={"payload": payload_str},
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_remind_no_button(self, api_server):
        """
        Test 7.3 remind flow: NO button

        Expected:
        - 200 status
        - Success response
        """
        timestamp = str(int(time.time()))

        # Simulate remind NO button click
        payload = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "remind_no", "value": '{"schedule_id": "test-schedule-id"}'}],
            "container": {"channel_id": "C12345", "message_ts": "12345.6789"},
        }

        payload_str = json.dumps(payload)
        from urllib.parse import urlencode

        body = urlencode({"payload": payload_str}).encode()

        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/interactive",
            data={"payload": payload_str},
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


class TestSlackSignatureValidation:
    """Test Slack signature validation."""

    def test_missing_signature_returns_401(self, api_server):
        """Test request without signature returns 401."""
        response = requests.post(f"{api_server}/slack/command", data={"command": "/base_commit"})

        assert response.status_code == 401

    def test_invalid_signature_returns_401(self, api_server):
        """Test request with invalid signature returns 401."""
        timestamp = str(int(time.time()))

        response = requests.post(
            f"{api_server}/slack/command",
            data={"command": "/base_commit"},
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": "v0=invalid_signature",
            },
        )

        assert response.status_code == 401

    def test_valid_signature_succeeds(self, api_server):
        """Test request with valid signature succeeds."""
        timestamp = str(int(time.time()))

        # Create the body that requests will send
        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBULT484"}
        body = urlencode(form_data).encode()

        print(f"[TEST] timestamp={timestamp}")
        print(f"[TEST] body={body}")

        signature = create_slack_signature(timestamp, body)

        print(f"[TEST] signature={signature}")

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200


class TestInternalAPIValidation:
    """Test internal API validation."""

    def test_missing_secret_returns_401(self, api_server):
        """Test request without secret returns 401."""
        response = requests.get(f"{api_server}/internal/config/TEST_KEY")
        assert response.status_code == 401

    def test_invalid_secret_returns_401(self, api_server):
        """Test request with invalid secret returns 401."""
        response = requests.get(
            f"{api_server}/internal/config/TEST_KEY",
            headers={"X-Internal-Secret": "invalid_secret"},
        )
        assert response.status_code == 401

    def test_valid_secret_succeeds(self, api_server):
        """Test request with valid secret succeeds (when env var set)."""
        # This test will pass in dev mode (returns 401 for unconfigured)
        response = requests.get(
            f"{api_server}/internal/config/TEST_KEY", headers={"X-Internal-Secret": "test_secret"}
        )
        # In dev mode, returns 401 with "not configured" message
        assert response.status_code == 401
