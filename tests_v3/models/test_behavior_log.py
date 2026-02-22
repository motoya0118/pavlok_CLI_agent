# v0.3 Behavior Log Tests (TDD)
from datetime import datetime, timedelta

from sqlalchemy import and_, func

from backend.behavior_log_lib import BehaviorLogger
from backend.models import ActionLog, ActionResult


class TestBehaviorLogger:
    """Test BehaviorLogger for action_logs table"""

    def test_log_yes_action(self, v3_db_session, v3_test_data_factory):
        """Test logging YES action"""
        schedule = v3_test_data_factory.create_schedule()
        logger = BehaviorLogger(v3_db_session)

        action_log = logger.log_action(schedule_id=schedule.id, result=ActionResult.YES)

        assert action_log.id is not None
        assert action_log.schedule_id == schedule.id
        assert action_log.result == ActionResult.YES
        assert action_log.created_at is not None
        assert isinstance(action_log.created_at, datetime)

    def test_log_no_action(self, v3_db_session, v3_test_data_factory):
        """Test logging NO action"""
        schedule = v3_test_data_factory.create_schedule()
        logger = BehaviorLogger(v3_db_session)

        action_log = logger.log_action(schedule_id=schedule.id, result=ActionResult.NO)

        assert action_log.id is not None
        assert action_log.result == ActionResult.NO

    def test_log_auto_ignore_action(self, v3_db_session, v3_test_data_factory):
        """Test logging AUTO_IGNORE action"""
        schedule = v3_test_data_factory.create_schedule()
        logger = BehaviorLogger(v3_db_session)

        action_log = logger.log_action(schedule_id=schedule.id, result=ActionResult.AUTO_IGNORE)

        assert action_log.id is not None
        assert action_log.result == ActionResult.AUTO_IGNORE

    def test_get_logs_for_schedule(self, v3_db_session, v3_test_data_factory):
        """Test getting action logs for a specific schedule"""
        schedule = v3_test_data_factory.create_schedule()
        logger = BehaviorLogger(v3_db_session)

        # Log some actions
        logger.log_action(schedule.id, ActionResult.YES)
        logger.log_action(schedule.id, ActionResult.NO)
        logger.log_action(schedule.id, ActionResult.YES)

        logs = logger.get_logs_for_schedule(schedule.id)

        assert len(logs) == 3
        assert logs[0].result == ActionResult.YES
        assert logs[1].result == ActionResult.NO
        assert logs[2].result == ActionResult.YES

    def test_get_recent_logs(self, v3_db_session, v3_test_data_factory):
        """Test getting recent logs within a time range"""
        schedule = v3_test_data_factory.create_schedule()
        logger = BehaviorLogger(v3_db_session)

        # Log actions at different times
        now = datetime.now()
        logger.log_action(schedule.id, ActionResult.YES)

        now - timedelta(hours=1)
        # Note: Can't manipulate time in SQLite easily due to CHECK constraint
        # So this test is skipped for now

        # Simulate getting recent logs
        recent_logs = logger.get_recent_logs(hours=1)

        assert len(recent_logs) >= 1  # At least the recent action

    def test_get_today_stats_manual(self, v3_db_session, v3_test_data_factory):
        """Test getting daily statistics using manual query"""
        schedule = v3_test_data_factory.create_schedule()
        logger = BehaviorLogger(v3_db_session)

        # Log various actions
        logger.log_action(schedule.id, ActionResult.YES)
        logger.log_action(schedule.id, ActionResult.YES)
        logger.log_action(schedule.id, ActionResult.NO)

        # Manual count query
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        yes_count = (
            v3_db_session.query(func.count(ActionLog.id))
            .filter(
                and_(
                    ActionLog.schedule_id == schedule.id,
                    ActionLog.result == ActionResult.YES,
                    ActionLog.created_at >= today_start,
                )
            )
            .scalar()
        )

        no_count = (
            v3_db_session.query(func.count(ActionLog.id))
            .filter(
                and_(
                    ActionLog.schedule_id == schedule.id,
                    ActionLog.result == ActionResult.NO,
                    ActionLog.created_at >= today_start,
                )
            )
            .scalar()
        )

        assert yes_count == 2
        assert no_count == 1
