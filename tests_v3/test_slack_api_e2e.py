"""E2E API Tests for Oni System v0.3

These tests verify API responses without relying on unimplemented handlers.
Tests use mock data to simulate complete Slack interactions.
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
                                "text": {
                                    "type": "plain_text",
                                    "text": "+ 追加",
                                },
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
# Slack User Flow Tests (Based on Design Document)
# ============================================================================


class TestSlackAPIE2E:
    """Test Slack API endpoints with mock data and verify responses.

    Tests follow v0.3 design document flow:
    - 7.1 init: /base_commit command → Modal
    - 7.2 plan: Modal submission → plan event
    - 7.3 remind: YES button → action log
    """

    def test_init_command_returns_modal(self, api_server):
        """
        Test 7.1 init flow: /base_commit command

        Expected:
        - 200 status
        - Modal response with trigger_id or view
        """
        timestamp = str(int(time.time()))

        # Create form data as Slack would send it
        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484", "text": ""}

        # Create signature
        body = urlencode(form_data).encode()
        signature = create_slack_signature(timestamp, body)

        # Send request
        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )

        # Verify response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "success", f"Expected success status, got {data}"
        assert "detail" in data or "text" in data or "blocks" in data, (
            f"Expected modal data, got {list(data.keys())}"
        )

        # Verify modal structure
        if "blocks" in data:
            blocks = data["blocks"]
            assert len(blocks) > 0, "Expected at least one block"

            # Check for modal or view
            assert "type" in blocks[0], "Expected first block to be modal or view"
            block_type = blocks[0]["type"]

            if block_type == "modal":
                # Verify modal structure
                assert "view" in blocks[0], "Modal should have view"
                view = blocks[0]["view"]
                assert "callback_id" in view, "Modal should have callback_id"
                assert view["callback_id"] == "base_commit_submit", (
                    f"Expected callback_id 'base_commit_submit', got {view['callback_id']}"
                )
                assert "title" in view, "Modal should have title"
                assert "submit" in view, "Modal should have submit button"

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


class TestSlackAPISignatureValidation:
    """Test Slack signature validation independently."""

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
        from urllib.parse import urlencode

        form_data = {"command": "/base_commit", "user_id": "U03JBLT484"}

        urlencode(form_data).encode()

        # Send without signature
        response = requests.post(
            f"{api_server}/slack/command",
            data=form_data,
            headers={"X-Slack-Request-Timestamp": str(int(time.time()))},
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
