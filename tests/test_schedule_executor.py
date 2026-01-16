from datetime import datetime, timedelta
from pathlib import Path

from db import models
import main


class DummyResult:
    def __init__(self, returncode=0, stdout="ok", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_schedule_executor_runs_due(db_session, monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_path = prompt_dir / "remind_ask.md"
    prompt_path.write_text("Input: {{input_value}}\n")

    now = datetime(2026, 1, 11, 9, 0)
    schedule = models.Schedule(
        prompt_name="remind_ask",
        input_value="hello",
        scheduled_date=now,
        state="pending",
    )
    morning = models.Schedule(
        prompt_name="morning",
        input_value="",
        scheduled_date=now + timedelta(days=1),
        state="pending",
    )
    db_session.add(schedule)
    db_session.add(morning)
    db_session.commit()

    def fake_now():
        return now

    def fake_run(prompt):
        assert "hello" in prompt
        return DummyResult()

    executor = main.ScheduleExecutor(
        prompt_dir=prompt_dir,
        runner=fake_run,
        now_func=fake_now,
        do_migrations=False,
    )

    executed = executor.run_once()

    assert executed == 1
    db_session.expire_all()
    refreshed = db_session.get(models.Schedule, schedule.id)
    assert refreshed.state == "done"
    assert refreshed.last_result == "ok"


def test_schedule_executor_failure_retries(db_session, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_path = prompt_dir / "remind_ask.md"
    prompt_path.write_text("Input: {{input_value}}\n")

    now = datetime(2026, 1, 11, 9, 0)
    schedule = models.Schedule(
        prompt_name="remind_ask",
        input_value="oops",
        scheduled_date=now,
        state="failed",
    )
    morning = models.Schedule(
        prompt_name="morning",
        input_value="",
        scheduled_date=now + timedelta(days=1),
        state="pending",
    )
    db_session.add(schedule)
    db_session.add(morning)
    db_session.commit()

    def fake_now():
        return now

    def fake_run(_prompt):
        return DummyResult(returncode=1, stdout="", stderr="boom")

    executor = main.ScheduleExecutor(
        prompt_dir=prompt_dir,
        runner=fake_run,
        now_func=fake_now,
        do_migrations=False,
    )

    executed = executor.run_once()

    assert executed == 1
    db_session.expire_all()
    refreshed = db_session.get(models.Schedule, schedule.id)
    assert refreshed.state == "failed"
    assert refreshed.last_error
    assert refreshed.scheduled_date > now


def test_schedule_executor_initial_morning(db_session, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_path = prompt_dir / "morning.md"
    prompt_path.write_text("Morning {{input_value}}\n")

    now = datetime(2026, 1, 11, 9, 0)

    def fake_now():
        return now

    def fake_run(_prompt):
        return DummyResult()

    executor = main.ScheduleExecutor(
        prompt_dir=prompt_dir,
        runner=fake_run,
        now_func=fake_now,
        do_migrations=False,
    )

    executed = executor.run_once()

    assert executed == 1
    created = db_session.query(models.Schedule).filter_by(prompt_name="morning").first()
    assert created is not None
    assert created.state == "done"
