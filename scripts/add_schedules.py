import argparse
import json
import sys
from datetime import datetime
from typing import Any

from db.engine import SessionLocal
from db.models import Schedule


def parse_scheduled_date(value: Any) -> datetime:
    if isinstance(value, int):
        value = str(value)

    if isinstance(value, str):
        value = value.strip()
        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, "%Y%m%d")
        if len(value) == 12 and value.isdigit():
            return datetime.strptime(value, "%Y%m%d%H%M")

        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

    raise SystemExit(
        "scheduled_date must be YYYYMMDD, YYYYMMDDhhmm, YYYY-MM-DD, or YYYY-MM-DD hh:mm: "
        f"{value!r}"
    )


def load_records(raw: str) -> list[dict[str, Any]]:
    if raw == "-":
        raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc.msg}") from exc

    if not isinstance(data, list):
        raise SystemExit("JSON must be a list of records.")

    return data


def build_schedules(records: list[dict[str, Any]]) -> list[Schedule]:
    schedules: list[Schedule] = []
    required = {"prompt_name", "input_value", "scheduled_date"}

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise SystemExit(f"Record #{index} must be an object.")

        cleaned = dict(record)
        cleaned.pop("id", None)
        cleaned.pop("state", None)

        missing = [key for key in required if key not in cleaned]
        if missing:
            raise SystemExit(
                f"Record #{index} is missing required fields: {', '.join(sorted(missing))}"
            )

        unknown = sorted(set(cleaned) - required)
        if unknown:
            raise SystemExit(
                f"Record #{index} has unsupported fields: {', '.join(unknown)}"
            )

        schedules.append(
            Schedule(
                prompt_name=str(cleaned["prompt_name"]),
                input_value=str(cleaned["input_value"]),
                scheduled_date=parse_scheduled_date(cleaned["scheduled_date"]),
                state="pending",
            )
        )

    return schedules


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Insert multiple schedule records into the database.",
    )
    parser.add_argument(
        "records",
        help="JSON array of schedule records (use '-' to read from stdin).",
    )
    args = parser.parse_args(argv)

    records = load_records(args.records)
    schedules = build_schedules(records)
    if not schedules:
        raise SystemExit("No records to insert.")

    session = SessionLocal()
    try:
        session.add_all(schedules)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(json.dumps({"inserted": len(schedules)}))


if __name__ == "__main__":
    main()
