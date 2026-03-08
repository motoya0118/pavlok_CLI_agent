"""Shared helpers for report input visibility/prefill in plan modal."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.models import (
    Configuration,
    EventType,
    ReportDelivery,
    Schedule,
    ScheduleState,
    deserialize_report_input_value,
)

DEFAULT_REPORT_WEEKDAY = "sat"
DEFAULT_REPORT_TIME = "07:00"
VALID_REPORT_WEEKDAYS = {"sun", "mon", "tue", "wed", "thu", "fri", "sat"}
WEEKDAY_TO_TOKEN = {
    0: "mon",
    1: "tue",
    2: "wed",
    3: "thu",
    4: "fri",
    5: "sat",
    6: "sun",
}


def _weekday_token(value: date) -> str:
    return WEEKDAY_TO_TOKEN.get(value.weekday(), "sat")


def _normalize_report_weekday(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in VALID_REPORT_WEEKDAYS:
        return value
    return DEFAULT_REPORT_WEEKDAY


def _normalize_report_time(raw: Any) -> str:
    value = str(raw or "").strip()
    if len(value) == 5 and ":" in value:
        hh, mm = value.split(":", 1)
        if hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
            return f"{hh.zfill(2)}:{mm.zfill(2)}"
    if len(value) == 8 and value.count(":") == 2:
        hh, mm, ss = value.split(":")
        if (
            hh.isdigit()
            and mm.isdigit()
            and ss.isdigit()
            and 0 <= int(hh) <= 23
            and 0 <= int(mm) <= 59
            and 0 <= int(ss) <= 59
        ):
            return f"{hh.zfill(2)}:{mm.zfill(2)}"
    return DEFAULT_REPORT_TIME


def _load_report_config(session: Session, user_id: str) -> tuple[str, str]:
    if not user_id:
        return DEFAULT_REPORT_WEEKDAY, DEFAULT_REPORT_TIME

    rows = (
        session.query(Configuration.key, Configuration.value)
        .filter(
            Configuration.user_id == user_id,
            Configuration.key.in_(["REPORT_WEEKDAY", "REPORT_TIME"]),
        )
        .all()
    )
    row_map = {str(key): str(value) for key, value in rows}
    weekday = _normalize_report_weekday(row_map.get("REPORT_WEEKDAY", DEFAULT_REPORT_WEEKDAY))
    time_text = _normalize_report_time(row_map.get("REPORT_TIME", DEFAULT_REPORT_TIME))
    return weekday, time_text


def _is_monthly_active(session: Session, user_id: str, today: date) -> bool:
    if not user_id:
        return False

    this_month_start = today.replace(day=1)
    prev_month_end = this_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    sent_row = (
        session.query(ReportDelivery.id)
        .filter(
            ReportDelivery.user_id == user_id,
            ReportDelivery.report_type == "monthly",
            ReportDelivery.period_start == prev_month_start,
            ReportDelivery.period_end == prev_month_end,
            ReportDelivery.posted_at.isnot(None),
        )
        .first()
    )
    return sent_row is None


def _resolve_default_date(config_weekday: str, today: date) -> str:
    tomorrow = today + timedelta(days=1)
    if _weekday_token(today) == config_weekday:
        return "today"
    if _weekday_token(tomorrow) == config_weekday:
        return "tomorrow"
    return "today"


def _pending_report_prefill(session: Session, user_id: str, today: date) -> tuple[str, str] | None:
    if not user_id:
        return None

    pending = (
        session.query(Schedule)
        .filter(
            Schedule.user_id == user_id,
            Schedule.event_type == EventType.REPORT,
            Schedule.state == ScheduleState.PENDING,
        )
        .order_by(Schedule.updated_at.desc(), Schedule.created_at.desc())
        .first()
    )
    if not pending:
        return None

    parsed = deserialize_report_input_value(getattr(pending, "input_value", None))
    if parsed:
        date_value = str(parsed.get("ui_date", "")).strip()
        if date_value not in {"today", "tomorrow"}:
            date_value = "today"
        time_value = _normalize_report_time(parsed.get("ui_time", ""))
        return date_value, time_value

    run_at = getattr(pending, "run_at", None)
    if isinstance(run_at, datetime):
        date_value = "tomorrow" if run_at.date() > today else "today"
        return date_value, run_at.strftime("%H:%M")

    return None


def build_report_plan_input_context(
    session: Session,
    user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Build report input visibility + prefill context for plan modal.

    Returns:
        {
            "show": bool,
            "date": "today"|"tomorrow",
            "time": "HH:MM",
            "weekday_match": bool,
            "monthly_active": bool,
        }
    """
    current = now or datetime.now()
    today = current.date()

    config_weekday, config_time = _load_report_config(session, user_id)
    weekday_match = _weekday_token(today) == config_weekday
    monthly_active = _is_monthly_active(session, user_id, today)
    should_show = weekday_match or monthly_active

    date_value = _resolve_default_date(config_weekday, today)
    time_value = config_time
    pending_prefill = _pending_report_prefill(session, user_id, today)
    if pending_prefill:
        date_value, time_value = pending_prefill

    return {
        "show": should_show,
        "date": date_value,
        "time": time_value,
        "weekday_match": weekday_match,
        "monthly_active": monthly_active,
    }
