# v0.3 Slack Command API Tests
import json
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.api.command import (
    process_base_commit,
    process_cal,
    process_config,
    process_help,
    process_plan,
    process_restart,
    process_stop,
)
from backend.models import (
    Base,
    Commitment,
    Configuration,
    ConfigValueType,
    EventType,
    ReportDelivery,
    Schedule,
    ScheduleState,
)


@pytest.mark.asyncio
class TestCommandApi:
    @staticmethod
    def _weekday_token(value: datetime) -> str:
        mapping = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
        return mapping[value.weekday()]

    @staticmethod
    def _non_today_tomorrow_weekday(today_token: str, tomorrow_token: str) -> str:
        for token in ("sun", "mon", "tue", "wed", "thu", "fri", "sat"):
            if token not in {today_token, tomorrow_token}:
                return token
        return "sat"

    @staticmethod
    def _previous_month_period(now_value: datetime) -> tuple[date, date]:
        this_month_start = now_value.date().replace(day=1)
        prev_month_end = this_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        return prev_month_start, prev_month_end

    async def test_base_commit_command(self, v3_db_session, v3_test_data_factory):
        v3_test_data_factory.create_schedule()
        request = MagicMock(spec=Request)
        request.state = "base_commit"

        result = await process_base_commit(request)
        assert result["status"] == "success"
        assert "blocks" in result

    @pytest.mark.asyncio
    async def test_cal_command_opens_modal_when_trigger_id_exists(self, monkeypatch):
        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["trigger_id"] = trigger_id
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_cal(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
                "response_url": "https://example.com/response",
            }
        )

        assert result["status"] == "success"
        assert captured["trigger_id"] == "TRIGGER_TEST"
        view = captured["view"]
        assert view["type"] == "modal"
        assert view["callback_id"] == "calorie_submit"
        assert "private_metadata" in view
        assert "カロリー計算モーダルを開きました" in result["text"]

    @pytest.mark.asyncio
    async def test_cal_command_returns_warning_when_trigger_id_missing(self):
        result = await process_cal(
            {
                "user_id": "U_TEST",
                "channel_id": "C_TEST",
            }
        )

        assert result["status"] == "success"
        assert result["response_type"] == "ephemeral"
        assert "trigger_id が取得できないためモーダルを開けませんでした" in result["text"]

    @pytest.mark.asyncio
    async def test_base_commit_prefills_existing_commitments(self, tmp_path, monkeypatch):
        db_path = tmp_path / "prefill.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = session_factory()
        try:
            session.add_all(
                [
                    Commitment(user_id="U_TEST", task="昼", time="12:00:00", active=True),
                    Commitment(user_id="U_TEST", task="朝", time="07:00:00", active=True),
                    Commitment(user_id="U_TEST", task="夜", time="21:00:00", active=True),
                ]
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)

        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["trigger_id"] = trigger_id
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_base_commit(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
                "response_url": "https://example.com/response",
            }
        )

        assert result["status"] == "success"
        assert captured["trigger_id"] == "TRIGGER_TEST"
        view = captured["view"]
        assert view["callback_id"] == "base_commit_submit"

        blocks = view["blocks"]
        task1 = next(b for b in blocks if b.get("block_id") == "commitment_1")
        task2 = next(b for b in blocks if b.get("block_id") == "commitment_2")
        task3 = next(b for b in blocks if b.get("block_id") == "commitment_3")
        time1 = next(b for b in blocks if b.get("block_id") == "time_1")
        time2 = next(b for b in blocks if b.get("block_id") == "time_2")
        time3 = next(b for b in blocks if b.get("block_id") == "time_3")

        assert task1["element"].get("initial_value") == "朝"
        assert task2["element"].get("initial_value") == "昼"
        assert task3["element"].get("initial_value") == "夜"
        assert time1["element"].get("initial_time") == "07:00"
        assert time2["element"].get("initial_time") == "12:00"
        assert time3["element"].get("initial_time") == "21:00"

    @pytest.mark.asyncio
    async def test_plan_command_opens_modal_with_pending_schedules(self, tmp_path, monkeypatch):
        db_path = tmp_path / "plan_modal.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = session_factory()
        try:
            now = datetime.now().replace(second=0, microsecond=0)
            morning = Commitment(user_id="U_TEST", task="朝", time="07:00:00", active=True)
            noon = Commitment(user_id="U_TEST", task="昼", time="12:00:00", active=True)
            night = Commitment(user_id="U_TEST", task="夜", time="21:00:00", active=True)
            session.add_all([morning, noon, night])
            session.flush()

            session.add_all(
                [
                    Schedule(
                        user_id="U_TEST",
                        event_type=EventType.REMIND,
                        commitment_id=morning.id,
                        run_at=now.replace(hour=7, minute=0),
                        state=ScheduleState.PENDING,
                        retry_count=0,
                        comment="朝",
                    ),
                    Schedule(
                        user_id="U_TEST",
                        event_type=EventType.REMIND,
                        commitment_id=night.id,
                        run_at=(now + timedelta(days=1)).replace(hour=21, minute=0),
                        state=ScheduleState.PENDING,
                        retry_count=0,
                        comment="夜",
                    ),
                    Schedule(
                        user_id="U_TEST",
                        event_type=EventType.PLAN,
                        run_at=(now + timedelta(days=1)).replace(hour=8, minute=0),
                        state=ScheduleState.PENDING,
                        retry_count=0,
                        comment="next plan",
                    ),
                    # DONE should not be shown in /plan prefill.
                    Schedule(
                        user_id="U_TEST",
                        event_type=EventType.REMIND,
                        commitment_id=noon.id,
                        run_at=now.replace(hour=12, minute=0),
                        state=ScheduleState.DONE,
                        retry_count=0,
                        comment="昼",
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["trigger_id"] = trigger_id
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_plan(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
                "response_url": "https://example.com/response",
            }
        )

        assert result["status"] == "success"
        assert captured["trigger_id"] == "TRIGGER_TEST"
        view = captured["view"]
        assert view["callback_id"] == "plan_submit"

        blocks = view["blocks"]
        first_section = blocks[0]
        second_section = blocks[5]
        time1 = next(b for b in blocks if b.get("block_id") == "task_1_time")
        time2 = next(b for b in blocks if b.get("block_id") == "task_2_time")
        date1 = next(b for b in blocks if b.get("block_id") == "task_1_date")
        date2 = next(b for b in blocks if b.get("block_id") == "task_2_date")
        next_plan_date = next(b for b in blocks if b.get("block_id") == "next_plan_date")
        next_plan_time = next(b for b in blocks if b.get("block_id") == "next_plan_time")

        assert "朝" in first_section["text"]["text"]
        assert "夜" in second_section["text"]["text"]
        assert date1["element"]["initial_option"]["value"] == "today"
        assert date2["element"]["initial_option"]["value"] == "tomorrow"
        assert time1["element"].get("initial_time") == "07:00"
        assert time2["element"].get("initial_time") == "21:00"
        assert next_plan_date["element"]["initial_option"]["value"] == "tomorrow"
        assert next_plan_time["element"].get("initial_time") == "08:00"

        metadata = json.loads(view["private_metadata"])
        plan_rows = metadata.get("plan_rows", [])
        assert len(plan_rows) == 2
        assert plan_rows[0]["index"] == 1
        assert plan_rows[0]["task"] == "朝"
        assert plan_rows[1]["index"] == 2
        assert plan_rows[1]["task"] == "夜"

    @pytest.mark.asyncio
    async def test_plan_command_shows_report_input_on_config_weekday(self, tmp_path, monkeypatch):
        db_path = tmp_path / "plan_report_weekday.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        now = datetime.now().replace(second=0, microsecond=0)
        today_token = self._weekday_token(now)

        session = session_factory()
        try:
            report_schedule = Schedule(
                user_id="U_TEST",
                event_type=EventType.REPORT,
                run_at=now,
                state=ScheduleState.DONE,
                retry_count=0,
            )
            session.add(report_schedule)
            session.flush()
            session.add(
                Configuration(
                    user_id="U_TEST",
                    key="REPORT_WEEKDAY",
                    value=today_token,
                    value_type=ConfigValueType.STR,
                )
            )
            session.add(
                Configuration(
                    user_id="U_TEST",
                    key="REPORT_TIME",
                    value="09:30",
                    value_type=ConfigValueType.STR,
                )
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_plan(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
            }
        )

        assert result["status"] == "success"
        blocks = captured["view"]["blocks"]
        report_date = next((b for b in blocks if b.get("block_id") == "report_date"), None)
        report_time = next((b for b in blocks if b.get("block_id") == "report_time"), None)
        assert report_date is not None
        assert report_time is not None
        assert report_date["element"]["initial_option"]["value"] == "today"
        assert report_time["element"]["initial_time"] == "09:30"

    @pytest.mark.asyncio
    async def test_plan_command_shows_report_input_when_monthly_active(self, tmp_path, monkeypatch):
        db_path = tmp_path / "plan_report_monthly_active.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        now = datetime.now().replace(second=0, microsecond=0)
        today_token = self._weekday_token(now)
        tomorrow_token = self._weekday_token(now + timedelta(days=1))
        non_match = self._non_today_tomorrow_weekday(today_token, tomorrow_token)

        session = session_factory()
        try:
            report_schedule = Schedule(
                user_id="U_TEST",
                event_type=EventType.REPORT,
                run_at=now,
                state=ScheduleState.DONE,
                retry_count=0,
            )
            session.add(report_schedule)
            session.flush()
            session.add(
                Configuration(
                    user_id="U_TEST",
                    key="REPORT_WEEKDAY",
                    value=non_match,
                    value_type=ConfigValueType.STR,
                )
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_plan(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
            }
        )

        assert result["status"] == "success"
        blocks = captured["view"]["blocks"]
        assert any(b.get("block_id") == "report_date" for b in blocks)
        assert any(b.get("block_id") == "report_time" for b in blocks)

    @pytest.mark.asyncio
    async def test_plan_command_hides_report_input_when_not_due(self, tmp_path, monkeypatch):
        db_path = tmp_path / "plan_report_hidden.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        now = datetime.now().replace(second=0, microsecond=0)
        today_token = self._weekday_token(now)
        tomorrow_token = self._weekday_token(now + timedelta(days=1))
        non_match = self._non_today_tomorrow_weekday(today_token, tomorrow_token)
        prev_start, prev_end = self._previous_month_period(now)

        session = session_factory()
        try:
            report_schedule = Schedule(
                user_id="U_TEST",
                event_type=EventType.REPORT,
                run_at=now,
                state=ScheduleState.DONE,
                retry_count=0,
            )
            session.add(report_schedule)
            session.flush()
            session.add(
                Configuration(
                    user_id="U_TEST",
                    key="REPORT_WEEKDAY",
                    value=non_match,
                    value_type=ConfigValueType.STR,
                )
            )
            session.add(
                ReportDelivery(
                    schedule_id=report_schedule.id,
                    user_id="U_TEST",
                    report_type="monthly",
                    period_start=prev_start,
                    period_end=prev_end,
                    posted_at=now,
                    markdown_table="|metric|value|",
                    llm_comment="ok",
                )
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_plan(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
            }
        )

        assert result["status"] == "success"
        blocks = captured["view"]["blocks"]
        assert not any(b.get("block_id") == "report_date" for b in blocks)
        assert not any(b.get("block_id") == "report_time" for b in blocks)

    @pytest.mark.asyncio
    async def test_stop_command(self, tmp_path, monkeypatch):
        db_path = tmp_path / "stop_command.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        result = await process_stop({"user_id": "U_TEST"})
        assert result["status"] == "success"
        assert "blocks" in result

        session = session_factory()
        try:
            row = session.query(Configuration).filter(Configuration.key == "SYSTEM_PAUSED").first()
            assert row is not None
            assert row.value == "true"
            assert row.value_type == ConfigValueType.BOOL
        finally:
            session.close()

    @pytest.mark.asyncio
    async def test_restart_command(self, tmp_path, monkeypatch):
        db_path = tmp_path / "restart_command.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        session = session_factory()
        try:
            session.add(
                Configuration(
                    user_id="U_TEST",
                    key="SYSTEM_PAUSED",
                    value="true",
                    value_type=ConfigValueType.BOOL,
                    default_value="false",
                )
            )
            session.commit()
        finally:
            session.close()

        result = await process_restart({"user_id": "U_TEST"})
        assert result["status"] == "success"
        assert "blocks" in result

        session = session_factory()
        try:
            row = session.query(Configuration).filter(Configuration.key == "SYSTEM_PAUSED").first()
            assert row is not None
            assert row.value == "false"
            assert row.value_type == ConfigValueType.BOOL
        finally:
            session.close()

    @pytest.mark.asyncio
    async def test_help_command(self):
        result = await process_help({"user_id": "U_TEST"})
        assert result["status"] == "success"
        assert result["response_type"] == "ephemeral"
        assert "blocks" in result
        blocks = result["blocks"]
        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"
        assert "/help" in blocks[0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_config_get_command(self, v3_db_session):
        request = MagicMock(spec=Request)
        request.method = "GET"

        result = await process_config(request)
        assert result["status"] == "success"
        assert "configurations" in result["data"]

    @pytest.mark.asyncio
    async def test_config_post_command(self, v3_db_session):
        config_data = {"PAVLOK_TYPE_PUNISH": "vibe", "PAVLOK_VALUE_PUNISH": "100"}

        request = MagicMock(spec=Request)
        request.method = "POST"
        request.state = "config"
        result = await process_config(request, config_data)

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_config_command_opens_modal_with_charactor_prefill(self, tmp_path, monkeypatch):
        db_path = tmp_path / "config_modal.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = session_factory()
        try:
            session.add(
                Configuration(
                    user_id="U_TEST",
                    key="COACH_CHARACTOR",
                    value="シビュラシステム",
                    value_type=ConfigValueType.STR,
                )
            )
            session.commit()
        finally:
            session.close()

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        captured: dict = {}

        def fake_open_slack_modal(trigger_id, view):
            captured["trigger_id"] = trigger_id
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.command._open_slack_modal", fake_open_slack_modal)

        result = await process_config(
            {
                "user_id": "U_TEST",
                "trigger_id": "TRIGGER_TEST",
                "channel_id": "C_TEST",
            }
        )

        assert result["status"] == "success"
        assert captured["trigger_id"] == "TRIGGER_TEST"
        blocks = captured["view"]["blocks"]
        coach_block = next(
            (b for b in blocks if b.get("block_id") == "COACH_CHARACTOR"),
            None,
        )
        assert coach_block is not None
        assert coach_block["element"]["initial_value"] == "シビュラシステム"

    @pytest.mark.asyncio
    async def test_config_submit_saves_charactor(self, tmp_path, monkeypatch):
        db_path = tmp_path / "config_submit.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        payload = {
            "type": "view_submission",
            "user": {"id": "U_TEST"},
            "view": {
                "callback_id": "config_submit",
                "state": {
                    "values": {
                        "COACH_CHARACTOR": {
                            "COACH_CHARACTOR_input": {
                                "type": "plain_text_input",
                                "value": "ラムちゃん",
                            }
                        }
                    }
                },
            },
        }

        result = await process_config(payload)
        assert result["response_action"] == "clear"

        session = session_factory()
        try:
            row = (
                session.query(Configuration)
                .filter(
                    Configuration.user_id == "U_TEST",
                    Configuration.key == "COACH_CHARACTOR",
                )
                .first()
            )
            assert row is not None
            assert row.value == "ラムちゃん"
        finally:
            session.close()

    @pytest.mark.asyncio
    async def test_config_submit_saves_notification_pavlok_settings(self, tmp_path, monkeypatch):
        db_path = tmp_path / "config_submit_notion.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        payload = {
            "type": "view_submission",
            "user": {"id": "U_TEST"},
            "view": {
                "callback_id": "config_submit",
                "state": {
                    "values": {
                        "PAVLOK_TYPE_NOTION": {
                            "PAVLOK_TYPE_NOTION_select": {
                                "type": "static_select",
                                "selected_option": {"value": "beep"},
                            }
                        },
                        "PAVLOK_VALUE_NOTION": {
                            "PAVLOK_VALUE_NOTION_input": {
                                "type": "plain_text_input",
                                "value": "80",
                            }
                        },
                    }
                },
            },
        }

        result = await process_config(payload)
        assert result["response_action"] == "clear"

        session = session_factory()
        try:
            rows = session.query(Configuration).filter(Configuration.user_id == "U_TEST").all()
            config_map = {row.key: row.value for row in rows}
            assert config_map["PAVLOK_TYPE_NOTION"] == "beep"
            assert config_map["PAVLOK_VALUE_NOTION"] == "80"
        finally:
            session.close()

    @pytest.mark.asyncio
    async def test_config_submit_rejects_notification_value_out_of_range(self):
        payload = {
            "type": "view_submission",
            "user": {"id": "U_TEST"},
            "view": {
                "callback_id": "config_submit",
                "state": {
                    "values": {
                        "PAVLOK_VALUE_NOTION": {
                            "PAVLOK_VALUE_NOTION_input": {
                                "type": "plain_text_input",
                                "value": "101",
                            }
                        }
                    }
                },
            },
        }

        result = await process_config(payload)
        assert result["response_action"] == "errors"
        assert result["errors"]["PAVLOK_VALUE_NOTION"] == "100以下で入力してください。"

    @pytest.mark.asyncio
    async def test_config_submit_updates_legacy_lowercase_value_type_rows(self, tmp_path, monkeypatch):
        db_path = tmp_path / "config_submit_report_legacy_value_type.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        now = datetime.now().isoformat(sep=" ")
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO configurations (
                        id, user_id, key, value, value_type,
                        description, default_value, version, created_at, updated_at
                    ) VALUES (
                        :id, :user_id, :key, :value, :value_type,
                        :description, :default_value, :version, :created_at, :updated_at
                    )
                    """
                ),
                [
                    {
                        "id": "cfg_report_weekday",
                        "user_id": "U_TEST",
                        "key": "REPORT_WEEKDAY",
                        "value": "sat",
                        "value_type": "str",
                        "description": "legacy",
                        "default_value": "sat",
                        "version": 1,
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "id": "cfg_report_time",
                        "user_id": "U_TEST",
                        "key": "REPORT_TIME",
                        "value": "07:00",
                        "value_type": "str",
                        "description": "legacy",
                        "default_value": "07:00",
                        "version": 1,
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        payload = {
            "type": "view_submission",
            "user": {"id": "U_TEST"},
            "view": {
                "callback_id": "config_submit",
                "state": {
                    "values": {
                        "REPORT_WEEKDAY": {
                            "REPORT_WEEKDAY_select": {
                                "type": "static_select",
                                "selected_option": {"value": "mon"},
                            }
                        },
                        "REPORT_TIME": {
                            "REPORT_TIME_time": {
                                "type": "timepicker",
                                "selected_time": "08:30",
                            }
                        },
                    }
                },
            },
        }

        result = await process_config(payload)
        assert result["response_action"] == "clear"

        session = session_factory()
        try:
            rows = (
                session.query(Configuration)
                .filter(
                    Configuration.user_id == "U_TEST",
                    Configuration.key.in_(["REPORT_WEEKDAY", "REPORT_TIME"]),
                )
                .all()
            )
            assert len(rows) == 2
            row_map = {row.key: row for row in rows}
            assert row_map["REPORT_WEEKDAY"].value == "mon"
            assert row_map["REPORT_WEEKDAY"].value_type == ConfigValueType.STR
            assert row_map["REPORT_TIME"].value == "08:30"
            assert row_map["REPORT_TIME"].value_type == ConfigValueType.STR
        finally:
            session.close()
