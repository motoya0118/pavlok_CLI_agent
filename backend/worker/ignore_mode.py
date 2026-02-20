"""Ignore Mode Detection Module"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session


def _safe_int(value: object, default: int) -> int:
    """Convert config-like value to int with fallback."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def calculate_ignore_punishment(ignore_time: int) -> dict[str, Any]:
    """
    ignore回数から罰を計算する

    Args:
        ignore_time: ignore回数（IGNORE_INTERVAL単位）

    Returns:
        {"type": str, "value": int}
    """
    if ignore_time <= 1:
        return {"type": "vibe", "value": 100}

    # 2回目以降はzap: min(35 + 10 * (ignore_time - 2), 100)
    zap_value = min(35 + 10 * (ignore_time - 2), 100)
    return {"type": "zap", "value": zap_value}


def _send_punishment(stimulus_type: str, value: int, reason: str = "") -> bool:
    """Send Pavlok stimulus. Return True on success."""
    try:
        from backend.pavlok_lib import PavlokClient

        client = PavlokClient()
        result = client.stimulate(
            stimulus_type=stimulus_type,
            value=value,
            reason=reason,
        )
    except Exception:
        return False

    return bool(isinstance(result, dict) and result.get("success"))


def _mark_auto_ignore_once(session: Session, schedule, now: datetime) -> None:
    """Mark schedule canceled and append AUTO_IGNORE action once."""
    from backend.models import ActionLog, ActionResult, ScheduleState

    schedule.state = ScheduleState.CANCELED
    schedule.updated_at = now

    existing_auto_ignore = (
        session.query(ActionLog.id)
        .filter(
            ActionLog.schedule_id == schedule.id,
            ActionLog.result == ActionResult.AUTO_IGNORE,
        )
        .first()
    )
    if not existing_auto_ignore:
        session.add(
            ActionLog(
                schedule_id=schedule.id,
                result=ActionResult.AUTO_IGNORE,
            )
        )


def _count_today_zap_executions(session: Session, user_id: str) -> int:
    """Count today's zap executions from punishment records for the user."""
    from sqlalchemy import and_, or_

    from backend.models import Punishment, PunishmentMode, Schedule

    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(day=day_start.day) + (day_start - day_start)  # keep type
    day_end = day_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    return (
        session.query(Punishment.id)
        .join(Schedule, Punishment.schedule_id == Schedule.id)
        .filter(
            Schedule.user_id == user_id,
            Punishment.created_at >= day_start,
            Punishment.created_at <= day_end,
            or_(
                Punishment.mode == PunishmentMode.NO,
                and_(
                    Punishment.mode == PunishmentMode.IGNORE,
                    Punishment.count >= 2,
                ),
            ),
        )
        .count()
    )


def detect_ignore_mode(session: Session, schedule) -> dict[str, Any]:
    """
    ignore_modeを検知する

    Args:
        session: DBセッション
        schedule: 対象スケジュール

    Returns:
        {"detected": bool, "ignore_time": int}
    """
    from backend.models import Punishment, PunishmentMode, ScheduleState
    from backend.worker.config_cache import get_config

    now = datetime.now()

    # Use processing start time as ignore timer origin.
    reference_time = schedule.run_at
    if getattr(schedule, "state", None) == ScheduleState.PROCESSING and isinstance(
        getattr(schedule, "updated_at", None), datetime
    ):
        reference_time = schedule.updated_at

    if isinstance(reference_time, datetime):
        elapsed_seconds = int((now - reference_time).total_seconds())
    else:
        elapsed_seconds = int(now.timestamp() - reference_time)

    config_interval = _safe_int(get_config("IGNORE_INTERVAL", 900, session=session), 900)
    if config_interval <= 0:
        config_interval = 900

    if elapsed_seconds < config_interval:
        return {"detected": False, "ignore_time": 0}

    ignore_time = elapsed_seconds // config_interval

    existing_same_trigger = (
        session.query(Punishment.id)
        .filter(
            Punishment.schedule_id == schedule.id,
            Punishment.mode == PunishmentMode.IGNORE,
            Punishment.count == ignore_time,
        )
        .first()
    )
    if existing_same_trigger:
        return {"detected": True, "ignore_time": ignore_time}

    ignore_max_retry = _safe_int(
        get_config("IGNORE_MAX_RETRY", 5, session=session),
        5,
    )
    if ignore_max_retry <= 0:
        ignore_max_retry = 1

    if ignore_time > ignore_max_retry:
        _mark_auto_ignore_once(session, schedule, now)
        session.commit()
        return {"detected": True, "ignore_time": ignore_time}

    punishment_data = calculate_ignore_punishment(ignore_time)
    stimulus_type = str(punishment_data["type"])
    value = int(punishment_data["value"])
    reason_text = ""
    try:
        from backend.pavlok_lib import build_reason_for_schedule

        reason_text = build_reason_for_schedule(session, schedule)
    except Exception:
        reason_text = ""

    if stimulus_type == "zap":
        zap_limit = _safe_int(
            get_config("LIMIT_DAY_PAVLOK_COUNTS", 100, session=session),
            100,
        )
        if zap_limit <= 0:
            zap_limit = 1
        zap_count = _count_today_zap_executions(session, str(schedule.user_id))
        if zap_count >= zap_limit:
            return {"detected": True, "ignore_time": ignore_time}

    # If the Pavlok call fails, do not record the trigger index so it can retry.
    sent = _send_punishment(
        stimulus_type=stimulus_type,
        value=value,
        reason=reason_text,
    )
    if not sent:
        return {"detected": False, "ignore_time": ignore_time}

    session.add(
        Punishment(
            schedule_id=schedule.id,
            mode=PunishmentMode.IGNORE,
            count=ignore_time,
        )
    )

    if stimulus_type == "zap" and value >= 100:
        _mark_auto_ignore_once(session, schedule, now)

    session.commit()
    return {"detected": True, "ignore_time": ignore_time}
