# v0.3 Worker No Mode Detection Tests
from datetime import datetime, timedelta

import pytest

from backend.models import Punishment, PunishmentMode
from backend.worker.no_mode import calculate_no_punishment, detect_no_mode


@pytest.mark.asyncio
class TestNoModeDetection:
    @pytest.mark.asyncio
    async def test_detect_no_response_within_timeout(self, v3_db_session, v3_test_data_factory):
        """TIMEOUT_REMIND内で応答がない場合no_modeを検知できること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=600),  # 10分
        )

        result = detect_no_mode(v3_db_session, schedule)
        assert result["detected"] is True
        assert result["no_time"] == 1

    @pytest.mark.asyncio
    async def test_no_detection_before_timeout(self, v3_db_session, v3_test_data_factory):
        """TIMEOUT_REMIND内では検知しないこと"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=300),  # 5分
        )

        result = detect_no_mode(v3_db_session, schedule)
        assert result["detected"] is False

    @pytest.mark.asyncio
    async def test_calculate_punishment_zap_incremental(self):
        """no_modeはZAP:35,55,75,100と増加すること"""
        # 1回目
        result1 = calculate_no_punishment(no_time=1)
        assert result1["mode"] == PunishmentMode.NO
        assert result1["value"] == 35

        # 2回目
        result2 = calculate_no_punishment(no_time=2)
        assert result2["mode"] == PunishmentMode.NO
        assert result2["value"] == 55

        # 3回目
        result3 = calculate_no_punishment(no_time=3)
        assert result3["mode"] == PunishmentMode.NO
        assert result3["value"] == 75

        # 4回目
        result4 = calculate_no_punishment(no_time=4)
        assert result4["mode"] == PunishmentMode.NO
        assert result4["value"] == 100

    @pytest.mark.asyncio
    async def test_calculate_punishment_max_100(self):
        """ZAPは最大100であること"""
        result = calculate_no_punishment(no_time=10)
        assert result["mode"] == PunishmentMode.NO
        assert result["value"] == 100

    @pytest.mark.asyncio
    async def test_punishment_already_exists(self, v3_db_session, v3_test_data_factory):
        """既存の罰レコードがある場合は追加しないこと"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=600)
        )
        # Create existing punishment with count=1 (which matches no_time=1)
        v3_test_data_factory.create_punishment(
            schedule_id=schedule.id,
            mode=PunishmentMode.NO,
            count=1,  # This matches no_time
        )

        result = detect_no_mode(v3_db_session, schedule)
        assert result["detected"] is True
        assert result["no_time"] == 1
        # Should still be 1 punishment (no duplicate)
        punishments = v3_db_session.query(Punishment).filter_by(schedule_id=schedule.id).all()
        assert len(punishments) == 1

    @pytest.mark.asyncio
    async def test_yes_response_clears_no_mode(self, v3_db_session, v3_test_data_factory):
        """YES応答でno_mode検知がリセットされること"""
        from backend.models import ActionResult

        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(seconds=600)
        )
        # Create YES action log
        v3_test_data_factory.create_action_log(schedule_id=schedule.id, result=ActionResult.YES)

        result = detect_no_mode(v3_db_session, schedule)
        assert result["detected"] is False
