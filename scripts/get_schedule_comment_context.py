#!/usr/bin/env python3
# ruff: noqa: E402
"""
Fetch schedule/action context for add_comment prompt generation.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import ActionLog, EventType, Schedule

load_dotenv()


def _read_input_json() -> str:
    """Read schedule ids JSON from argv/env/stdin."""
    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        if arg == "-":
            return sys.stdin.read()
        return arg
    return os.getenv("SCHEDULE_IDS_JSON", "[]")


def _parse_schedule_ids(raw: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise ValueError("schedule ids input must be JSON array")
    return [str(v) for v in payload if str(v)]


def main() -> None:
    try:
        schedule_ids = _parse_schedule_ids(_read_input_json())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///oni.db"))
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        rows = (
            session.query(Schedule)
            .filter(
                Schedule.id.in_(schedule_ids),
                Schedule.event_type == EventType.REMIND,
            )
            .order_by(Schedule.run_at.asc())
            .all()
        )
        user_ids = sorted({row.user_id for row in rows})
        since = datetime.now() - timedelta(days=3)

        recent = []
        if user_ids:
            recent_rows = (
                session.query(ActionLog, Schedule)
                .join(Schedule, ActionLog.schedule_id == Schedule.id)
                .filter(
                    Schedule.user_id.in_(user_ids),
                    ActionLog.created_at >= since,
                )
                .order_by(ActionLog.created_at.desc())
                .limit(300)
                .all()
            )
            for action, schedule in recent_rows:
                recent.append(
                    {
                        "schedule_id": action.schedule_id,
                        "result": str(action.result),
                        "created_at": action.created_at.isoformat() if action.created_at else None,
                        "event_type": str(schedule.event_type),
                        "task_hint": schedule.comment,
                        "run_at": schedule.run_at.isoformat() if schedule.run_at else None,
                    }
                )

        result = {
            "schedule_ids": schedule_ids,
            "schedules": [
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "event_type": str(row.event_type),
                    "state": str(row.state),
                    "run_at": row.run_at.isoformat() if row.run_at else None,
                    "comment": row.comment,
                    "yes_comment": row.yes_comment,
                    "no_comment": row.no_comment,
                }
                for row in rows
            ],
            "recent_action_logs": recent,
        }
        print(json.dumps(result, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    main()
