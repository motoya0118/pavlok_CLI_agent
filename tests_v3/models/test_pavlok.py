# v0.3 Pavlok Client Tests (TDD)
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Configuration, ConfigValueType
from backend.models import EventType, Schedule, ScheduleState
from backend.pavlok_lib import (
    PavlokClient,
    stimulate_notification_for_user,
    build_reason_for_schedule_id,
)


class TestPavlokClientValidation:
    """Test PavlokClient validation logic (no API calls required)"""

    def test_init_with_api_key(self):
        """Test client initialization with API key"""
        client = PavlokClient(api_key="test-api-key-123")
        assert client.api_key == "test-api-key-123"

    def test_init_with_env_api_key(self, monkeypatch):
        """Test client initialization using env variable"""
        monkeypatch.setenv("PAVLOK_API_KEY", "env-api-key")
        client = PavlokClient()
        assert client.api_key == "env-api-key"

    def test_init_without_api_key_raises_error(self, monkeypatch):
        """Test initialization without API key raises ValueError"""
        monkeypatch.delenv("PAVLOK_API_KEY", raising=False)
        with pytest.raises(ValueError, match="PAVLOK_API_KEY is not set"):
            PavlokClient()

    def test_custom_api_base(self):
        """Test custom API base URL"""
        custom_base = "https://test-api.example.com/api/v5"
        client = PavlokClient(api_key="test-key", api_base=custom_base)
        assert client.api_base == custom_base

    def test_custom_http_client(self):
        """Test custom HTTP client injection"""
        class MockHTTP:
            def post(self, *args, **kwargs):
                pass
            def get(self, *args, **kwargs):
                pass

        mock_http = MockHTTP()
        client = PavlokClient(api_key="test-key", http_client=mock_http)
        assert client.http_client == mock_http

    def test_invalid_stimulus_type(self):
        """Test invalid stimulus type raises error"""
        client = PavlokClient(api_key="test-key")

        with pytest.raises(ValueError, match="Invalid stimulus type"):
            client._validate_stimulus_type("invalid_type")

    def test_value_out_of_range_high(self):
        """Test value > 100 raises error"""
        client = PavlokClient(api_key="test-key")

        with pytest.raises(ValueError, match="Value must be between"):
            client._validate_value(150)

    def test_value_out_of_range_low(self):
        """Test value < 0 raises error"""
        client = PavlokClient(api_key="test-key")

        with pytest.raises(ValueError, match="Value must be between"):
            client._validate_value(-10)

    def test_valid_stimulus_types(self):
        """Test all valid stimulus types pass validation"""
        client = PavlokClient(api_key="test-key")

        # Should not raise
        client._validate_stimulus_type("zap")
        client._validate_stimulus_type("beep")
        client._validate_stimulus_type("vibe")

    def test_valid_values_pass_validation(self):
        """Test valid values (0-100) pass validation"""
        client = PavlokClient(api_key="test-key")

        # Should not raise
        client._validate_value(0)
        client._validate_value(50)
        client._validate_value(100)

    def test_get_headers_format(self):
        """Test headers are formatted correctly"""
        client = PavlokClient(api_key="test-api-key")
        headers = client._get_headers()

        assert headers["accept"] == "application/json"
        assert headers["content-type"] == "application/json"
        assert headers["authorization"] == "Bearer test-api-key"


