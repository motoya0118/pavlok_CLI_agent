# v0.3 Internal Protection Middleware Tests
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from backend.api.internal_protection import verify_internal_request


@pytest.mark.asyncio
class TestInternalProtectionMiddleware:
    @pytest.mark.asyncio
    async def test_valid_secret_acceptance(self):
        signing_secret = "test-secret"
        with patch.dict(os.environ, {"ONI_INTERNAL_SECRET": signing_secret}):
            request = MagicMock(spec=Request)
            request.url.path = "/internal/api/test"
            request.headers = {"X-Internal-Secret": signing_secret}

            # Mock request.json() and body()
            async def mock_json():
                return {}

            async def mock_body():
                return b"{}"

            request.json = mock_json
            request.body = mock_body

            result = await verify_internal_request(request)
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_secret_rejection(self):
        signing_secret = "correct-secret"
        with patch.dict(os.environ, {"ONI_INTERNAL_SECRET": signing_secret}):
            request = MagicMock(spec=Request)
            request.url.path = "/internal/api/test"
            request.headers = {"X-Internal-Secret": "wrong-secret"}

            async def mock_json():
                return {}

            async def mock_body():
                return b"{}"

            request.json = mock_json
            request.body = mock_body

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_request(request)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_secret_rejection(self):
        signing_secret = "test-secret"
        with patch.dict(os.environ, {"ONI_INTERNAL_SECRET": signing_secret}):
            request = MagicMock(spec=Request)
            request.url.path = "/internal/api/test"
            request.headers = {}

            async def mock_json():
                return {}

            async def mock_body():
                return b"{}"

            request.json = mock_json
            request.body = mock_body

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_request(request)
            assert exc_info.value.status_code == 401
