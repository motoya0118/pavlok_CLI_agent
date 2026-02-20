# v0.3 Slack Command API Tests
import json
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.api.command import (
    process_base_commit,
    process_plan,
    process_stop,
    process_restart,
    process_help,
    process_config
)
from backend.models import (
    Schedule,
    Base,
    Commitment,
    Configuration,
    ConfigValueType,
    EventType,
    ScheduleState,
)


@pytest.mark.asyncio
class TestCommandApi:

    async def test_base_commit_command(self, v3_db_session, v3_test_data_factory):
        schedule = v3_test_data_factory.create_schedule()
        request = MagicMock(spec=Request)
        request.state = "base_commit"

        result = await process_base_commit(request)
        assert result["status"] == "success"
        assert "blocks" in result

    @pytest.mark.asyncio
    async def test_base_commit_prefills_existing_commitments(self, tmp_path, monkeypatch):
        db_path = tmp_path / "prefill.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = Session()
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
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = Session()
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
    async def test_stop_command(self, tmp_path, monkeypatch):
        db_path = tmp_path / "stop_command.db"
        database_url = f"sqlite:///{db_path}"
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        result = await process_stop({"user_id": "U_TEST"})
        assert result["status"] == "success"
        assert "blocks" in result

        session = Session()
        try:
            row = (
                session.query(Configuration)
                .filter(Configuration.key == "SYSTEM_PAUSED")
                .first()
            )
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
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.command._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.command._SESSION_DB_URL", None)

        session = Session()
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

        session = Session()
        try:
            row = (
                session.query(Configuration)
                .filter(Configuration.key == "SYSTEM_PAUSED")
                .first()
            )
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
        config_data = {
            "PAVLOK_TYPE_PUNISH": "vibe",
            "PAVLOK_VALUE_PUNISH": "100"
        }

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
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = Session()
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
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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

        session = Session()
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
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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

        session = Session()
        try:
            rows = (
                session.query(Configuration)
                .filter(Configuration.user_id == "U_TEST")
                .all()
            )
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
