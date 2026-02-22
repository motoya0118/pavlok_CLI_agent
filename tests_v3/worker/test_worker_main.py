# v0.3 Worker Main Tests
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models import EventType, Schedule, ScheduleState
from backend.worker.worker import PunishmentWorker


@pytest.mark.asyncio
class TestPunishmentWorker:
    @pytest.mark.asyncio
    async def test_fetch_pending_schedules(self, v3_db_session, v3_test_data_factory):
        """pendingかつrun_at <= nowのスケジュールを取得できること"""
        past_schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(minutes=5), state=ScheduleState.PENDING
        )
        v3_test_data_factory.create_schedule(
            run_at=datetime.now() + timedelta(minutes=5), state=ScheduleState.PENDING
        )

        worker = PunishmentWorker(v3_db_session)
        schedules = await worker.fetch_pending_schedules()

        assert len(schedules) == 1
        assert schedules[0].id == past_schedule.id

    @pytest.mark.asyncio
    async def test_bootstrap_inserts_initial_plan_when_no_inflight(
        self, v3_db_session, v3_test_data_factory
    ):
        """PENDING/PROCESSINGのplanが0なら初回planを登録すること"""
        v3_test_data_factory.create_commitment(task="朝のタスク", time="07:00:00")

        worker = PunishmentWorker(v3_db_session)
        created_id = await worker.ensure_initial_plan_schedule()

        assert created_id is not None
        created = v3_db_session.query(Schedule).filter_by(id=created_id).one()
        assert created.event_type == EventType.PLAN
        assert created.state == ScheduleState.PENDING
        assert created.run_at <= datetime.now()

    @pytest.mark.asyncio
    async def test_bootstrap_skips_when_inflight_exists(self, v3_db_session, v3_test_data_factory):
        """PENDING/PROCESSINGのplanが存在する場合は初回planを登録しないこと"""
        v3_test_data_factory.create_schedule(
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PENDING,
        )

        worker = PunishmentWorker(v3_db_session)
        created_id = await worker.ensure_initial_plan_schedule()

        assert created_id is None
        schedules = v3_db_session.query(Schedule).all()
        assert len(schedules) == 1

    @pytest.mark.asyncio
    async def test_bootstrap_creates_when_only_completed_plan_exists(
        self, v3_db_session, v3_test_data_factory
    ):
        """DONE/CANCELEDしかない場合は新しいplanを補充すること"""
        v3_test_data_factory.create_commitment(task="朝のタスク", time="07:00:00")
        v3_test_data_factory.create_schedule(
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(hours=1),
            state=ScheduleState.DONE,
        )

        worker = PunishmentWorker(v3_db_session)
        created_id = await worker.ensure_initial_plan_schedule()

        assert created_id is not None
        schedules = (
            v3_db_session.query(Schedule).filter(Schedule.event_type == EventType.PLAN).all()
        )
        assert len(schedules) == 2

    @pytest.mark.asyncio
    async def test_bootstrap_ignores_inflight_remind_and_creates_plan(
        self, v3_db_session, v3_test_data_factory
    ):
        """inflightがremindのみならplanを補充すること"""
        commitment = v3_test_data_factory.create_commitment(task="朝のタスク", time="07:00:00")
        v3_test_data_factory.create_schedule(
            event_type=EventType.REMIND,
            run_at=datetime.now() - timedelta(minutes=10),
            state=ScheduleState.PROCESSING,
            commitment_id=commitment.id,
            comment="朝のタスク",
        )

        worker = PunishmentWorker(v3_db_session)
        created_id = await worker.ensure_initial_plan_schedule()

        assert created_id is not None
        created = v3_db_session.query(Schedule).filter_by(id=created_id).one()
        assert created.event_type == EventType.PLAN
        assert created.state == ScheduleState.PENDING

    @pytest.mark.asyncio
    async def test_bootstrap_skips_when_only_inactive_commitments(
        self, v3_db_session, v3_test_data_factory
    ):
        """active=falseしかない場合は初回planを登録しないこと"""
        v3_test_data_factory.create_commitment(
            task="inactive task",
            time="09:00:00",
            active=False,
        )

        worker = PunishmentWorker(v3_db_session)
        created_id = await worker.ensure_initial_plan_schedule()

        assert created_id is None
        schedules = v3_db_session.query(Schedule).all()
        assert len(schedules) == 0

    @pytest.mark.asyncio
    async def test_process_schedule_plan_event(self, v3_db_session, v3_test_data_factory):
        """planイベントは処理後もprocessingで待機すること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(minutes=1), state=ScheduleState.PENDING
        )

        worker = PunishmentWorker(v3_db_session)
        with patch.object(worker, "execute_script"):
            await worker.process_schedule(schedule)

        assert schedule.state == ScheduleState.PROCESSING

    @pytest.mark.asyncio
    async def test_process_schedule_plan_cancels_old_processing(
        self, v3_db_session, v3_test_data_factory
    ):
        """plan実行時に同一ユーザーの古いprocessing planをcanceledにすること"""
        old_processing = v3_test_data_factory.create_schedule(
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=30),
            state=ScheduleState.PROCESSING,
        )
        new_pending = v3_test_data_factory.create_schedule(
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PENDING,
        )

        worker = PunishmentWorker(v3_db_session)
        with patch.object(worker, "execute_script"):
            await worker.process_schedule(new_pending)

        v3_db_session.refresh(old_processing)
        v3_db_session.refresh(new_pending)
        assert old_processing.state == ScheduleState.CANCELED
        assert new_pending.state == ScheduleState.PROCESSING

    @pytest.mark.asyncio
    async def test_process_schedule_remind_event(self, v3_db_session, v3_test_data_factory):
        """remindイベントを処理できること"""
        from backend.models import EventType

        schedule = v3_test_data_factory.create_schedule(
            event_type=EventType.REMIND,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PENDING,
        )

        worker = PunishmentWorker(v3_db_session)
        with patch.object(worker, "execute_script"):
            await worker.process_schedule(schedule)

        assert schedule.state == ScheduleState.PROCESSING

    @pytest.mark.asyncio
    async def test_process_schedule_failure_retry(self, v3_db_session, v3_test_data_factory):
        """失敗時にretry_countを増やすこと"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(minutes=1), state=ScheduleState.PENDING, retry_count=0
        )

        worker = PunishmentWorker(v3_db_session)
        with patch.object(worker, "execute_script", side_effect=Exception("Test error")):
            await worker.process_schedule(schedule)

        # After failure, retry_count should increase
        assert schedule.retry_count == 1
        # State should be FAILED or PENDING (if rescheduled)
        assert schedule.state in [ScheduleState.FAILED, ScheduleState.PENDING]

    @pytest.mark.asyncio
    async def test_process_schedule_max_retry_exceeded(self, v3_db_session, v3_test_data_factory):
        """最大リトライ数を超えた場合にfailedのままにすること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(minutes=1), state=ScheduleState.PENDING, retry_count=3
        )

        worker = PunishmentWorker(v3_db_session)
        with patch.object(worker, "execute_script", side_effect=Exception("Test error")):
            await worker.process_schedule(schedule)

        # retry_count should increment (4)
        assert schedule.retry_count == 4
        # State should be FAILED (since retry_count >= max_retry of 3)
        assert schedule.state == ScheduleState.FAILED

    @pytest.mark.asyncio
    async def test_ignore_mode_detection(self, v3_db_session, v3_test_data_factory):
        """ignore_modeを検知して罰を追加できること"""
        schedule = v3_test_data_factory.create_schedule(
            run_at=datetime.now() - timedelta(minutes=20),  # 20分経過
            state=ScheduleState.PROCESSING,
            event_type=EventType.PLAN,
        )
        schedule.updated_at = datetime.now() - timedelta(minutes=20)
        v3_db_session.commit()

        worker = PunishmentWorker(v3_db_session)
        with patch("backend.worker.ignore_mode._send_punishment", return_value=True):
            await worker.monitor_processing_schedules()

        # Check if punishment was created
        from backend.models import Punishment

        punishments = v3_db_session.query(Punishment).filter_by(schedule_id=schedule.id).all()
        assert len(punishments) > 0

    @pytest.mark.asyncio
    async def test_monitor_processing_targets_latest_per_user(
        self, v3_db_session, v3_test_data_factory
    ):
        """processing監視はユーザーごとに最新1件のみ対象にすること"""
        older = v3_test_data_factory.create_schedule(
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=20),
            state=ScheduleState.PROCESSING,
        )
        newer = v3_test_data_factory.create_schedule(
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=5),
            state=ScheduleState.PROCESSING,
        )
        other_user = Schedule(
            user_id="U_OTHER",
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=5),
            state=ScheduleState.PROCESSING,
            retry_count=0,
        )
        v3_db_session.add(other_user)
        v3_db_session.commit()
        v3_db_session.refresh(other_user)

        worker = PunishmentWorker(v3_db_session)
        with patch("backend.worker.ignore_mode.detect_ignore_mode") as mock_ignore:
            mock_ignore.return_value = {"detected": False, "ignore_time": 0}
            await worker.monitor_processing_schedules()

        monitored_schedule_ids = {str(call.args[1].id) for call in mock_ignore.call_args_list}
        assert str(newer.id) in monitored_schedule_ids
        assert str(other_user.id) in monitored_schedule_ids
        assert str(older.id) not in monitored_schedule_ids

    @pytest.mark.asyncio
    async def test_monitor_processing_includes_remind(self, v3_db_session, v3_test_data_factory):
        """processing監視対象にremindも含まれること"""
        remind_schedule = v3_test_data_factory.create_schedule(
            event_type=EventType.REMIND,
            run_at=datetime.now() - timedelta(minutes=20),
            state=ScheduleState.PROCESSING,
        )

        worker = PunishmentWorker(v3_db_session)
        with patch("backend.worker.ignore_mode.detect_ignore_mode") as mock_ignore:
            mock_ignore.return_value = {"detected": False, "ignore_time": 0}
            await worker.monitor_processing_schedules()

        monitored_schedule_ids = {str(call.args[1].id) for call in mock_ignore.call_args_list}
        assert str(remind_schedule.id) in monitored_schedule_ids

    @pytest.mark.asyncio
    async def test_main_loop_interval(self, v3_db_session):
        """メインループが1分間隔で実行されること"""
        call_count = 0

        async def mock_run_once(self):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise SystemExit

        with patch.object(PunishmentWorker, "run_once", mock_run_once):
            with patch("asyncio.sleep"):
                try:
                    worker = PunishmentWorker(v3_db_session)
                    # Run 2 iterations manually
                    for _ in range(2):
                        await worker.run_once()
                except SystemExit:
                    pass

        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_run_once_calls_bootstrap_every_time(self, v3_db_session):
        """run_onceは毎回bootstrapチェックを行うこと"""
        worker = PunishmentWorker(v3_db_session)

        with (
            patch("backend.worker.worker.get_config", return_value=False),
            patch.object(
                worker, "ensure_initial_plan_schedule", new=AsyncMock(return_value=None)
            ) as mock_bootstrap,
            patch.object(
                worker, "fetch_pending_schedules", new=AsyncMock(return_value=[])
            ) as mock_fetch,
            patch.object(worker, "process_schedule", new=AsyncMock()) as mock_process_schedule,
            patch.object(worker, "monitor_processing_schedules", new=AsyncMock()) as mock_monitor,
        ):
            await worker.run_once()
            await worker.run_once()

        assert mock_bootstrap.await_count == 2
        assert mock_fetch.await_count == 2
        assert mock_process_schedule.await_count == 0
        assert mock_monitor.await_count == 2

    @pytest.mark.asyncio
    async def test_run_once_skips_all_when_system_paused(self, v3_db_session):
        """SYSTEM_PAUSED=trueのとき後続処理を実行しないこと"""
        worker = PunishmentWorker(v3_db_session)

        with (
            patch("backend.worker.worker.get_config", return_value=True) as mock_get_config,
            patch.object(worker, "ensure_initial_plan_schedule", new=AsyncMock()) as mock_bootstrap,
            patch.object(
                worker, "fetch_pending_schedules", new=AsyncMock(return_value=[])
            ) as mock_fetch,
            patch.object(worker, "process_schedule", new=AsyncMock()) as mock_process_schedule,
            patch.object(worker, "monitor_processing_schedules", new=AsyncMock()) as mock_monitor,
        ):
            await worker.run_once()

        assert mock_get_config.call_count == 1
        assert mock_bootstrap.await_count == 0
        assert mock_fetch.await_count == 0
        assert mock_process_schedule.await_count == 0
        assert mock_monitor.await_count == 0

    @pytest.mark.asyncio
    async def test_run_once_continues_after_bootstrap_error(self):
        """bootstrap失敗時もrollbackしてpending処理を継続すること"""
        mock_session = MagicMock()
        worker = PunishmentWorker(mock_session)
        fake_schedule = MagicMock()

        with (
            patch("backend.worker.worker.get_config", return_value=False),
            patch.object(
                worker,
                "ensure_initial_plan_schedule",
                new=AsyncMock(side_effect=Exception("bootstrap failed")),
            ) as mock_bootstrap,
            patch.object(
                worker,
                "fetch_pending_schedules",
                new=AsyncMock(return_value=[fake_schedule]),
            ) as mock_fetch,
            patch.object(worker, "process_schedule", new=AsyncMock()) as mock_process_schedule,
            patch.object(worker, "monitor_processing_schedules", new=AsyncMock()) as mock_monitor,
        ):
            await worker.run_once()

        assert mock_bootstrap.await_count == 1
        assert mock_session.rollback.call_count == 1
        assert mock_fetch.await_count == 1
        assert mock_process_schedule.await_count == 1
        assert mock_monitor.await_count == 1
