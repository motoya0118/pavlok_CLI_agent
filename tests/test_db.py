from datetime import datetime

from db import models


def test_db_crud(db_session):
    now = datetime(2026, 1, 11, 9, 0)

    schedule = models.Schedule(
        prompt_name="morning",
        input_value="{}",
        scheduled_date=now,
        state="pending",
    )
    db_session.add(schedule)

    punishment = models.DailyPunishment(
        date=now.date(),
        ignore_count=1,
        punishment_count=1,
        executed_count=0,
        state="pending",
    )
    db_session.add(punishment)

    ignore_event = models.SlackIgnoreEvent(
        slack_message_ts="1700000000.0001",
        detected_at=now,
        date=now.date(),
    )
    db_session.add(ignore_event)

    pavlok_count = models.PavlokCount(
        date=now.date(),
        zap_count=2,
    )
    db_session.add(pavlok_count)

    behavior_log = models.BehaviorLog(
        behavior="good",
        related_date=now.date(),
        pavlok_log={"ok": True},
        coach_comment="nice",
    )
    db_session.add(behavior_log)

    db_session.commit()

    fetched_schedule = db_session.get(models.Schedule, schedule.id)
    assert fetched_schedule is not None
    assert fetched_schedule.prompt_name == "morning"

    fetched_punishment = db_session.get(models.DailyPunishment, punishment.id)
    assert fetched_punishment is not None
    assert fetched_punishment.punishment_count == 1

    fetched_ignore = db_session.get(models.SlackIgnoreEvent, ignore_event.id)
    assert fetched_ignore is not None
    assert fetched_ignore.slack_message_ts == "1700000000.0001"

    fetched_pavlok = db_session.get(models.PavlokCount, pavlok_count.id)
    assert fetched_pavlok is not None
    assert fetched_pavlok.zap_count == 2

    fetched_behavior = db_session.get(models.BehaviorLog, behavior_log.id)
    assert fetched_behavior is not None
    assert fetched_behavior.related_date == now.date()
