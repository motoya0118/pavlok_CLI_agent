# v0.3 Config API Tests
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from backend.api.config import get_configurations, upsert_configuration


@pytest.mark.asyncio
class TestConfigApi:
    @pytest.mark.asyncio
    async def test_get_configurations(self, v3_db_session, v3_test_data_factory):
        request = MagicMock(spec=Request)
        request.method = "GET"

        result = await get_configurations(request)
        assert result["status"] == "success"
        assert "configurations" in result["data"]

    @pytest.mark.asyncio
    async def test_upsert_configuration(self, v3_db_session, v3_test_data_factory):
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.state = "config"

        new_config = {
            "PAVLOK_TYPE_PUNISH": "vibe",
            "PAVLOK_VALUE_PUNISH": "100",
        }

        result = await upsert_configuration(request, new_config)

        assert result["status"] == "success"
        assert result["data"]["PAVLOK_TYPE_PUNISH"] == "vibe"
        assert result["data"]["PAVLOK_VALUE_PUNISH"] == 100
