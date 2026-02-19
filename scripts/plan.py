#!/usr/bin/env python3
"""
v0.3 Plan Event Script

planイベント実行：24時間分の予定をSlackに投稿
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.slack_lib.blockkit import BlockKitBuilder
from scripts import slack


def main():
    """planイベントメイン処理"""
    schedule_id = os.getenv("SCHEDULE_ID")
    if not schedule_id:
        print("Error: SCHEDULE_ID environment variable not set")
        sys.exit(1)

    # Get user's commitments from database
    from backend.models import Commitment, Schedule
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

        # Get active commitments
        commitments = session.query(Commitment).filter_by(
            user_id=schedule.user_id,
            active=True
        ).order_by(Commitment.time).all()

        # Build scheduled tasks list
        scheduled_tasks = []
        for cm in commitments:
            scheduled_tasks.append({
                "task": cm.task,
                "date": "今日",
                "time": cm.time
            })

        # Build next plan info
        next_plan = {
            "date": "明日",
            "time": "07:00"
        }

        # Get channel
        channel = slack.require_channel()

        # Post plan open notification
        token = slack.require_bot_token()
        blocks = BlockKitBuilder.plan_open_notification(
            schedule_id=schedule_id,
            user_id=str(schedule.user_id),
        )

        response = slack.post_message(blocks, channel, token)

        # Save thread_ts for later updates
        thread_ts = response.json().get("message", {}).get("ts")
        print(f"Plan notification sent. thread_ts: {thread_ts}")

        # Update schedule with thread_ts
        schedule.thread_ts = thread_ts
        session.commit()

    finally:
        session.close()


if __name__ == "__main__":
    main()
