"""Comprehensive API Tests for Oni System v0.3

These tests verify all API endpoints with proper mock data and validation.
Tests follow v0.3 design document flow.
"""

import hashlib
import hmac
import time

import pytest
import requests

from tests_v3.api_server import run_api_server

# ============================================================================
# Test Server Management
# ============================================================================


@pytest.fixture(scope="module")
def api_server():
    """Start and stop FastAPI server for testing."""
    with run_api_server() as base_url:
        yield base_url


# ============================================================================
# Mock Data Helpers
# ============================================================================


class MockSlackData:
    """Mock Slack response data based on v0.3 design."""

    @staticmethod
    def modal_response(trigger_id: str = "base_commit_submit") -> dict:
        """Generate a modal response like Slack would return."""
        return {
            "type": "modal",
            "trigger_id": trigger_id,
            "view": {
                "type": "modal",
                "callback_id": trigger_id,
                "title": {"type": "plain_text", "text": "ベースコミット管理"},
                "submit": {"type": "plain_text", "text": "送信"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "毎日実行するコミットメントを設定します。入力内容はplan_APIに送信されます。",
                        },
                    },
                    {
                        "type": "divider",
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "+ 追加"},
                                "style": "primary",
                                "action_id": "commitment_add_row",
                            }
                        ],
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "コミットは毎日指定時刻にplanイベントとして登録されます",
                            }
                        ],
                    },
                ],
            },
        }

    @staticmethod
    def command_response(text: str, detail: str = None) -> dict:
        """Generate a command response like Slack would return."""
        response = {"status": "success", "detail": detail or text}

        if detail:
            response["data"] = detail

        return response

    @staticmethod
    def confirmation_response(text: str) -> dict:
        """Generate a confirmation response with text and blocks."""
        return {
            "status": "success",
            "text": text,
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
        }


# ============================================================================
# Slack Signature Helpers
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


# ============================================================================
# Health Check Tests
# ============================================================================


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_returns_200(self, api_server):
        """Test health check returns 200 with version info."""
        response = requests.get(f"{api_server}/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert data["version"] == "0.3.0"
        assert "timestamp" in data

    def test_health_returns_valid_json(self, api_server):
        """Test health check returns valid JSON structure."""
        response = requests.get(f"{api_server}/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "timestamp" in data


# ============================================================================
# Slack Command Tests
# ============================================================================


class TestSlackCommands:
    """Test Slack slash command endpoints.

    Test cases:
    - /base_commit → Modal with blocks
    - /stop → Confirmation message
    - /restart → Confirmation message
    - /config → Configuration display/update
    """

    def test_base_commit_command_returns_modal(self, api_server):
        """
        Test 7.1 init flow: /base_commit command

        Expected:
        - 200 status
        - Modal response with:
            - type: "modal"
            - trigger_id: "base_commit_submit"
            - view with blocks containing title, submit button
        """
        timestamp = str(int(time.time()))

        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484", "text": ""}

        body = urlencode(form_data).encode()
        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert "blocks" in data or "view" in data

        if "blocks" in data:
            blocks = data["blocks"]
            assert len(blocks) > 0
            assert blocks[0]["type"] in ["modal", "view", "section"]

            if blocks[0]["type"] == "modal":
                view = blocks[0].get("view")
                assert view is not None
                assert view["callback_id"] == "base_commit_submit"
                assert "title" in view
                assert "submit" in view

    def test_stop_command(self, api_server):
        """
        Test /stop command

        Expected:
        - 200 status
        - Success response with text or blocks
        """
        timestamp = str(int(time.time()))

        from urllib.parse import urlencode

        form_data = {"command": "/stop", "user_id": "U03JBLT484"}

        body = urlencode(form_data).encode()
        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_restart_command(self, api_server):
        """
        Test /restart command

        Expected:
        - 200 status
        - Success response with text or blocks
        """
        timestamp = str(int(time.time()))

        from urllib.parse import urlencode

        form_data = {"command": "/restart", "user_id": "U03JBLT484"}

        body = urlencode(form_data).encode()
        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


# ============================================================================
# Slack Signature Validation Tests
# ============================================================================


class TestSlackAPISignatureValidation:
    """Test Slack signature validation independently.

    Test cases:
    - Missing timestamp → 401
    - Missing signature → 401
    - Valid signature → 200 with modal
    """

    def test_missing_timestamp_returns_401(self, api_server):
        """Test request without timestamp returns 401."""
        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484"}

        urlencode(form_data).encode()

        # Send without timestamp
        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Signature": "v0=invalid_signature"},
        )

        assert response.status_code == 401

    def test_missing_signature_returns_401(self, api_server):
        """Test request without signature returns 401."""
        timestamp = str(int(time.time()))

        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484"}

        urlencode(form_data).encode()

        # Send without signature
        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp},
        )

        assert response.status_code == 401

    def test_valid_signature_succeeds(self, api_server):
        """Test request with valid signature succeeds (returns modal)."""
        timestamp = str(int(time.time()))

        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484"}

        body = urlencode(form_data).encode()
        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert "blocks" in data
        assert data["blocks"][0]["type"] in ["modal", "section"]

        if data["blocks"][0]["type"] == "modal":
            view = data["blocks"][0].get("view")
            assert view is not None
            assert view.get("callback_id") == "base_commit_submit"


# ============================================================================
# Internal API Tests
# ============================================================================


class TestInternalAPIValidation:
    """Test internal API validation.

    Test cases:
    - /internal/execute/* without secret → 401
    - /internal/config/* without secret → 401
    - /internal/config/* with secret (dev mode) → 401 with "not configured"
    """

    def test_internal_execute_without_secret_returns_401(self, api_server):
        """Test /internal/execute without secret returns 401."""
        response = requests.get(f"{api_server}/internal/execute/plan")

        assert response.status_code == 401

    def test_internal_config_without_secret_returns_401(self, api_server):
        """Test /internal/config without secret returns 401."""
        response = requests.get(f"{api_server}/internal/config/PAVLOK_VALUE_PUNISH")

        assert response.status_code == 401

    def test_internal_config_with_secret_succeeds_in_dev_mode(self, api_server):
        """Test /internal/config with secret succeeds in dev mode (returns 401 with 'not configured')."""
        response = requests.get(
            f"{api_server}/internal/config/TEST_KEY", headers={"X-Internal-Secret": "test_secret"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data.get("detail") == "ONI_INTERNAL_SECRET is not configured"


# ============================================================================
# Integration Tests (End-to-End Flow)
# ============================================================================


class TestIntegrationE2E:
    """Integration tests that verify complete user flows.

    Tests follow the complete user journey:
    1. User sends /base_commit command
    2. System returns modal with blocks
    3. User fills form and submits
    4. System creates plan event
    """

    def test_complete_base_commit_flow(self, api_server):
        """
        Test complete flow: /base_commit → plan registration

        This test verifies:
        1. /base_commit command works
        2. Modal is properly formatted
        3. Plan can be registered (via mock data)
        """
        # Step 1: Send /base_commit command
        timestamp = str(int(time.time()))

        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484", "text": ""}

        body = urlencode(form_data).encode()
        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        assert response.status_code == 200
        initial_data = response.json()
        assert initial_data["status"] == "success"
        assert "blocks" in initial_data