class TestPavlokClientWithMock:
    """Test PavlokClient with mock HTTP client"""

    def test_stimulate_zap_success(self):
        """Test zap stimulation with mock"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.stimulate(stimulus_type="zap", value=50)

        assert response["success"] is True
        assert response["type"] == "zap"
        assert response["value"] == 50

    def test_stimulate_vibe_success(self):
        """Test vibe stimulation with mock"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.stimulate(stimulus_type="vibe", value=100)

        assert response["success"] is True
        assert response["type"] == "vibe"
        assert response["value"] == 100

    def test_stimulate_beep_success(self):
        """Test beep stimulation with mock"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.stimulate(stimulus_type="beep", value=80)

        assert response["success"] is True
        assert response["type"] == "beep"
        assert response["value"] == 80

    def test_stimulate_default_value(self):
        """Test stimulate with default value (50)"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.stimulate(stimulus_type="zap")

        assert response["success"] is True
        assert response["value"] == 50  # default value

    def test_stimulate_with_reason_sends_payload_reason(self):
        """Test reason field is included in stimulus payload."""
        captured_payload = {}

        class MockResponse:
            status_code = 200

            def json(self):
                return {"status": "ok"}

            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                captured_payload.update(json)
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.stimulate(
            stimulus_type="vibe",
            value=80,
            reason="remind: ジム行く",
        )

        assert response["success"] is True
        assert response["reason"] == "remind: ジム行く"
        assert captured_payload["stimulus"]["reason"] == "remind: ジム行く"

    def test_zap_method(self):
        """Test convenience zap method"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.zap(value=70)

        assert response["success"] is True
        assert response["type"] == "zap"
        assert response["value"] == 70

    def test_vibe_method(self):
        """Test convenience vibe method"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.vibe(value=100)

        assert response["success"] is True
        assert response["type"] == "vibe"
        assert response["value"] == 100

    def test_beep_method(self):
        """Test convenience beep method"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        response = client.beep(value=90)

        assert response["success"] is True
        assert response["type"] == "beep"
        assert response["value"] == 90

    def test_api_error_handling(self):
        """Test API error handling"""
        class MockResponse:
            status_code = 401

        class MockHTTP:
            def post(self, url, json, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())

        response = client.stimulate(stimulus_type="zap", value=50)

        assert response["success"] is False
        assert "error" in response

    def test_get_status_success(self):
        """Test get_status method with mock"""
        class MockResponse:
            status_code = 200
            def json(self):
                return {"battery": 85, "is_charging": False}
            def raise_for_status(self):
                pass

        class MockHTTP:
            def get(self, url, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        status = client.get_status()

        assert status.get("success") is True
        assert status.get("battery") == 85
        assert status.get("is_charging") is False

    def test_get_status_error_handling(self):
        """Test get_status error handling"""
        class MockResponse:
            status_code = 500

        class MockHTTP:
            def get(self, url, headers, timeout):
                return MockResponse()

        client = PavlokClient(api_key="test-key", http_client=MockHTTP())
        status = client.get_status()

        assert status["success"] is False
        assert "error" in status


class TestNotificationStimulusConfig:
    """Test DB-backed notification stimulus helper."""

    def test_notification_stimulus_uses_defaults_when_config_missing(self, tmp_path, monkeypatch):
        db_path = tmp_path / "notification_defaults.sqlite3"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.pavlok_lib.client._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.pavlok_lib.client._SESSION_DB_URL", None)

        calls: list[tuple[str, int, str]] = []

        class _FakePavlokClient:
            VALID_STIMULUS_TYPES = ("zap", "beep", "vibe")

            def __init__(self, *args, **kwargs):
                pass

            def stimulate(self, stimulus_type: str, value: int, reason: str = ""):
                calls.append((stimulus_type, value, reason))
                return {
                    "success": True,
                    "type": stimulus_type,
                    "value": value,
                    "reason": reason,
                }

        monkeypatch.setattr(
            "backend.pavlok_lib.client.PavlokClient",
            _FakePavlokClient,
        )

        result = stimulate_notification_for_user(
            user_id="U_TEST",
            reason="plan: 今日のプランを登録してください",
        )
        assert result["success"] is True
        assert calls == [("vibe", 100, "plan: 今日のプランを登録してください")]

    def test_notification_stimulus_uses_user_config_values(self, tmp_path, monkeypatch):
        db_path = tmp_path / "notification_user_config.sqlite3"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = Session()
        try:
            session.add_all(
                [
                    Configuration(
                        user_id="U_TEST",
                        key="PAVLOK_TYPE_NOTION",
                        value="beep",
                        value_type=ConfigValueType.STR,
                    ),
                    Configuration(
                        user_id="U_TEST",
                        key="PAVLOK_VALUE_NOTION",
                        value="80",
                        value_type=ConfigValueType.INT,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.pavlok_lib.client._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.pavlok_lib.client._SESSION_DB_URL", None)

        calls: list[tuple[str, int, str]] = []

        class _FakePavlokClient:
            VALID_STIMULUS_TYPES = ("zap", "beep", "vibe")

            def __init__(self, *args, **kwargs):
                pass

            def stimulate(self, stimulus_type: str, value: int, reason: str = ""):
                calls.append((stimulus_type, value, reason))
                return {
                    "success": True,
                    "type": stimulus_type,
                    "value": value,
                    "reason": reason,
                }

        monkeypatch.setattr(
            "backend.pavlok_lib.client.PavlokClient",
            _FakePavlokClient,
        )

        result = stimulate_notification_for_user(
            user_id="U_TEST",
            reason="remind: ジム行く",
        )
        assert result["success"] is True
        assert calls == [("beep", 80, "remind: ジム行く")]

    def test_build_reason_for_schedule_id_plan_and_remind(self, tmp_path, monkeypatch):
        db_path = tmp_path / "notification_reason.sqlite3"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = Session()
        try:
            user_id = "U_TEST"
            session.add(
                Configuration(
                    user_id=user_id,
                    key="PAVLOK_TYPE_NOTION",
                    value="vibe",
                    value_type=ConfigValueType.STR,
                )
            )
            session.add(
                Configuration(
                    user_id=user_id,
                    key="PAVLOK_VALUE_NOTION",
                    value="100",
                    value_type=ConfigValueType.INT,
                )
            )
            session.add(
                Configuration(
                    user_id=user_id,
                    key="IGNORE_INTERVAL",
                    value="900",
                    value_type=ConfigValueType.INT,
                )
            )
            session.add(
                Configuration(
                    user_id=user_id,
                    key="TIMEOUT_REMIND",
                    value="600",
                    value_type=ConfigValueType.INT,
                )
            )
            plan_schedule = Schedule(
                user_id=user_id,
                event_type=EventType.PLAN,
                run_at=datetime.now(),
                state=ScheduleState.PENDING,
            )
            from backend.models import Commitment

            commitment = Commitment(
                user_id=user_id,
                task="ジム行く",
                time="07:00:00",
                active=True,
            )
            session.add(commitment)
            session.flush()
            remind_schedule = Schedule(
                user_id=user_id,
                event_type=EventType.REMIND,
                commitment_id=commitment.id,
                run_at=datetime(2026, 2, 19, 7, 0, 0),
                state=ScheduleState.PENDING,
            )
            session.add_all([plan_schedule, remind_schedule])
            session.flush()
            plan_id = plan_schedule.id
            remind_id = remind_schedule.id
            session.add(
                Configuration(
                    user_id=user_id,
                    key="COACH_CHARACTOR",
                    value="ラムちゃん",
                    value_type=ConfigValueType.STR,
                )
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.pavlok_lib.client._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.pavlok_lib.client._SESSION_DB_URL", None)

        plan_reason = build_reason_for_schedule_id(plan_id)
        remind_reason = build_reason_for_schedule_id(remind_id)

        assert plan_reason == "plan: 今日のプランを登録してください"
        assert remind_reason == "remind: ジム行く"


class TestMockPavlokClientFixture:
    """Test MockPavlokClient from conftest"""

    def test_zap_count_tracking(self, mock_pavlok_client):
        """Test zap count tracking"""
        assert mock_pavlok_client.get_zap_count() == 0

        mock_pavlok_client.zap(value=50)
        assert mock_pavlok_client.get_zap_count() == 1

        mock_pavlok_client.zap(value=70)
        assert mock_pavlok_client.get_zap_count() == 2

    def test_vibe_count_tracking(self, mock_pavlok_client):
        """Test vibe count tracking"""
        assert mock_pavlok_client.get_vibe_count() == 0

        mock_pavlok_client.vibe(value=100)
        assert mock_pavlok_client.get_vibe_count() == 1

    def test_beep_count_tracking(self, mock_pavlok_client):
        """Test beep count tracking"""
        assert mock_pavlok_client.get_beep_count() == 0

        mock_pavlok_client.beep(value=80)
        assert mock_pavlok_client.get_beep_count() == 1

    def test_reset(self, mock_pavlok_client):
        """Test reset method clears counts"""
        mock_pavlok_client.zap(value=50)
        mock_pavlok_client.vibe(value=100)

        assert mock_pavlok_client.get_zap_count() == 1
        assert mock_pavlok_client.get_vibe_count() == 1

        mock_pavlok_client.reset()

        assert mock_pavlok_client.get_zap_count() == 0
        assert mock_pavlok_client.get_vibe_count() == 0

    def test_fail_mode(self, mock_pavlok_client):
        """Test fail mode affects responses"""
        mock_pavlok_client.set_fail_mode(True)

        response = mock_pavlok_client.stimulate(stimulus_type="zap", value=50)

        assert response["success"] is False
        assert "error" in response

    def test_call_history(self, mock_pavlok_client):
        """Test call history tracking"""
        mock_pavlok_client.zap(value=50)
        mock_pavlok_client.vibe(value=100)

        history = mock_pavlok_client.get_call_history()
        assert len(history) == 2
        assert history[0].method == "stimulate"
        assert history[1].method == "stimulate"

    def test_assert_called(self, mock_pavlok_client):
        """Test assert_called method"""
        mock_pavlok_client.zap(value=50)

        # Should not raise
        mock_pavlok_client.assert_called("stimulate", times=1)

        # Should raise
        with pytest.raises(AssertionError):
            mock_pavlok_client.assert_called("nonexistent_method")

    def test_assert_not_called(self, mock_pavlok_client):
        """Test assert_not_called method"""
        mock_pavlok_client.reset()

        # Should not raise
        mock_pavlok_client.assert_not_called("stimulate")
