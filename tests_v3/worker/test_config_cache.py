# v0.3 Worker Config Cache Tests
import pytest
import time
from unittest.mock import MagicMock, patch
from backend.worker.config_cache import get_config, invalidate_config_cache


@pytest.mark.asyncio
class TestConfigCache:

    @pytest.mark.asyncio
    async def test_get_config_from_db(self, v3_db_session, v3_test_data_factory):
        """DBから設定値を取得できること"""
        config = v3_test_data_factory.create_configuration(
            key="TEST_CONFIG",
            value="test_value",
            value_type="str"
        )

        result = get_config("TEST_CONFIG", session=v3_db_session)
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_config_from_env(self, v3_db_session):
        """環境変数から設定値を取得できること"""
        with patch.dict("os.environ", {"TEST_ENV_CONFIG": "env_value"}):
            result = get_config("TEST_ENV_CONFIG")
            assert result == "env_value"

    @pytest.mark.asyncio
    async def test_get_config_default(self, v3_db_session):
        """デフォルト値を取得できること"""
        result = get_config("NON_EXISTENT_CONFIG", default="default_value")
        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_cache_ttl_60_seconds(self, v3_db_session, v3_test_data_factory):
        """キャッシュが60秒間有効であること"""
        config = v3_test_data_factory.create_configuration(
            key="CACHE_TEST_CONFIG",
            value="initial_value",
            value_type="str"
        )

        # First call - from DB
        result1 = get_config("CACHE_TEST_CONFIG", session=v3_db_session)
        assert result1 == "initial_value"

        # Update DB
        config.value = "updated_value"
        v3_db_session.commit()

        # Second call - should return cached value (not updated)
        result2 = get_config("CACHE_TEST_CONFIG", session=v3_db_session)
        assert result2 == "initial_value"

        # Wait for cache to expire
        time.sleep(61)

        # Third call - should return updated value
        result3 = get_config("CACHE_TEST_CONFIG", session=v3_db_session)
        assert result3 == "updated_value"

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, v3_db_session, v3_test_data_factory):
        """キャッシュの無効化ができること"""
        config = v3_test_data_factory.create_configuration(
            key="INVALIDATE_TEST_CONFIG",
            value="initial_value",
            value_type="str"
        )

        # First call
        result1 = get_config("INVALIDATE_TEST_CONFIG", session=v3_db_session)
        assert result1 == "initial_value"

        # Update DB
        config.value = "updated_value"
        v3_db_session.commit()

        # Invalidate cache
        invalidate_config_cache("INVALIDATE_TEST_CONFIG")

        # Should return updated value
        result2 = get_config("INVALIDATE_TEST_CONFIG", session=v3_db_session)
        assert result2 == "updated_value"

    @pytest.mark.asyncio
    async def test_parse_value_types(self, v3_db_session, v3_test_data_factory):
        """各種タイプの値を正しくパースできること"""
        # String type
        str_config = v3_test_data_factory.create_configuration(
            key="STR_CONFIG",
            value="hello",
            value_type="str"
        )
        assert get_config("STR_CONFIG", session=v3_db_session) == "hello"

        # Integer type
        int_config = v3_test_data_factory.create_configuration(
            key="INT_CONFIG",
            value="42",
            value_type="int"
        )
        assert get_config("INT_CONFIG", session=v3_db_session) == 42

        # Boolean type
        bool_config = v3_test_data_factory.create_configuration(
            key="BOOL_CONFIG",
            value="true",
            value_type="bool"
        )
        assert get_config("BOOL_CONFIG", session=v3_db_session) is True

        # JSON type
        import json
        json_value = json.dumps({"key": "value"})
        json_config = v3_test_data_factory.create_configuration(
            key="JSON_CONFIG",
            value=json_value,
            value_type="json"
        )
        assert get_config("JSON_CONFIG", session=v3_db_session) == {"key": "value"}

    @pytest.mark.asyncio
    async def test_env_only_timeout_remind_ignores_db(self, v3_db_session, v3_test_data_factory):
        """TIMEOUT_REMINDはDBより.env値を優先すること"""
        v3_test_data_factory.create_configuration(
            key="TIMEOUT_REMIND",
            value="1200",
            value_type="int",
        )
        invalidate_config_cache("TIMEOUT_REMIND")

        with patch.dict("os.environ", {"TIMEOUT_REMIND": "600"}):
            result = get_config("TIMEOUT_REMIND", 600, session=v3_db_session)
            assert result == 600

    @pytest.mark.asyncio
    async def test_retry_delay_env_fallback_key(self):
        """RETRY_DELAY未設定時はRETRY_DELAY_MINを後方互換で参照すること"""
        invalidate_config_cache("RETRY_DELAY")
        with patch.dict("os.environ", {"RETRY_DELAY_MIN": "7"}, clear=True):
            result = get_config("RETRY_DELAY", 5)
            assert result == 7
