"""
v0.3 Behavior Logger

Actionログを記録・クエリするモジュール
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from backend.models import ActionLog, ActionResult, Schedule


class BehaviorLogger:
    """行動ログの記録・取得を行うクラス"""

    def __init__(self, db_session: Session):
        """
        Args:
            db_session: SQLAlchemy DBセッション
        """
        self.session = db_session

    def log_action(
        self, schedule_id: str, result: ActionResult, created_at: datetime | None = None
    ) -> ActionLog:
        """
        アクションを記録

        Args:
            schedule_id: 対象スケジュールID
            result: アクション結果
            created_at: 作成日時（省略時は現在時刻）

        Returns:
            ActionLog: 作成されたアクションログ
        """
        if created_at is None:
            created_at = datetime.now()

        action_log = ActionLog(schedule_id=schedule_id, result=result, created_at=created_at)

        self.session.add(action_log)
        self.session.commit()
        self.session.refresh(action_log)

        return action_log

    def get_logs_for_schedule(self, schedule_id: str) -> list[ActionLog]:
        """
        特定スケジュールのアクションログを取得

        Args:
            schedule_id: スケジュールID

        Returns:
            list[ActionLog]: アクションログリスト（古い順）
        """
        logs = (
            self.session.query(ActionLog)
            .filter_by(schedule_id=schedule_id)
            .order_by(ActionLog.created_at.asc())
            .all()
        )

        return logs

    def get_recent_logs(self, hours: int = 24, user_id: str | None = None) -> list[ActionLog]:
        """
        最近のアクションログを取得

        Args:
            hours: 取得時間（時間）
            user_id: ユーザーID（省略時は全ユーザー）

        Returns:
            list[ActionLog]: アクションログリスト（新しい順）
        """
        since = datetime.now() - timedelta(hours=hours)

        query = self.session.query(ActionLog).filter(ActionLog.created_at >= since)

        if user_id:
            query = query.join(
                Schedule,
                ActionLog.schedule_id == Schedule.id,
            ).filter(
                Schedule.user_id == user_id,
            )

        return query.order_by(ActionLog.created_at.desc()).all()

    def get_today_yes_count(self, schedule_id: str) -> int:
        """
        今日のYES回数を取得

        Args:
            schedule_id: スケジュールID

        Returns:
            int: 今日のYES回数
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        count = (
            self.session.query(func.count(ActionLog.id))
            .join(ActionLog)
            .filter(
                and_(
                    ActionLog.schedule_id == schedule_id,
                    ActionLog.result == ActionResult.YES,
                    ActionLog.created_at >= today_start,
                )
            )
            .scalar()
        )

        return count or 0

    def get_today_no_count(self, schedule_id: str) -> int:
        """
        今日のNO回数を取得

        Args:
            schedule_id: スケジュールID

        Returns:
            int: 今日のNO回数
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        count = (
            self.session.query(func.count(ActionLog.id))
            .join(ActionLog)
            .filter(
                and_(
                    ActionLog.schedule_id == schedule_id,
                    ActionLog.result == ActionResult.NO,
                    ActionLog.created_at >= today_start,
                )
            )
            .scalar()
        )

        return count or 0

    def get_auto_ignore_count(self, schedule_id: str) -> int:
        """
        AUTO_IGNORE回数を取得

        Args:
            schedule_id: スケジュールID

        Returns:
            int: AUTO_IGNORE回数
        """
        return (
            self.session.query(func.count(ActionLog.id))
            .join(ActionLog)
            .filter(
                and_(
                    ActionLog.schedule_id == schedule_id,
                    ActionLog.result == ActionResult.AUTO_IGNORE,
                )
            )
            .scalar()
            or 0
        )

    def get_daily_stats(self, schedule_id: str, date: datetime | None = None) -> dict[str, Any]:
        """
        1日の統計を取得

        Args:
            schedule_id: スケジュールID
            date: 対象日（省略時は今日）

        Returns:
            dict: 統計情報 {"yes_count": int, "no_count": int, "auto_ignore_count": int}
        """
        if date is None:
            date = datetime.now().date()

        day_start = datetime.combine(date, datetime.min.time())

        yes_count = (
            self.session.query(func.count(ActionLog.id))
            .join(ActionLog)
            .filter(
                and_(
                    ActionLog.schedule_id == schedule_id,
                    ActionLog.result == ActionResult.YES,
                    ActionLog.created_at >= day_start,
                    ActionLog.created_at < day_start + timedelta(days=1),
                )
            )
            .scalar()
            or 0
        )

        no_count = (
            self.session.query(func.count(ActionLog.id))
            .join(ActionLog)
            .filter(
                and_(
                    ActionLog.schedule_id == schedule_id,
                    ActionLog.result == ActionResult.NO,
                    ActionLog.created_at >= day_start,
                    ActionLog.created_at < day_start + timedelta(days=1),
                )
            )
            .scalar()
            or 0
        )

        auto_ignore_count = (
            self.session.query(func.count(ActionLog.id))
            .join(ActionLog)
            .filter(
                and_(
                    ActionLog.schedule_id == schedule_id,
                    ActionLog.result == ActionResult.AUTO_IGNORE,
                    ActionLog.created_at >= day_start,
                    ActionLog.created_at < day_start + timedelta(days=1),
                )
            )
            .scalar()
            or 0
        )

        return {
            "yes_count": yes_count,
            "no_count": no_count,
            "auto_ignore_count": auto_ignore_count,
        }
