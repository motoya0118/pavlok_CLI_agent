from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    ActionLog,
    ActionResult,
    Base,
    Commitment,
    EventType,
    ReportDelivery,
    Schedule,
    ScheduleState,
    serialize_report_input_value,
)
from scripts import report as report_script


def _new_session(tmp_path, filename: str):
    db_path = tmp_path / filename
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _create_remind_schedule(
    session,
    user_id: str,
    task: str,
    run_at: datetime,
    thread_ts: str | None = None,
) -> Schedule:
    commitment = Commitment(user_id=user_id, task=task, time=run_at.strftime("%H:%M:%S"), active=True)
    session.add(commitment)
    session.flush()
    schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REMIND,
        commitment_id=commitment.id,
        run_at=run_at,
        state=ScheduleState.DONE,
        thread_ts=thread_ts,
        comment=task,
        retry_count=0,
    )
    session.add(schedule)
    session.flush()
    return schedule


def test_decide_report_type_returns_monthly_when_previous_month_not_delivered(tmp_path):
    session_factory = _new_session(tmp_path, "report_type_monthly.sqlite3")
    session = session_factory()

    report_type = report_script.decide_report_type(session, "U_TEST", date(2026, 3, 10))
    assert report_type == "monthly"
    session.close()


def test_decide_report_type_returns_weekly_when_previous_month_delivered(tmp_path):
    session_factory = _new_session(tmp_path, "report_type_weekly.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=datetime(2026, 3, 10, 7, 0, 0),
        state=ScheduleState.DONE,
        retry_count=0,
        comment="report",
    )
    session.add(schedule)
    session.flush()
    prev_start, prev_end = report_script.previous_month_period(date(2026, 3, 10))
    session.add(
        ReportDelivery(
            schedule_id=schedule.id,
            user_id=user_id,
            report_type="monthly",
            period_start=prev_start,
            period_end=prev_end,
            posted_at=datetime(2026, 3, 1, 7, 0, 0),
            thread_ts="1730000000.000100",
            markdown_table="|k|v|",
            llm_comment="ok",
        )
    )
    session.commit()

    report_type = report_script.decide_report_type(session, user_id, date(2026, 3, 10))
    assert report_type == "weekly"
    session.close()


def test_resolve_report_period_weekly_uses_last_weekly_end(tmp_path):
    session_factory = _new_session(tmp_path, "report_period_weekly.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=datetime(2026, 3, 10, 7, 0, 0),
        state=ScheduleState.DONE,
        retry_count=0,
        comment="report",
    )
    session.add(schedule)
    session.flush()
    session.add(
        ReportDelivery(
            schedule_id=schedule.id,
            user_id=user_id,
            report_type="weekly",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 5),
            posted_at=datetime(2026, 3, 6, 7, 0, 0),
            thread_ts="1730000000.000200",
            markdown_table="|k|v|",
            llm_comment="ok",
        )
    )
    session.commit()

    period_start, period_end = report_script.resolve_report_period(
        session,
        user_id=user_id,
        run_date=date(2026, 3, 10),
        report_type="weekly",
    )
    assert period_start == date(2026, 3, 6)
    assert period_end == date(2026, 3, 9)
    session.close()


def test_aggregate_report_stats_counts_only_posted_remind_with_yes(tmp_path):
    session_factory = _new_session(tmp_path, "report_aggregate.sqlite3")
    session = session_factory()
    user_id = "U_TEST"

    # Counted + success
    remind_1 = _create_remind_schedule(
        session,
        user_id=user_id,
        task="task1",
        run_at=datetime(2026, 3, 2, 7, 0, 0),
        thread_ts="1730000000.000300",
    )
    session.add(ActionLog(schedule_id=remind_1.id, result=ActionResult.YES))

    # Counted + failure
    _create_remind_schedule(
        session,
        user_id=user_id,
        task="task2",
        run_at=datetime(2026, 3, 3, 7, 0, 0),
        thread_ts="1730000000.000301",
    )

    # Not counted (thread_ts is NULL)
    remind_3 = _create_remind_schedule(
        session,
        user_id=user_id,
        task="task3",
        run_at=datetime(2026, 3, 4, 7, 0, 0),
        thread_ts=None,
    )
    session.add(ActionLog(schedule_id=remind_3.id, result=ActionResult.YES))

    # Not counted (out of range)
    remind_4 = _create_remind_schedule(
        session,
        user_id=user_id,
        task="task4",
        run_at=datetime(2026, 2, 20, 7, 0, 0),
        thread_ts="1730000000.000302",
    )
    session.add(ActionLog(schedule_id=remind_4.id, result=ActionResult.YES))

    session.commit()

    stats = report_script.aggregate_report_stats(
        session,
        user_id=user_id,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 7),
    )
    assert stats["success_count"] == 1
    assert stats["failure_count"] == 1
    assert stats["success_rate"] == 50.0
    by_commitment = stats["by_commitment"]
    assert isinstance(by_commitment, list)
    assert len(by_commitment) == 2
    rows_by_task = {str(row["task"]): row for row in by_commitment}
    assert int(rows_by_task["task1"]["success_count"]) == 1
    assert int(rows_by_task["task1"]["failure_count"]) == 0
    assert float(rows_by_task["task1"]["success_rate"]) == 100.0
    assert int(rows_by_task["task2"]["success_count"]) == 0
    assert int(rows_by_task["task2"]["failure_count"]) == 1
    assert float(rows_by_task["task2"]["success_rate"]) == 0.0
    session.close()


