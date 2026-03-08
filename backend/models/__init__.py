"""
v0.3 Database Models

Oni System v0.3で使用するデータベースモデル定義
"""

import enum
import json
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 DeclarativeBase for v0.3 models."""

    pass


class UUIDMixin:
    """UUID PKを持つMixin"""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    def __init__(self, **kwargs):
        # idが渡されない場合のみ自動生成
        if "id" not in kwargs:
            self.id = str(uuid.uuid4())
        super().__init__(**kwargs)


class TimestampMixin:
    """作成日時・更新日時を持つMixin"""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )


class ScheduleState(enum.StrEnum):
    """スケジュールの状態"""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELED = "canceled"


class EventType(enum.StrEnum):
    """イベント種別"""

    PLAN = "plan"
    REMIND = "remind"
    REPORT = "report"


class ActionResult(enum.StrEnum):
    """アクション結果"""

    YES = "YES"
    NO = "NO"
    AUTO_IGNORE = "AUTO_IGNORE"
    REPORT_READ = "REPORT_READ"


class PunishmentMode(enum.StrEnum):
    """罰モード"""

    IGNORE = "ignore"
    NO = "no"
    ZAP = "zap"
    VIBE = "vibe"


class ConfigValueType(enum.StrEnum):
    """設定値の型"""

    INT = "int"
    FLOAT = "float"
    STR = "str"
    JSON = "json"
    BOOL = "bool"


class ChangeSource(enum.StrEnum):
    """設定変更ソース"""

    SLACK_COMMAND = "slack_command"
    ROLLBACK = "rollback"
    RESET = "reset"
    MIGRATION = "migration"


def serialize_report_input_value(
    ui_date: str,
    ui_time: str,
    updated_at: str | datetime | None = None,
) -> str:
    """Serialize report UI values for schedules.input_value."""
    ui_date_value = str(ui_date).strip()
    ui_time_value = str(ui_time).strip()

    if isinstance(updated_at, datetime):
        updated_at_value = updated_at.isoformat(timespec="seconds")
    elif isinstance(updated_at, str) and updated_at.strip():
        updated_at_value = updated_at.strip()
    else:
        updated_at_value = datetime.now().isoformat(timespec="seconds")

    payload = {
        "ui_date": ui_date_value,
        "ui_time": ui_time_value,
        "updated_at": updated_at_value,
    }
    return json.dumps(payload, ensure_ascii=False)


def deserialize_report_input_value(raw_value: str | None) -> dict[str, str] | None:
    """Deserialize schedules.input_value for report events."""
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None

    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    ui_date = payload.get("ui_date")
    ui_time = payload.get("ui_time")
    updated_at = payload.get("updated_at")
    if not (
        isinstance(ui_date, str)
        and ui_date.strip()
        and isinstance(ui_time, str)
        and ui_time.strip()
        and isinstance(updated_at, str)
        and updated_at.strip()
    ):
        return None

    return {
        "ui_date": ui_date.strip(),
        "ui_time": ui_time.strip(),
        "updated_at": updated_at.strip(),
    }


class Commitment(Base, UUIDMixin, TimestampMixin):
    """コミットメント（ユーザーの毎日の予定）"""

    __tablename__ = "commitments"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    time: Mapped[str] = mapped_column(String(8), nullable=False)  # HH:MM:SS
    task: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Schedule(Base, UUIDMixin, TimestampMixin):
    """全ての実行予定を管理するテーブル"""

    __tablename__ = "schedules"

    commitment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("commitments.id"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(SQLEnum(EventType), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    state: Mapped[str] = mapped_column(
        SQLEnum(ScheduleState), nullable=False, default=ScheduleState.PENDING
    )
    thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    yes_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(upper(event_type) = 'REMIND' AND commitment_id IS NOT NULL) OR "
            "(upper(event_type) IN ('PLAN', 'REPORT') AND commitment_id IS NULL)",
            name="ck_schedules_event_commitment_id",
        ),
    )

    def set_report_input_value(
        self,
        ui_date: str,
        ui_time: str,
        updated_at: str | datetime | None = None,
    ) -> None:
        """Set report UI inputs into schedules.input_value JSON."""
        self.input_value = serialize_report_input_value(
            ui_date=ui_date,
            ui_time=ui_time,
            updated_at=updated_at,
        )

    def get_report_input_value(self) -> dict[str, str] | None:
        """Get report UI inputs from schedules.input_value JSON."""
        return deserialize_report_input_value(self.input_value)


class ActionLog(Base, UUIDMixin):
    """行動ログを記録するテーブル"""

    __tablename__ = "action_logs"

    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    result: Mapped[str] = mapped_column(SQLEnum(ActionResult), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())


class Punishment(Base, UUIDMixin):
    """罰実行記録を管理するテーブル"""

    __tablename__ = "punishments"

    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(SQLEnum(PunishmentMode), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    # 制約: UNIQUE(schedule_id, mode, count)
    __table_args__ = (
        UniqueConstraint("schedule_id", "mode", "count", name="uix_schedule_mode_count"),
    )


class Configuration(Base, UUIDMixin, TimestampMixin):
    """ユーザーが変更可能な設定値を管理するテーブル"""

    __tablename__ = "configurations"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(SQLEnum(ConfigValueType), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_value: Mapped[float | None] = mapped_column(Integer, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Integer, nullable=True)
    valid_values: Mapped[str | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 制約: UNIQUE(user_id, key)
    __table_args__ = (UniqueConstraint("user_id", "key", name="uix_user_key"),)


class ConfigAuditLog(Base, UUIDMixin):
    """設定変更の監査ログを記録するテーブル"""

    __tablename__ = "config_audit_log"

    config_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(), index=True
    )
    change_source: Mapped[str] = mapped_column(SQLEnum(ChangeSource), nullable=False)


class CalorieRecord(Base, UUIDMixin):
    """カロリー解析結果の記録"""

    __tablename__ = "calorie_records"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    food_name: Mapped[str] = mapped_column(Text, nullable=False)
    calorie: Mapped[int] = mapped_column(Integer, nullable=False)
    llm_raw_response_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        CheckConstraint("calorie >= 0", name="ck_calorie_records_calorie_non_negative"),
        CheckConstraint(
            "lower(provider) in ('openai', 'gemini')",
            name="ck_calorie_records_provider",
        ),
    )


class ReportDelivery(Base, UUIDMixin, TimestampMixin):
    """レポート投稿履歴"""

    __tablename__ = "report_deliveries"

    schedule_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("schedules.id"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    markdown_table: Mapped[str] = mapped_column(Text, nullable=False)
    llm_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("lower(report_type) in ('weekly', 'monthly')", name="ck_report_deliveries_type"),
        UniqueConstraint(
            "user_id",
            "report_type",
            "period_start",
            "period_end",
            name="uix_report_deliveries_user_period",
        ),
    )
