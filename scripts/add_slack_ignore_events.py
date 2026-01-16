import argparse
import json
from datetime import datetime

from db.engine import SessionLocal
from db.models import DailyPunishment, SlackIgnoreEvent, now_jst


def parse_detected_at(value: str | None) -> datetime:
    if value is None:
        return now_jst()
    raw = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise SystemExit("detected_at must be YYYY-MM-DD HH:MM or YYYYMMDDHHMM.")


def add_event(slack_message_ts: str, detected_at: datetime | None = None) -> int:
    detected_at = detected_at or now_jst()
    event_date = detected_at.date()

    session = SessionLocal()
    try:
        event = SlackIgnoreEvent(
            slack_message_ts=slack_message_ts,
            detected_at=detected_at,
            date=event_date,
        )
        session.add(event)

        punishment = session.query(DailyPunishment).filter_by(date=event_date).first()
        if punishment is None:
            punishment = DailyPunishment(
                date=event_date,
                ignore_count=1,
                punishment_count=1,
                executed_count=0,
                state="pending",
            )
            session.add(punishment)
        else:
            punishment.ignore_count += 1
            punishment.punishment_count += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return remaining_total()


def remaining_total() -> int:
    session = SessionLocal()
    try:
        rows = session.query(DailyPunishment).all()
        total = 0
        for row in rows:
            total += max(row.punishment_count - row.executed_count, 0)
        return total
    finally:
        session.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Insert a slack ignore event and update daily punishments.",
    )
    parser.add_argument("slack_message_ts", help="Slack message ts to record.")
    parser.add_argument(
        "--detected-at",
        help="Detected datetime (YYYY-MM-DD HH:MM or YYYYMMDDHHMM).",
    )
    args = parser.parse_args(argv)

    detected_at = parse_detected_at(args.detected_at)
    total = add_event(args.slack_message_ts, detected_at)
    print(json.dumps({"remaining_total": total}))


if __name__ == "__main__":
    main()