def test_main_inserts_report_delivery_only_after_successful_post(tmp_path, monkeypatch):
    session_factory = _new_session(tmp_path, "report_main_success.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    report_schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=datetime(2026, 3, 10, 7, 0, 0),
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
    )
    session.add(report_schedule)
    session.commit()
    schedule_id = str(report_schedule.id)
    session.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'report_main_success.sqlite3'}")
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")

    class _FakeResponse:
        def json(self):
            return {"ok": True, "message": {"ts": "1730000000.000900"}}

    monkeypatch.setattr(report_script.slack, "post_message", lambda *args, **kwargs: _FakeResponse())
    monkeypatch.setattr(
        report_script,
        "generate_report_comment",
        lambda payload, report_type, stats, charactor: ("generated", {"ok": True}),
    )

    report_script.main()

    session = session_factory()
    delivery_rows = session.query(ReportDelivery).filter(ReportDelivery.user_id == user_id).all()
    assert len(delivery_rows) == 1
    refreshed = session.query(Schedule).filter(Schedule.id == schedule_id).first()
    assert refreshed is not None
    assert refreshed.thread_ts == "1730000000.000900"
    session.close()


def test_main_accepts_top_level_ts_from_slack_post_response(tmp_path, monkeypatch):
    session_factory = _new_session(tmp_path, "report_main_success_top_level_ts.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    report_schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=datetime(2026, 3, 10, 7, 0, 0),
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
    )
    session.add(report_schedule)
    session.commit()
    schedule_id = str(report_schedule.id)
    session.close()

    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite:///{tmp_path / 'report_main_success_top_level_ts.sqlite3'}"
    )
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")

    class _FakeResponse:
        def json(self):
            return {"ok": True, "ts": "1730000000.000901", "message": {"text": "posted"}}

    monkeypatch.setattr(report_script.slack, "post_message", lambda *args, **kwargs: _FakeResponse())
    monkeypatch.setattr(
        report_script,
        "generate_report_comment",
        lambda payload, report_type, stats, charactor: ("generated", {"ok": True}),
    )

    report_script.main()

    session = session_factory()
    delivery_rows = session.query(ReportDelivery).filter(ReportDelivery.user_id == user_id).all()
    assert len(delivery_rows) == 1
    refreshed = session.query(Schedule).filter(Schedule.id == schedule_id).first()
    assert refreshed is not None
    assert refreshed.thread_ts == "1730000000.000901"
    session.close()


def test_main_does_not_insert_report_delivery_when_post_fails(tmp_path, monkeypatch):
    session_factory = _new_session(tmp_path, "report_main_failure.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    report_schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=datetime(2026, 3, 10, 7, 0, 0),
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
    )
    session.add(report_schedule)
    session.commit()
    schedule_id = str(report_schedule.id)
    session.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'report_main_failure.sqlite3'}")
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")
    monkeypatch.setattr(
        report_script,
        "generate_report_comment",
        lambda payload, report_type, stats, charactor: ("generated", {"ok": True}),
    )

    def _raise_post_error(*args, **kwargs):
        raise RuntimeError("post failed")

    monkeypatch.setattr(report_script.slack, "post_message", _raise_post_error)

    with pytest.raises(RuntimeError, match="post failed"):
        report_script.main()

    session = session_factory()
    delivery_rows = session.query(ReportDelivery).filter(ReportDelivery.user_id == user_id).all()
    assert len(delivery_rows) == 0
    refreshed = session.query(Schedule).filter(Schedule.id == schedule_id).first()
    assert refreshed is not None
    assert refreshed.thread_ts is None
    session.close()


