import argparse
import json
import sys
from datetime import date, datetime, timedelta
from typing import Any

from db.engine import SessionLocal
from db.models import BehaviorLog, now_jst


def parse_pavlok_log(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None

    raw = raw.strip()
    if raw == "-":
        raw = sys.stdin.read().strip()
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON for pavlok_log: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise SystemExit("pavlok_log must be a JSON object.")

    return data


def parse_related_date(value: str | None) -> date | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise SystemExit("related_date must be YYYY-MM-DD or YYYYMMDD.")


def write_log(
    behavior: str,
    related_date: date | None,
    pavlok_log: dict | None,
    coach_comment: str | None,
) -> int:
    behavior_log = BehaviorLog(
        behavior=behavior,
        related_date=related_date,
        pavlok_log=pavlok_log,
        coach_comment=coach_comment,
    )

    session = SessionLocal()
    try:
        session.add(behavior_log)
        session.commit()
        return behavior_log.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def read_logs(days: int) -> list[dict[str, Any]]:
    if days <= 0:
        raise SystemExit("days must be a positive integer.")
    session = SessionLocal()
    try:
        today = now_jst().date()
        start_date = today - timedelta(days=days - 1)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(today + timedelta(days=1), datetime.min.time())
        rows = (
            session.query(BehaviorLog)
            .filter(BehaviorLog.created_at >= start_dt)
            .filter(BehaviorLog.created_at < end_dt)
            .order_by(BehaviorLog.created_at.asc())
            .all()
        )
        return [
            {
                "id": row.id,
                "behavior": row.behavior,
                "related_date": row.related_date.isoformat() if row.related_date else None,
                "pavlok_log": row.pavlok_log,
                "coach_comment": row.coach_comment,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    finally:
        session.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Insert or read behavior log records.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    write_parser = subparsers.add_parser("write", help="Insert a record.")
    write_parser.add_argument(
        "behavior",
        choices=("good", "bad"),
        help="Behavior type.",
    )
    write_parser.add_argument(
        "--related-date",
        help="Optional related date (YYYY-MM-DD or YYYYMMDD).",
    )
    write_parser.add_argument(
        "--pavlok-log",
        help="JSON object for pavlok_log (use '-' to read from stdin).",
    )
    write_parser.add_argument(
        "--coach-comment",
        help="Optional coach comment.",
    )

    read_parser = subparsers.add_parser("read", help="Fetch logs from the last N days.")
    read_parser.add_argument(
        "days",
        type=int,
        help="Number of days to include counting back from today (JST).",
    )

    args = parser.parse_args(argv)

    if args.mode == "read":
        payload = read_logs(args.days)
        print(json.dumps(payload))
        return

    pavlok_log = parse_pavlok_log(args.pavlok_log)
    related_date = parse_related_date(args.related_date)
    record_id = write_log(args.behavior, related_date, pavlok_log, args.coach_comment)
    print(json.dumps({"id": record_id}))


if __name__ == "__main__":
    main()
