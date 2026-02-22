# v0.3 Slack Signature Verification Middleware Tests
import hashlib
import hmac
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from backend.api.signature import (
    verify_signature_middleware,
)


@pytest.mark.asyncio
class TestSignatureMiddleware:
    @pytest.mark.asyncio
    async def test_valid_signature_verification(self):
        timestamp = "1531420620005"
        signing_secret = "test-secret"
        body = b"test_body"

        # Slack公式フォーマット: v0:timestamp:body
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        expected_hash = hmac.new(
            signing_secret.encode(), msg=sig_basestring.encode(), digestmod=hashlib.sha256
        ).hexdigest()
        signature = f"v0={expected_hash}"

        with patch.dict(os.environ, {"SLACK_SIGNING_SECRET": signing_secret}):
            request = MagicMock(spec=Request)
            request.url.path = "/api/test"
            request.headers = {
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            }

            # Mock body() method to return bytes
            async def mock_body():
                return body

            request.body = mock_body

            # Mock call_next properly
            async def mock_call_next(req):
                return MagicMock()

            call_next = AsyncMock()
            call_next.side_effect = mock_call_next

            result = await verify_signature_middleware(request, call_next)
            assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_signature_rejection(self):
        timestamp = "1531420620005"
        signing_secret = "test-secret"
        signature = "v0:invalid"

        with patch.dict(os.environ, {"SLACK_SIGNING_SECRET": signing_secret}):
            request = MagicMock(spec=Request)
            request.url.path = "/api/test"
            request.headers = {
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            }

            async def mock_body():
                return b"test_body"

            request.body = mock_body

            async def mock_call_next(req):
                return MagicMock()

            call_next = AsyncMock()
            call_next.side_effect = mock_call_next

            with pytest.raises(HTTPException) as exc_info:
                await verify_signature_middleware(request, call_next)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_signature_rejection(self):
        signing_secret = "test-secret"
        timestamp = "1531420620005"

        with patch.dict(os.environ, {"SLACK_SIGNING_SECRET": signing_secret}):
            request = MagicMock(spec=Request)
            request.url.path = "/api/test"
            request.headers = {
                "X-Slack-Request-Timestamp": timestamp,
                # No signature header
            }

            async def mock_body():
                return b"test_body"

            request.body = mock_body

            async def mock_call_next(req):
                return MagicMock()

            call_next = AsyncMock()
            call_next.side_effect = mock_call_next

            with pytest.raises(HTTPException) as exc_info:
                await verify_signature_middleware(request, call_next)
            assert exc_info.value.status_code == 401