def test_main_prefers_monthly_and_suppresses_weekly_when_monthly_active(tmp_path, monkeypatch):
    session_factory = _new_session(tmp_path, "report_main_monthly_active.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    run_at = datetime(2026, 3, 10, 7, 0, 0)

    target = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=run_at,
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
    )
    session.add(target)
    session.flush()

    old_weekly_schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=run_at - timedelta(days=2),
        state=ScheduleState.DONE,
        retry_count=0,
        comment="report",
    )
    session.add(old_weekly_schedule)
    session.flush()
    session.add(
        ReportDelivery(
            schedule_id=old_weekly_schedule.id,
            user_id=user_id,
            report_type="weekly",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 7),
            posted_at=datetime(2026, 3, 8, 7, 0, 0),
            thread_ts="1730000000.111100",
            markdown_table="|k|v|",
            llm_comment="old weekly",
        )
    )
    session.commit()
    schedule_id = str(target.id)
    session.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'report_main_monthly_active.sqlite3'}")
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")
    monkeypatch.setattr(
        report_script,
        "generate_report_comment",
        lambda payload, report_type, stats, charactor: ("generated", {"ok": True}),
    )

    captured: dict[str, str] = {}

    class _FakeResponse:
        def json(self):
            return {"ok": True, "message": {"ts": "1730000000.111199"}}

    def _fake_post_message(*args, **kwargs):
        captured["text"] = str(kwargs.get("text", ""))
        return _FakeResponse()

    monkeypatch.setattr(report_script.slack, "post_message", _fake_post_message)

    report_script.main()

    session = session_factory()
    created = (
        session.query(ReportDelivery)
        .filter(ReportDelivery.schedule_id == schedule_id)
        .first()
    )
    assert created is not None
    assert created.report_type == "monthly"
    assert captured["text"].startswith("月次レポート")
    assert "週次" not in captured["text"]
    session.close()


def test_main_creates_replacement_schedule_when_delivery_exists_for_same_schedule(tmp_path, monkeypatch):
    session_factory = _new_session(tmp_path, "report_main_replacement_schedule.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    run_at = datetime(2026, 3, 10, 7, 0, 0)

    target = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=run_at,
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
    )
    session.add(target)
    session.flush()

    # Existing monthly row on the same schedule_id (already used once).
    prev_start, prev_end = report_script.previous_month_period(run_at.date())
    session.add(
        ReportDelivery(
            schedule_id=target.id,
            user_id=user_id,
            report_type="monthly",
            period_start=prev_start,
            period_end=prev_end,
            posted_at=datetime(2026, 3, 1, 7, 0, 0),
            thread_ts="1730000000.444400",
            markdown_table="old monthly",
            llm_comment="old",
        )
    )
    session.commit()
    schedule_id = str(target.id)
    session.close()

    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite:///{tmp_path / 'report_main_replacement_schedule.sqlite3'}"
    )
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")
    monkeypatch.setattr(
        report_script,
        "generate_report_comment",
        lambda payload, report_type, stats, charactor: ("generated", {"ok": True}),
    )

    class _FakeResponse:
        def json(self):
            return {"ok": True, "message": {"ts": "1730000000.444499"}}

    monkeypatch.setattr(report_script.slack, "post_message", lambda *args, **kwargs: _FakeResponse())

    report_script.main()

    session = session_factory()
    deliveries = (
        session.query(ReportDelivery)
        .filter(ReportDelivery.user_id == user_id)
        .order_by(ReportDelivery.posted_at.asc())
        .all()
    )
    assert len(deliveries) == 2
    monthly, weekly = deliveries[0], deliveries[1]
    assert monthly.report_type == "monthly"
    assert weekly.report_type == "weekly"
    assert str(monthly.schedule_id) == schedule_id
    assert str(weekly.schedule_id) != schedule_id

    original = session.query(Schedule).filter(Schedule.id == schedule_id).first()
    replacement = session.query(Schedule).filter(Schedule.id == str(weekly.schedule_id)).first()
    assert original is not None
    assert replacement is not None
    assert original.state == ScheduleState.DONE
    assert replacement.state == ScheduleState.PROCESSING
    assert replacement.thread_ts == "1730000000.444499"
    session.close()


