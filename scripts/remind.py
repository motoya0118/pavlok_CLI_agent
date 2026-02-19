#!/usr/bin/env python3
"""
v0.3 Remind Event Script

remindイベント実行：激励メッセージ + YES/NOボタンを投稿
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.slack_lib.blockkit import BlockKitBuilder
from scripts import slack


def resolve_ignore_interval_minutes(session, user_id: str) -> int:
    """Resolve IGNORE_INTERVAL (seconds) from user config and convert to minutes."""
    from backend.models import Configuration

    interval_seconds = 900
    row = (
        session.query(Configuration.value)
        .filter(
            Configuration.user_id == user_id,
            Configuration.key == "IGNORE_INTERVAL",
        )
        .first()
    )
    if row and row[0] is not None:
        try:
            interval_seconds = int(str(row[0]))
        except (TypeError, ValueError):
            interval_seconds = 900

    if interval_seconds <= 0:
        interval_seconds = 900
    return max(1, interval_seconds // 60)


def build_remind_content(session, schedule) -> tuple[str, str, str]:
    """Resolve task name/time/description for remind notification."""
    from backend.models import Commitment

    if isinstance(schedule.run_at, datetime):
        task_time = schedule.run_at.strftime("%H:%M:%S")
    else:
        task_time = "--:--:--"

    # Match commitment by exact time to avoid picking unrelated active rows.
    commitment = (
        session.query(Commitment)
        .filter_by(
            user_id=schedule.user_id,
            active=True,
            time=task_time,
        )
        .first()
    )

    if commitment:
        task_name = commitment.task
    else:
        task_name = (schedule.comment or "").strip() or "タスク"

    description = schedule.comment or "やってるか？"
    return task_name, task_time, description


def main():
    """remindイベントメイン処理"""
    schedule_id = os.getenv("SCHEDULE_ID")
    if not schedule_id:
        print("Error: SCHEDULE_ID environment variable not set")
        sys.exit(1)

    # Get schedule from database
    from backend.models import Schedule
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///oni.db"))
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        schedule = session.query(Schedule).filter_by(id=schedule_id).first()
        if not schedule:
            print(f"Error: Schedule {schedule_id} not found")
            sys.exit(1)

        task_name, task_time, description = build_remind_content(session, schedule)
        ignore_interval_minutes = resolve_ignore_interval_minutes(
            session=session,
            user_id=str(schedule.user_id),
        )

        # Get channel
        channel = slack.require_channel()

        # Post remind notification
        token = slack.require_bot_token()
        blocks = BlockKitBuilder.remind_notification(
            schedule_id=schedule_id,
            task_name=task_name,
            task_time=task_time,
            description=description,
            ignore_interval_minutes=ignore_interval_minutes,
        )

        response = slack.post_message(blocks, channel, token)

        # Save thread_ts for later updates
        thread_ts = response.json().get("message", {}).get("ts")
        print(f"Remind notification sent. thread_ts: {thread_ts}")

        # Update schedule with thread_ts
        schedule.thread_ts = thread_ts
        session.commit()

    finally:
        session.close()


if __name__ == "__main__":
    main()
