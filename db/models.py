from sqlalchemy import Column, Date, DateTime, Enum, Integer, JSON, String, Text

from .engine import Base
from .time_utils import now_jst


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    prompt_name = Column(String, nullable=False)
    input_value = Column(String, nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    state = Column(
        Enum("pending", "running", "done", "failed", name="schedule_state_enum"),
        nullable=False,
        default="pending",
    )
    last_result = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_jst)
    updated_at = Column(DateTime, nullable=False, default=now_jst, onupdate=now_jst)


class BehaviorLog(Base):
    __tablename__ = "behavior_logs"

    id = Column(Integer, primary_key=True)
    behavior = Column(Enum("good", "bad", name="behavior_enum"), nullable=False)
    related_date = Column(Date, nullable=True)
    pavlok_log = Column(JSON, nullable=True)
    coach_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_jst)


class SlackIgnoreEvent(Base):
    __tablename__ = "slack_ignore_events"

    id = Column(Integer, primary_key=True)
    slack_message_ts = Column(String, nullable=False, unique=True)
    detected_at = Column(DateTime, nullable=False)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_jst)


class DailyPunishment(Base):
    __tablename__ = "daily_punishments"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)
    ignore_count = Column(Integer, nullable=False)
    punishment_count = Column(Integer, nullable=False)
    executed_count = Column(Integer, nullable=False, default=0)
    state = Column(
        Enum("pending", "running", "done", "failed", name="punishment_state_enum"),
        nullable=False,
        default="pending",
    )
    last_executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_jst)
    updated_at = Column(DateTime, nullable=False, default=now_jst, onupdate=now_jst)


class PavlokCount(Base):
    __tablename__ = "pavlok_counts"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)
    zap_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=now_jst)
    updated_at = Column(DateTime, nullable=False, default=now_jst, onupdate=now_jst)
