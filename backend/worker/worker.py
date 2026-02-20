"""Punishment Worker Main Module"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.worker.config_cache import get_config, invalidate_config_cache

logger = logging.getLogger(__name__)

# Load local .env if present (without overriding real environment variables).
load_dotenv()


class PunishmentWorker:
    """鬼コーチPunishment Worker"""

    def __init__(self, session: Session):
        """
        初期化

        Args:
            session: DBセッション
        """
        self.session = session

    @staticmethod
    def _as_bool(value: object) -> bool:
        """Normalize config value to bool safely."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    def _resolve_bootstrap_user_id(self) -> str | None:
        """
        Resolve user_id for initial plan bootstrap.
        Rule:
        - Only users who have active commitments are eligible.
        """
        from backend.models import Commitment

        commitment_row = (
            self.session.query(Commitment.user_id)
            .filter(Commitment.active.is_(True))
            .order_by(Commitment.updated_at.desc())
            .first()
        )
        if commitment_row and commitment_row[0]:
            return str(commitment_row[0])

        return None

    async def ensure_initial_plan_schedule(self) -> str | None:
        """
        Bootstrap first plan schedule if no pending/processing records exist.

        Returns:
            Created schedule id if inserted, otherwise None.
        """
        from backend.models import EventType, Schedule, ScheduleState

        in_flight_count = (
            self.session.query(Schedule)
            .filter(Schedule.state.in_([ScheduleState.PENDING, ScheduleState.PROCESSING]))
            .count()
        )
        if in_flight_count > 0:
            logger.info(
                "Bootstrap skipped: pending+processing schedules exist (%s)",
                in_flight_count,
            )
            return None

        user_id = self._resolve_bootstrap_user_id()
        if not user_id:
            logger.warning(
                "Bootstrap skipped: no active commitments found. "
                "Run /base_commit to create active commitments first."
            )
            return None

        now = datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        existing_today = (
            self.session.query(Schedule.id)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.PLAN,
                Schedule.run_at >= day_start,
                Schedule.run_at < day_end,
            )
            .first()
        )
        if existing_today:
            logger.info(
                "Bootstrap skipped: today's plan already exists for user_id=%s schedule_id=%s",
                user_id,
                existing_today[0],
            )
            return None

        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=now,
            state=ScheduleState.PENDING,
            retry_count=0,
        )
        self.session.add(schedule)
        self.session.commit()
        logger.info(
            "Bootstrap inserted initial plan schedule: schedule_id=%s user_id=%s",
            schedule.id,
            user_id,
        )
        return str(schedule.id)

    async def fetch_pending_schedules(self) -> list:
        """
        処理待ちスケジュールを取得する

        Returns:
            pendingかつrun_at <= nowのスケジュールリスト
        """
        from backend.models import Schedule, ScheduleState

        now = datetime.now()
        schedules = (
            self.session.query(Schedule)
            .filter(Schedule.state == ScheduleState.PENDING, Schedule.run_at <= now)
            .all()
        )

        return schedules

    async def fetch_processing_plan_schedules(self) -> list:
        """
        監視対象候補のprocessing scheduleを取得する

        Returns:
            processingかつ(plan/remind)かつrun_at <= nowのスケジュールリスト
        """
        from backend.models import EventType, Schedule, ScheduleState

        now = datetime.now()
        schedules = (
            self.session.query(Schedule)
            .filter(
                Schedule.state == ScheduleState.PROCESSING,
                Schedule.event_type.in_([EventType.PLAN, EventType.REMIND]),
                Schedule.run_at <= now,
            )
            .all()
        )
        return schedules

    @staticmethod
    def _recency_key(schedule) -> tuple:
        """Compare schedules by most recently updated processing context."""
        updated = schedule.updated_at or datetime.min
        run_at = schedule.run_at or datetime.min
        created = schedule.created_at or datetime.min
        return (updated, run_at, created, str(schedule.id))

    def select_latest_processing_per_user(self, schedules: list) -> list:
        """
        ユーザーごとに最新processingレコードを1件に絞る
        """
        latest_by_user = {}
        for schedule in schedules:
            user_id = str(schedule.user_id)
            current = latest_by_user.get(user_id)
            if current is None or self._recency_key(schedule) > self._recency_key(current):
                latest_by_user[user_id] = schedule
        return list(latest_by_user.values())

    def cancel_stale_processing_plans(self, user_id: str, keep_schedule_id: str) -> int:
        """
        同一ユーザーの古いprocessing planをcanceledに更新する

        Returns:
            更新件数
        """
        from backend.models import EventType, Schedule, ScheduleState

        stale_rows = (
            self.session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.PLAN,
                Schedule.state == ScheduleState.PROCESSING,
                Schedule.id != keep_schedule_id,
            )
            .all()
        )
        for stale in stale_rows:
            stale.state = ScheduleState.CANCELED

        if stale_rows:
            self.session.commit()
            logger.info(
                "Canceled stale processing plans: user_id=%s count=%s keep_schedule_id=%s",
                user_id,
                len(stale_rows),
                keep_schedule_id,
            )
        return len(stale_rows)

    async def execute_script(self, script_name: str, schedule) -> None:
        """
        スクリプトを実行する

        Args:
            script_name: スクリプト名（plan.py, remind.py）
            schedule: 対象スケジュール
        """
        import subprocess

        repo_root = Path(__file__).resolve().parents[2]
        script_path = repo_root / "scripts" / script_name

        env = os.environ.copy()
        env["SCHEDULE_ID"] = str(schedule.id)

        if not script_path.is_file():
            raise Exception(f"Script file not found: {script_path}")

        result = subprocess.run(
            [sys.executable, str(script_path)], env=env, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise Exception(f"Script execution failed: {result.stderr}")

    async def process_schedule(self, schedule) -> None:
        """
        スケジュールを処理する

        Args:
            schedule: 対象スケジュール
        """
        from backend.models import EventType, ScheduleState

        try:
            if schedule.event_type == EventType.PLAN:
                self.cancel_stale_processing_plans(
                    user_id=str(schedule.user_id),
                    keep_schedule_id=str(schedule.id),
                )

            # Mark as processing while script is running / waiting for user response.
            schedule.state = ScheduleState.PROCESSING
            self.session.commit()

            # Execute script based on event_type
            if schedule.event_type == EventType.PLAN:
                await self.execute_script("plan.py", schedule)
            elif schedule.event_type == EventType.REMIND:
                await self.execute_script("remind.py", schedule)

            # Keep processing until user responds from Slack (YES/NO).
            # This applies to both plan and remind.
            self.session.commit()

        except Exception as e:
            logger.error(f"Error processing schedule {schedule.id}: {e}")
            schedule.state = ScheduleState.FAILED
            schedule.retry_count += 1

            # Retry if under limit
            max_retry = 3
            if schedule.retry_count < max_retry:
                from datetime import timedelta

                from backend.worker.config_cache import get_config

                retry_delay = get_config("RETRY_DELAY", 5, session=self.session)
                schedule.run_at = datetime.now() + timedelta(minutes=retry_delay)
                schedule.state = ScheduleState.PENDING
            self.session.commit()

    async def monitor_processing_schedules(self) -> None:
        """
        processing状態のplan/remindを監視してignoreを検知する
        """
        from backend.worker.ignore_mode import detect_ignore_mode

        candidates = await self.fetch_processing_plan_schedules()
        targets = self.select_latest_processing_per_user(candidates)
        logger.info(
            "Monitoring %s processing schedules (candidates=%s)",
            len(targets),
            len(candidates),
        )

        for schedule in targets:
            try:
                ignore_result = detect_ignore_mode(self.session, schedule)
                if ignore_result["detected"]:
                    logger.info(
                        "ignore_mode detected: schedule_id=%s ignore_time=%s",
                        schedule.id,
                        ignore_result["ignore_time"],
                    )
            except Exception as e:
                self.session.rollback()
                logger.error(
                    "Processing monitor error: schedule_id=%s error=%s",
                    schedule.id,
                    e,
                )

    async def run_once(self) -> None:
        """
        1回分の処理を実行する
        """
        # SYSTEM_PAUSED is operationally critical; always refresh it per cycle.
        invalidate_config_cache("SYSTEM_PAUSED")
        system_paused = get_config("SYSTEM_PAUSED", False, session=self.session)
        if self._as_bool(system_paused):
            logger.info("SYSTEM_PAUSED=true, skipping worker cycle")
            return

        try:
            await self.ensure_initial_plan_schedule()
        except Exception as e:
            self.session.rollback()
            logger.error(f"Bootstrap error: {e}")

        schedules = await self.fetch_pending_schedules()
        logger.info(f"Processing {len(schedules)} schedules")

        for schedule in schedules:
            await self.process_schedule(schedule)

        await self.monitor_processing_schedules()

    async def run(self) -> None:
        """
        無限ループで処理を実行する
        """
        while True:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Worker error: {e}")
            # Wait 1 minute
            await asyncio.sleep(60)


async def main() -> None:
    """
    メインエントリーポイント
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create database session
    database_url = os.getenv("DATABASE_URL", "sqlite:///oni.db")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        worker = PunishmentWorker(session)
        await worker.run()
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
