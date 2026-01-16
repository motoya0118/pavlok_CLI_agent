import argparse
import json
import os

import requests
from dotenv import load_dotenv

from db.engine import SessionLocal
from db.models import PavlokCount, now_jst

load_dotenv()


def _require_api_key() -> str:
    api_key = os.getenv("PAVLOK_API_KEY")
    if not api_key:
        raise SystemExit("PAVLOK_API_KEY is not set. Add it to .env or the environment.")
    return api_key


def _get_int_env(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        if default is None:
            raise SystemExit(f"{name} is not set. Add it to .env or the environment.")
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer.") from exc


def _increment_zap_count() -> tuple[str, int]:
    session = SessionLocal()
    try:
        today = now_jst().date()
        record = session.query(PavlokCount).filter_by(date=today).first()
        if record is None:
            record = PavlokCount(date=today, zap_count=1)
            session.add(record)
            new_count = 1
        else:
            record.zap_count += 1
            new_count = record.zap_count
        session.commit()
        return today.isoformat(), new_count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def call(stimulus_type: str, stimulus_value: int, reason: str) -> dict:
    url = "https://api.pavlok.com/api/v5/stimulus/send"
    api_key = _require_api_key()

    stimulus_type = str(stimulus_type)
    stimulus_value = int(stimulus_value)

    if stimulus_type.lower() == "zap":
        limit_day = _get_int_env("LIMIT_DAY_PAVLOK_COUNTS")
        limit_value = _get_int_env("LIMIT_PAVLOK_ZAP_VALUE")
        date_str, zap_count = _increment_zap_count()
        if zap_count > limit_day:
            return {
                "skipped": True,
                "reason": "limit_reached",
                "date": date_str,
                "zap_count": zap_count,
                "LIMIT_DAY_PAVLOK_COUNTS": limit_day,
            }
        if stimulus_value > limit_value:
            stimulus_value = limit_value

    payload = {
        "stimulus": {
            "stimulusType": stimulus_type,
            "stimulusValue": stimulus_value,
        }
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=10)
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a Pavlok stimulus via the API.",
    )
    parser.add_argument("stimulusType", help="Type of stimulus to send.")
    parser.add_argument("stimulusValue", type=int, help="Stimulus value as an integer.")
    parser.add_argument("reason", help="Trigger reason for the Pavlok device")
    args = parser.parse_args()

    result = call(args.stimulusType, args.stimulusValue, args.reason)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
