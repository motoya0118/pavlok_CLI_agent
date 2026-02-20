#!/usr/bin/env python3
# ruff: noqa: E402
"""
Update schedule.comment / yes_comment / no_comment in bulk.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import EventType, Schedule

load_dotenv()


def _read_updates_json() -> str:
    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        if arg == "-":
            return sys.stdin.read()
        return arg
    return os.getenv("COMMENT_UPDATES_JSON", "[]")


def _parse_updates(raw: str) -> list[dict[str, str]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if isinstance(payload, dict):
        payload = payload.get("updates", [])
    if not isinstance(payload, list):
        raise ValueError("updates input must be JSON array or object with 'updates'")

    normalized = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each update must be object")
        schedule_id = str(item.get("schedule_id", "")).strip()
        if not schedule_id:
            raise ValueError("schedule_id is required")
        normalized.append(
            {
                "schedule_id": schedule_id,
                "comment": item.get("comment"),
                "yes_comment": item.get("yes_comment"),
                "no_comment": item.get("no_comment"),
            }
        )
    return normalized


def main() -> None:
    try:
        updates = _parse_updates(_read_updates_json())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if not updates:
        print(json.dumps({"updated": 0, "requested": 0}))
        return

    update_map = {item["schedule_id"]: item for item in updates}
    target_ids = list(update_map.keys())

    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///oni.db"))
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        rows = (
            session.query(Schedule)
            .filter(
                Schedule.id.in_(target_ids),
                Schedule.event_type == EventType.REMIND,
            )
            .all()
        )

        updated = 0
        for row in rows:
            item = update_map.get(row.id)
            if not item:
                continue

            changed = False
            for field in ("comment", "yes_comment", "no_comment"):
                value = item.get(field)
                if value is None:
                    continue
                text = str(value).strip()
                if text == "":
                    continue
                if getattr(row, field) != text:
                    setattr(row, field, text)
                    changed = True

            if changed:
                updated += 1

        session.commit()
        print(json.dumps({"updated": updated, "requested": len(updates)}))
    finally:
        session.close()


if __name__ == "__main__":
    main()
