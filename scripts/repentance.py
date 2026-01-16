import json
import os
import time

from db.engine import SessionLocal
from db.models import DailyPunishment, now_jst
from scripts import pavlok


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


def execute_punishments() -> int:
    stimulus_type = os.getenv("PAVLOK_TYPE_PUNISH")
    if not stimulus_type:
        raise SystemExit("PAVLOK_TYPE_PUNISH is not set. Add it to .env or the environment.")
    stimulus_value = _get_int_env("PAVLOK_VALUE_PUNISH")
    interval = _get_int_env("PUNISH_INTERVAL_SEC", default=1)

    session = SessionLocal()
    executed_total = 0
    try:
        targets = (
            session.query(DailyPunishment)
            .filter(DailyPunishment.state.in_(["pending", "failed"]))
            .all()
        )

        for punishment in targets:
            punishment.state = "running"
            session.commit()

            remaining = max(punishment.punishment_count - punishment.executed_count, 0)
            if remaining == 0:
                punishment.state = "done"
                session.commit()
                continue

            for _ in range(remaining):
                try:
                    result = pavlok.call(
                        stimulus_type,
                        stimulus_value,
                        f"repentance:{punishment.date.isoformat()}",
                    )
                except Exception:
                    punishment.executed_count += 1
                    punishment.state = "failed"
                    punishment.last_executed_at = now_jst()
                    session.commit()
                    break

                if result.get("skipped") and result.get("reason") == "limit_reached":
                    punishment.state = "failed"
                    session.commit()
                    break

                punishment.executed_count += 1
                executed_total += 1
                punishment.last_executed_at = now_jst()
                session.commit()

                if interval > 0:
                    time.sleep(interval)
            else:
                punishment.executed_count = punishment.punishment_count
                punishment.state = "done"
                session.commit()

        return executed_total
    finally:
        session.close()


def main(argv: list[str] | None = None) -> None:
    if argv:
        raise SystemExit("repentance does not accept arguments.")

    executed = execute_punishments()
    print(json.dumps({"executed": executed}))


if __name__ == "__main__":
    main()
