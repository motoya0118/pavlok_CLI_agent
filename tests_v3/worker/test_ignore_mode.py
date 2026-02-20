# v0.3 Worker Ignore Mode Detection Tests
from datetime import datetime, timedelta

import pytest

from backend.models import (
    ActionLog,
    ActionResult,
    Punishment,
    PunishmentMode,
    ScheduleState,
)
from backend.worker.ignore_mode import calculate_ignore_punishment, detect_ignore_mode


@pytest.mark.asyncio
class TestIgnoreModeDetection:
    @staticmethod
    def _set_processing_started_at(session, schedule, seconds_ago: int) -> None:
        schedule.updated_at = datetime.now() - timedelta(seconds=seconds_ago)
        session.commit()

    @pytest.mark.asyncio
    async def test_detect_ignore_single_interval(self, v3_db_session, v3_test_data_factory):
        """1回のignore_intervalを検知できること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=900),  # IGNORE_INTERVAL default
            state=ScheduleState.PROCESSING,
        )
        self._set_processing_started_at(v3_db_session, schedule, 900)

        from backend.worker import ignore_mode

        original_send = ignore_mode._send_punishment
        ignore_mode._send_punishment = lambda stimulus_type, value, reason="": True
        result = detect_ignore_mode(v3_db_session, schedule)
        ignore_mode._send_punishment = original_send

        assert result["detected"] is True
        assert result["ignore_time"] == 1
        punishments = v3_db_session.query(Punishment).filter_by(schedule_id=schedule.id).all()
        assert len(punishments) == 1
        assert punishments[0].mode == PunishmentMode.IGNORE
        assert punishments[0].count == 1

    @pytest.mark.asyncio
    async def test_detect_ignore_multiple_intervals(self, v3_db_session, v3_test_data_factory):
        """複数回のignore_intervalを検知できること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=1800),  # 30分 = 2 intervals
            state=ScheduleState.PROCESSING,
        )
        self._set_processing_started_at(v3_db_session, schedule, 1800)

        from backend.worker import ignore_mode

        original_send = ignore_mode._send_punishment
        ignore_mode._send_punishment = lambda stimulus_type, value, reason="": True
        result = detect_ignore_mode(v3_db_session, schedule)
        ignore_mode._send_punishment = original_send

        assert result["detected"] is True
        assert result["ignore_time"] == 2
        punishments = v3_db_session.query(Punishment).filter_by(schedule_id=schedule.id).all()
        assert len(punishments) == 1
        assert punishments[0].count == 2

    @pytest.mark.asyncio
    async def test_no_ignore_within_interval(self, v3_db_session, v3_test_data_factory):
        """ignore_interval内では検知しないこと"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=300),  # 5分 < 15分
            state=ScheduleState.PROCESSING,
        )
        self._set_processing_started_at(v3_db_session, schedule, 300)

        result = detect_ignore_mode(v3_db_session, schedule)
        assert result["detected"] is False

    @pytest.mark.asyncio
    async def test_calculate_punishment_ignore_first_time(self):
        """初回ignoreはIGNORE:100であること"""
        result = calculate_ignore_punishment(ignore_time=1)
        assert result["type"] == "vibe"
        assert result["value"] == 100

    @pytest.mark.asyncio
    async def test_calculate_punishment_zap_second_time(self):
        """2回目ignoreはZAP:35であること"""
        result = calculate_ignore_punishment(ignore_time=2)
        assert result["type"] == "zap"
        assert result["value"] == 35

    @pytest.mark.asyncio
    async def test_calculate_punishment_zap_third_time(self):
        """3回目ignoreはZAP:45であること"""
        result = calculate_ignore_punishment(ignore_time=3)
        assert result["type"] == "zap"
        assert result["value"] == 45

    @pytest.mark.asyncio
    async def test_calculate_punishment_zap_max_100(self):
        """ZAPは最大100であること"""
        result = calculate_ignore_punishment(ignore_time=10)
        assert result["type"] == "zap"
        assert result["value"] == 100

    @pytest.mark.asyncio
    async def test_punishment_already_exists(self, v3_db_session, v3_test_data_factory):
        """既存の罰レコードがある場合は追加しないこと"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=900),
            state=ScheduleState.PROCESSING,
        )
        self._set_processing_started_at(v3_db_session, schedule, 900)
        v3_test_data_factory.create_punishment(
            schedule_id=schedule.id, mode=PunishmentMode.IGNORE, count=1
        )

        from backend.worker import ignore_mode

        original_send = ignore_mode._send_punishment
        ignore_mode._send_punishment = lambda stimulus_type, value, reason="": True
        result = detect_ignore_mode(v3_db_session, schedule)
        ignore_mode._send_punishment = original_send

        assert result["detected"] is True
        assert result["ignore_time"] == 1
        # No duplicate row for the same trigger index.
        punishments = v3_db_session.query(Punishment).filter_by(schedule_id=schedule.id).all()
        assert len(punishments) == 1

    @pytest.mark.asyncio
    async def test_auto_ignore_marks_schedule_canceled_at_zap_100(
        self, v3_db_session, v3_test_data_factory
    ):
        """ignore罰が100到達時にcanceled+AUTO_IGNOREを記録すること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=8100),  # ignore_time=9
            state=ScheduleState.PROCESSING,
            thread_ts="1730000000.000001",
        )
        self._set_processing_started_at(v3_db_session, schedule, 8100)

        from backend.worker import ignore_mode

        notify_calls = []
        original_send = ignore_mode._send_punishment
        original_notify = ignore_mode._notify_auto_canceled_once
        ignore_mode._send_punishment = lambda stimulus_type, value, reason="": True
        ignore_mode._notify_auto_canceled_once = (
            lambda session, s, final_stimulus_type, final_stimulus_value: (
                notify_calls.append((str(s.id), final_stimulus_type, final_stimulus_value)) or True
            )
        )

        result = detect_ignore_mode(v3_db_session, schedule)

        ignore_mode._send_punishment = original_send
        ignore_mode._notify_auto_canceled_once = original_notify

        assert result["detected"] is True
        assert result["ignore_time"] >= 9
        v3_db_session.refresh(schedule)
        assert schedule.state == ScheduleState.CANCELED
        auto_ignore_count = (
            v3_db_session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule.id,
                ActionLog.result == ActionResult.AUTO_IGNORE,
            )
            .count()
        )
        assert auto_ignore_count == 1
        assert len(notify_calls) == 1

    @pytest.mark.asyncio
    async def test_ignore_max_retry_exceeded_marks_auto_ignore_once(
        self, v3_db_session, v3_test_data_factory, monkeypatch
    ):
        """IGNORE_MAX_RETRY超過でcanceled+AUTO_IGNOREを1回だけ記録すること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=2700),  # ignore_time=3
            state=ScheduleState.PROCESSING,
            thread_ts="1730000000.000002",
        )
        self._set_processing_started_at(v3_db_session, schedule, 2700)

        from backend.worker import ignore_mode

        original_get_config = __import__(
            "backend.worker.config_cache", fromlist=["get_config"]
        ).get_config
        original_send = ignore_mode._send_punishment
        original_notify = ignore_mode._notify_auto_canceled_once

        def _fake_get_config(key, default=None, session=None):
            if key == "IGNORE_MAX_RETRY":
                return 2
            return default

        notify_calls = []
        monkeypatch.setattr("backend.worker.config_cache.get_config", _fake_get_config)
        ignore_mode._send_punishment = lambda stimulus_type, value, reason="": True
        ignore_mode._notify_auto_canceled_once = (
            lambda session, s, final_stimulus_type, final_stimulus_value: (
                notify_calls.append((str(s.id), final_stimulus_type, final_stimulus_value)) or True
            )
        )

        first = detect_ignore_mode(v3_db_session, schedule)
        second = detect_ignore_mode(v3_db_session, schedule)

        ignore_mode._send_punishment = original_send
        ignore_mode._notify_auto_canceled_once = original_notify
        monkeypatch.setattr("backend.worker.config_cache.get_config", original_get_config)

        assert first["detected"] is True
        assert second["detected"] is True
        v3_db_session.refresh(schedule)
        assert schedule.state == ScheduleState.CANCELED
        auto_ignore_count = (
            v3_db_session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule.id,
                ActionLog.result == ActionResult.AUTO_IGNORE,
            )
            .count()
        )
        assert auto_ignore_count == 1
        assert len(notify_calls) == 1