@pytest.mark.parametrize(
    ("has_previous_monthly", "expected_type"),
    [
        (False, "monthly"),
        (True, "weekly"),
    ],
)
def test_main_uses_run_date_even_if_ui_selected_tomorrow(
    tmp_path, monkeypatch, has_previous_monthly, expected_type
):
    db_name = f"report_main_tomorrow_{expected_type}.sqlite3"
    session_factory = _new_session(tmp_path, db_name)
    session = session_factory()
    user_id = "U_TEST"
    run_at = datetime(2026, 3, 2, 7, 0, 0)

    target = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=run_at,
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
        input_value=serialize_report_input_value(
            ui_date="tomorrow",
            ui_time="07:00",
            updated_at="2026-03-01T23:00:00",
        ),
    )
    session.add(target)
    session.flush()

    if has_previous_monthly:
        prev_schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=run_at - timedelta(days=1),
            state=ScheduleState.DONE,
            retry_count=0,
            comment="report",
        )
        session.add(prev_schedule)
        session.flush()
        session.add(
            ReportDelivery(
                schedule_id=prev_schedule.id,
                user_id=user_id,
                report_type="monthly",
                period_start=date(2026, 2, 1),
                period_end=date(2026, 2, 28),
                posted_at=datetime(2026, 3, 1, 7, 0, 0),
                thread_ts="1730000000.222201",
                markdown_table="|k|v|",
                llm_comment="old monthly",
            )
        )

    session.commit()
    schedule_id = str(target.id)
    session.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / db_name}")
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")
    monkeypatch.setattr(
        report_script,
        "generate_report_comment",
        lambda payload, report_type, stats, charactor: ("generated", {"ok": True}),
    )

    captured: dict[str, str] = {}

    class _FakeResponse:
        def json(self):
            return {"ok": True, "message": {"ts": "1730000000.222299"}}

    def _fake_post_message(*args, **kwargs):
        captured["text"] = str(kwargs.get("text", ""))
        return _FakeResponse()

    monkeypatch.setattr(report_script.slack, "post_message", _fake_post_message)

    report_script.main()

    session = session_factory()
    created = (
        session.query(ReportDelivery)
        .filter(ReportDelivery.schedule_id == schedule_id)
        .first()
    )
    assert created is not None
    assert created.report_type == expected_type
    expected_label = "月次レポート" if expected_type == "monthly" else "週次レポート"
    assert captured["text"].startswith(expected_label)
    session.close()


def test_main_handles_zero_targets_without_comment_failure(tmp_path, monkeypatch):
    session_factory = _new_session(tmp_path, "report_main_zero_targets.sqlite3")
    session = session_factory()
    user_id = "U_TEST"
    run_at = datetime(2026, 3, 10, 7, 0, 0)
    report_schedule = Schedule(
        user_id=user_id,
        event_type=EventType.REPORT,
        run_at=run_at,
        state=ScheduleState.PROCESSING,
        retry_count=0,
        comment="report",
    )
    session.add(report_schedule)
    session.commit()
    schedule_id = str(report_schedule.id)
    session.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'report_main_zero_targets.sqlite3'}")
    monkeypatch.setenv("SCHEDULE_ID", schedule_id)
    monkeypatch.setattr(report_script.slack, "require_channel", lambda: "C_TEST")
    monkeypatch.setattr(report_script.slack, "require_bot_token", lambda: "xoxb-test")
    monkeypatch.setattr(report_script, "load_coach_charactor", lambda session, user_id: "coach")
    monkeypatch.setattr(
        report_script,
        "run_codex_exec",
        lambda prompt: {"ok": False, "stdout": "", "stderr": "codex failed"},
    )

    class _FakeResponse:
        def json(self):
            return {"ok": True, "message": {"ts": "1730000000.333300"}}

    monkeypatch.setattr(report_script.slack, "post_message", lambda *args, **kwargs: _FakeResponse())

    report_script.main()

    session = session_factory()
    created = (
        session.query(ReportDelivery)
        .filter(ReportDelivery.schedule_id == schedule_id)
        .first()
    )
    assert created is not None
    assert "合計: 成功 0 / 失敗 0 / 成功率 0.0%" in created.markdown_table
    assert "（対象なし）" in created.markdown_table
    assert "0.0%" in created.markdown_table
    assert isinstance(created.llm_comment, str)
    assert created.llm_comment.strip() != ""
    session.close()


def test_format_report_summary_text_outputs_commitment_lines():
    summary = report_script.format_report_summary_text(
        {
            "success_count": 3,
            "failure_count": 1,
            "success_rate": 75.0,
            "by_commitment": [
                {"task": "朝の散歩", "success_count": 2, "failure_count": 1, "success_rate": 66.7},
                {"task": "筋トレ", "success_count": 1, "failure_count": 0, "success_rate": 100.0},
            ],
        }
    )

    assert "合計: 成功 3 / 失敗 1 / 成功率 75.0%" in summary
    assert "- 朝の散歩: 成功 2 / 失敗 1 / 成功率 66.7%" in summary
    assert "- 筋トレ: 成功 1 / 失敗 0 / 成功率 100.0%" in summary


def test_build_report_blocks_contains_report_read_button():
    blocks = report_script.build_report_blocks(
        schedule_id="S_REPORT_1",
        user_id="U_TEST",
        report_type="weekly",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 7),
        stats={
            "success_count": 1,
            "failure_count": 0,
            "success_rate": 100.0,
            "by_commitment": [
                {
                    "task": "運動する",
                    "success_count": 1,
                    "failure_count": 0,
                    "success_rate": 100.0,
                }
            ],
        },
        llm_comment="コメント",
    )
    actions = [b for b in blocks if b.get("type") == "actions"]
    assert actions
    button = actions[0]["elements"][0]
    assert button["action_id"] == "report_read"
    assert "S_REPORT_1" in button["value"]
