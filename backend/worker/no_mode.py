"""No Mode Detection Module"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session


def calculate_no_punishment(no_time: int) -> dict[str, Any]:
    """
    no回数から罰を計算する

    Args:
        no_time: no回数（TIMEOUT_REMIND単位）

    Returns:
        {"mode": PunishmentMode, "value": int}
    """
    from backend.models import PunishmentMode

    # zap: 35, 55, 75, 100 (max)
    zap_values = [35, 55, 75, 100]
    index = min(no_time - 1, len(zap_values) - 1)
    zap_value = zap_values[index]

    return {"mode": PunishmentMode.NO, "value": zap_value}


def detect_no_mode(session: Session, schedule) -> dict[str, Any]:
    """
    no_modeを検知する

    Args:
        session: DBセッション
        schedule: 対象スケジュール

    Returns:
        {"detected": bool, "no_time": int}
    """
    from backend.models import ActionLog, ActionResult, Punishment, PunishmentMode

    # Get TIMEOUT_REMIND (default 600 seconds = 10 minutes)
    from backend.worker.config_cache import get_config

    timeout_remind = get_config("TIMEOUT_REMIND", 600)

    now = datetime.now()
    if isinstance(schedule.run_at, datetime):
        elapsed = int((now - schedule.run_at).total_seconds())
    else:
        elapsed = int(now.timestamp() - schedule.run_at)

    # Check if TIMEOUT_REMIND has passed
    if elapsed < timeout_remind:
        return {"detected": False, "no_time": 0}

    # Check if YES response exists (clears no_mode)
    yes_log = (
        session.query(ActionLog).filter_by(schedule_id=schedule.id, result=ActionResult.YES).first()
    )

    if yes_log:
        return {"detected": False, "no_time": 0}

    # Calculate no_time
    no_time = elapsed // timeout_remind

    # Check if punishment already exists for the same trigger index.
    existing = (
        session.query(Punishment)
        .filter_by(schedule_id=schedule.id, mode=PunishmentMode.NO, count=no_time)
        .first()
    )

    if existing:
        return {"detected": True, "no_time": no_time}

    # Create new punishment
    punishment_data = calculate_no_punishment(no_time)

    punishment = Punishment(
        schedule_id=schedule.id,
        mode=punishment_data["mode"],
        count=no_time,
    )
    session.add(punishment)
    session.commit()

    return {"detected": True, "no_time": no_time}
