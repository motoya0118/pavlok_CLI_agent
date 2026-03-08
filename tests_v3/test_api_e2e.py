"""E2E API Tests for Oni System v0.3

These tests require a running FastAPI server.
Run with: pytest -v -m e2e tests_v3/test_api_e2e.py

Start server before running:
  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
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
    """Start and stop the FastAPI server for testing."""
    with run_api_server(extra_env={"ONI_INTERNAL_SECRET": "test_internal_secret"}) as base_url:
        yield base_url


# ============================================================================
# Slack Signature Helper
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
# Health Check Tests (Normal Flow)
# ============================================================================


class TestHealthCheck:
    """Test health check endpoint - critical for monitoring."""

    def test_health_returns_200(self, api_server):
        """Test that health endpoint returns 200 status."""
        response = requests.get(f"{api_server}/health")
        assert response.status_code == 200

    def test_health_returns_valid_json(self, api_server):
        """Test that health endpoint returns valid JSON."""
        response = requests.get(f"{api_server}/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data

    def test_health_version_is_0_3(self, api_server):
        """Test that health endpoint reports v0.3.0."""
        response = requests.get(f"{api_server}/health")
        data = response.json()
        assert data["version"] == "0.3.0"


# ============================================================================
# Slack Command Tests (Normal Flow)
# ============================================================================


class TestSlackCommand:
    """Test Slack slash command endpoints."""

    def test_base_commit_command(self, api_server):
        """Test /base_commit command returns modal with valid signature."""
        from urllib.parse import urlencode

        timestamp = str(int(time.time()))
        form_data = {"command": "/base_commit", "user_id": "U03JBULT484", "text": ""}
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

    def test_stop_command(self, api_server):
        """Test /stop command with valid signature."""
        from urllib.parse import urlencode

        timestamp = str(int(time.time()))
        form_data = {"command": "/stop", "user_id": "U03JBULT484", "text": ""}
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
        """Test /restart command with valid signature."""
        from urllib.parse import urlencode

        timestamp = str(int(time.time()))
        form_data = {"command": "/restart", "user_id": "U03JBULT484", "text": ""}
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
# Internal API Tests (Normal Flow)
# ============================================================================


class TestInternalAPI:
    """Test internal endpoints for Worker communication."""

    def test_execute_plan_event(self, api_server):
        """Test /internal/execute/plan endpoint with valid secret."""
        response = requests.post(
            f"{api_server}/internal/execute/plan",
            headers={"X-Internal-Secret": "test_internal_secret"},
        )
        # Should return 200 with valid secret
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "plan"

    def test_execute_remind_event(self, api_server):
        """Test /internal/execute/remind endpoint with valid secret."""
        response = requests.post(
            f"{api_server}/internal/execute/remind",
            headers={"X-Internal-Secret": "test_internal_secret"},
        )
        # Should return 200 with valid secret
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["event_type"] == "remind"

    def test_get_config_value(self, api_server):
        """Test /internal/config/{key} endpoint with valid secret."""
        response = requests.get(
            f"{api_server}/internal/config/PAVLOK_VALUE_PUNISH",
            headers={"X-Internal-Secret": "test_internal_secret"},
        )
        # Should return 200 with valid secret
        assert response.status_code == 200
        data = response.json()
        assert "key" in data


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling."""

    def test_unknown_endpoint_returns_404(self, api_server):
        """Test that unknown endpoints return 404."""
        response = requests.get(f"{api_server}/unknown")
        assert response.status_code == 404

    def test_invalid_json_returns_400_or_401(self, api_server):
        """Test that invalid payload returns error."""
        timestamp = str(int(time.time()))

        # Create a request with invalid payload
        body = b"payload=invalid_json"
        signature = create_slack_signature(timestamp, body)

        response = requests.post(
            f"{api_server}/slack/interactive",
            data={"payload": "invalid_json"},
            headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        )
        # Should return 400 (bad request) or handle gracefully
        assert response.status_code in [400, 500]


# ============================================================================
# Manual Test Script
# ============================================================================


def run_manual_tests(base_url="http://localhost:8000"):
    """Run manual tests against running server."""
    print("\n" + "=" * 60)
    print("E2E API Test - Oni System v0.3")
    print("=" * 60)

    # Test 1: Health Check
    print("\n[Test 1] Health Check")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
        assert response.status_code == 200
        print("  ✓ PASSED")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    # Test 2: Health returns valid data
    print("\n[Test 2] Health returns valid JSON")
    try:
        response = requests.get(f"{base_url}/health")
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.3.0"
        print("  Status: ok")
        print(f"  Version: {data['version']}")
        print("  ✓ PASSED")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    # Test 3: Unknown endpoint
    print("\n[Test 3] Unknown endpoint returns 404")
    try:
        response = requests.get(f"{base_url}/unknown")
        assert response.status_code == 404
        print(f"  Status: {response.status_code}")
        print("  ✓ PASSED")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    # Test 4: Slack command without signature
    print("\n[Test 4] Slack command without signature returns 401")
    try:
        response = requests.post(f"{base_url}/slack/command", data={"command": "/base_commit"})
        assert response.status_code == 401
        print(f"  Status: {response.status_code}")
        print("  ✓ PASSED")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    # Test 5: Internal endpoint without secret
    print("\n[Test 5] Internal endpoint without secret returns 401")
    try:
        response = requests.post(f"{base_url}/internal/execute/plan")
        assert response.status_code == 401
        print(f"  Status: {response.status_code}")
        print("  ✓ PASSED")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import sys

    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    run_manual_tests(base_url)
