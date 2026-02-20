# v0.3 Interactive API Tests
import json
import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.api.interactive as interactive_api
from backend.api.interactive import (
    process_plan_submit,
    process_plan_modal_submit,
    process_remind_response,
    process_ignore_response,
    process_commitment_add_row,
    process_commitment_remove_row,
)
from backend.models import (
    Base,
    Schedule,
    Commitment,
    ActionLog,
    ActionResult,
    EventType,
    ScheduleState,
    Punishment,
    PunishmentMode,
    Configuration,
    ConfigValueType,
)
from backend.slack_ui import base_commit_modal
from backend.worker.config_cache import invalidate_config_cache


@pytest.mark.asyncio
class TestInteractiveApi:

    @pytest.mark.asyncio
    async def test_plan_submit(self, v3_db_session, v3_test_data_factory):
        schedule = v3_test_data_factory.create_schedule()

        payload_data = {
            "type": "view_submission",
            "user": {"id": "U03JBULT484"},
            "view": {
                "callback_id": "commitment_submit",
                "state": {
                    "values": {
                        "task_1": {"task": "朝の瞑想", "time": "07:00"},
                        "task_2": {"task": "メールチェック", "time": "09:00"},
                        "task_3": {"task": "振り返り", "time": "22:00"},
                        "next_plan": {"date": "tomorrow", "time": "07:00"}
                    }
                }
            }
        }

        result = await process_plan_submit(payload_data)
        assert result["response_action"] == "clear"

    @pytest.mark.asyncio
    async def test_plan_modal_submit_saves_schedules_and_returns_clear(self, monkeypatch, tmp_path):
        db_path = tmp_path / "plan_submit.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)
        async def _fake_notify_plan_saved(*args, **kwargs):
            return None
        async def _fake_run_agent_call(*args, **kwargs):
            return None
        monkeypatch.setattr("backend.api.interactive._notify_plan_saved", _fake_notify_plan_saved)
        monkeypatch.setattr("backend.api.interactive._run_agent_call", _fake_run_agent_call)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        user_id = "U03JBULT484"
        opened_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PROCESSING,
        )
        session.add(opened_plan)
        old_pending_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() + timedelta(hours=10),
            state=ScheduleState.PENDING,
            comment="old next plan",
        )
        morning_commitment = Commitment(
            user_id=user_id,
            task="朝やる",
            time="06:00:00",
            active=True,
        )
        noon_commitment = Commitment(
            user_id=user_id,
            task="昼やる",
            time="12:00:00",
            active=True,
        )
        session.add_all([morning_commitment, noon_commitment])
        session.flush()
        old_pending_remind = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=morning_commitment.id,
            run_at=datetime.now() + timedelta(hours=2),
            state=ScheduleState.PENDING,
            comment="old remind",
        )
        session.add_all(
            [old_pending_plan, old_pending_remind]
        )
        session.commit()
        opened_plan_id = opened_plan.id
        old_pending_plan_id = old_pending_plan.id
        old_pending_remind_id = old_pending_remind.id
        session.close()

        payload_data = {
            "type": "view_submission",
            "user": {"id": user_id},
            "view": {
                "callback_id": "plan_submit",
                "private_metadata": json.dumps(
                    {
                        "user_id": user_id,
                        "schedule_id": opened_plan_id,
                        "channel_id": "C123456",
                    }
                ),
                "state": {
                    "values": {
                        "task_1_date": {
                            "date": {
                                "selected_option": {
                                    "value": "today",
                                }
                            }
                        },
                        "task_1_time": {
                            "time": {
                                "selected_time": "06:00",
                            }
                        },
                        "task_1_skip": {
                            "skip": {
                                "selected_options": [],
                            }
                        },
                        "task_2_date": {
                            "date": {
                                "selected_option": {
                                    "value": "today",
                                }
                            }
                        },
                        "task_2_time": {
                            "time": {
                                "selected_time": "12:00",
                            }
                        },
                        "task_2_skip": {
                            "skip": {
                                "selected_options": [],
                            }
                        },
                        "next_plan_date": {
                            "date": {
                                "selected_option": {
                                    "value": "tomorrow",
                                }
                            }
                        },
                        "next_plan_time": {
                            "time": {
                                "selected_time": "07:00",
                            }
                        },
                    }
                },
            },
        }

        result = await process_plan_modal_submit(payload_data)
        assert result["response_action"] == "clear"

        session = Session()
        refreshed_opened_plan = session.get(Schedule, opened_plan_id)
        assert refreshed_opened_plan is not None
        assert refreshed_opened_plan.state == ScheduleState.DONE
        old_plan_row = session.get(Schedule, old_pending_plan_id)
        old_remind_row = session.get(Schedule, old_pending_remind_id)
        assert old_plan_row is not None
        assert old_remind_row is not None
        assert old_plan_row.state == ScheduleState.CANCELED
        assert old_remind_row.state == ScheduleState.CANCELED

        remind_schedules = (
            session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.REMIND,
                Schedule.state == ScheduleState.PENDING,
            )
            .all()
        )
        assert len(remind_schedules) == 2
        assert len({r.run_at.date() for r in remind_schedules}) == 1
        assert sorted(r.run_at.strftime("%H:%M:%S") for r in remind_schedules) == [
            "06:00:00",
            "12:00:00",
        ]
        assert all(r.commitment_id for r in remind_schedules)

        next_plan_schedules = (
            session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.PLAN,
                Schedule.state == ScheduleState.PENDING,
            )
            .all()
        )
        assert len(next_plan_schedules) == 1
        session.close()

    @pytest.mark.asyncio
    async def test_plan_modal_submit_uses_plan_rows_metadata_mapping(self, monkeypatch, tmp_path):
        db_path = tmp_path / "plan_submit_metadata.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        async def _fake_notify_plan_saved(*args, **kwargs):
            return None

        async def _fake_run_agent_call(*args, **kwargs):
            return None

        monkeypatch.setattr("backend.api.interactive._notify_plan_saved", _fake_notify_plan_saved)
        monkeypatch.setattr("backend.api.interactive._run_agent_call", _fake_run_agent_call)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        user_id = "U03JBULT484"
        commitment_1 = Commitment(
            user_id=user_id,
            task="朝やる",
            time="06:00:00",
            active=False,
        )
        commitment_2 = Commitment(
            user_id=user_id,
            task="昼やる",
            time="12:00:00",
            active=False,
        )
        session.add_all([commitment_1, commitment_2])
        session.commit()
        commitment_1_id = str(commitment_1.id)
        commitment_2_id = str(commitment_2.id)
        session.close()

        payload_data = {
            "type": "view_submission",
            "user": {"id": user_id},
            "view": {
                "callback_id": "plan_submit",
                "private_metadata": json.dumps(
                    {
                        "user_id": user_id,
                        "plan_rows": [
                            {"index": 1, "commitment_id": commitment_1_id, "task": "朝やる"},
                            {"index": 2, "commitment_id": commitment_2_id, "task": "昼やる"},
                        ],
                    }
                ),
                "state": {
                    "values": {
                        "task_1_date": {
                            "date": {
                                "selected_option": {
                                    "value": "today",
                                }
                            }
                        },
                        "task_1_time": {
                            "time": {
                                "selected_time": "06:00",
                            }
                        },
                        "task_1_skip": {
                            "skip": {
                                "selected_options": [],
                            }
                        },
                        "task_2_date": {
                            "date": {
                                "selected_option": {
                                    "value": "today",
                                }
                            }
                        },
                        "task_2_time": {
                            "time": {
                                "selected_time": "12:00",
                            }
                        },
                        "task_2_skip": {
                            "skip": {
                                "selected_options": [],
                            }
                        },
                        "next_plan_date": {
                            "date": {
                                "selected_option": {
                                    "value": "tomorrow",
                                }
                            }
                        },
                        "next_plan_time": {
                            "time": {
                                "selected_time": "07:00",
                            }
                        },
                    }
                },
            },
        }

        result = await process_plan_modal_submit(payload_data)
        assert result["response_action"] == "clear"

        session = Session()
        remind_schedules = (
            session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.REMIND,
                Schedule.state == ScheduleState.PENDING,
            )
            .order_by(Schedule.run_at.asc())
            .all()
        )
        assert len(remind_schedules) == 2
        assert [str(s.commitment_id) for s in remind_schedules] == [
            commitment_1_id,
            commitment_2_id,
        ]
        session.close()

    @pytest.mark.asyncio
    async def test_plan_modal_submit_records_skip_to_action_logs(self, monkeypatch, tmp_path):
        db_path = tmp_path / "plan_skip.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)
        async def _fake_notify_plan_saved(*args, **kwargs):
            return None
        async def _fake_run_agent_call(*args, **kwargs):
            return None
        monkeypatch.setattr("backend.api.interactive._notify_plan_saved", _fake_notify_plan_saved)
        monkeypatch.setattr("backend.api.interactive._run_agent_call", _fake_run_agent_call)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        user_id = "U03JBULT484"
        opened_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PROCESSING,
        )
        session.add(opened_plan)
        session.add_all(
            [
                Commitment(user_id=user_id, task="朝やる", time="06:00:00", active=True),
                Commitment(user_id=user_id, task="昼やる", time="12:00:00", active=True),
            ]
        )
        session.commit()
        opened_plan_id = opened_plan.id
        session.close()

        payload_data = {
            "type": "view_submission",
            "user": {"id": user_id},
            "view": {
                "callback_id": "plan_submit",
                "private_metadata": json.dumps(
                    {
                        "user_id": user_id,
                        "schedule_id": opened_plan_id,
                    }
                ),
                "state": {
                    "values": {
                        "task_1_date": {
                            "date": {
                                "selected_option": {
                                    "value": "today",
                                }
                            }
                        },
                        "task_1_time": {
                            "time": {
                                "selected_time": "06:00",
                            }
                        },
                        "task_1_skip": {
                            "skip": {
                                "selected_options": [
                                    {"value": "skip"},
                                ],
                            }
                        },
                        "task_2_date": {
                            "date": {
                                "selected_option": {
                                    "value": "today",
                                }
                            }
                        },
                        "task_2_time": {
                            "time": {
                                "selected_time": "12:00",
                            }
                        },
                        "task_2_skip": {
                            "skip": {
                                "selected_options": [],
                            }
                        },
                        "next_plan_date": {
                            "date": {
                                "selected_option": {
                                    "value": "tomorrow",
                                }
                            }
                        },
                        "next_plan_time": {
                            "time": {
                                "selected_time": "07:00",
                            }
                        },
                    }
                },
            },
        }

        result = await process_plan_modal_submit(payload_data)
        assert result["response_action"] == "clear"

        session = Session()
        skipped_logs = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == opened_plan_id,
                ActionLog.result == ActionResult.NO,
            )
            .all()
        )
        assert len(skipped_logs) == 1

        remind_pending = (
            session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.REMIND,
                Schedule.state == ScheduleState.PENDING,
            )
            .all()
        )
        assert len(remind_pending) == 1
        session.close()

    @pytest.mark.asyncio
    async def test_remind_response_yes(self, monkeypatch, tmp_path):
        db_path = tmp_path / "remind_yes.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)
        async def _fake_notify_remind_result(*args, **kwargs):
            return None
        monkeypatch.setattr(
            "backend.api.interactive._notify_remind_result",
            _fake_notify_remind_result,
        )

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        user_id = "U03JBULT484"
        run_at = datetime.now().replace(microsecond=0)
        commitment = Commitment(
            user_id=user_id,
            task="朝のジム",
            time=run_at.strftime("%H:%M:%S"),
            active=True,
        )
        session.add(commitment)
        session.flush()
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
            comment="朝のジム",
        )
        session.add(schedule)
        session.commit()
        schedule_id = schedule.id
        session.close()

        payload_data = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [{"action_id": "remind_yes", "value": f'{{"schedule_id": "{schedule_id}"}}'}],
            "container": {"channel_id": "C123"},
        }

        result = await process_remind_response(payload_data, "YES")
        assert result["status"] == "success"
        assert result.get("detail") == "やりました！"
        assert result.get("response_type") == "ephemeral"
        assert result.get("replace_original") is False

        session = Session()
        refreshed = session.get(Schedule, schedule_id)
        assert refreshed is not None
        assert refreshed.state == ScheduleState.DONE
        yes_count = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule_id,
                ActionLog.result == ActionResult.YES,
            )
            .count()
        )
        assert yes_count == 1
        session.close()

    @pytest.mark.asyncio
    async def test_remind_response_no(self, monkeypatch, tmp_path):
        db_path = tmp_path / "remind_no.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)
        async def _fake_notify_remind_result(*args, **kwargs):
            return None
        monkeypatch.setattr(
            "backend.api.interactive._notify_remind_result",
            _fake_notify_remind_result,
        )
        async def _fake_no_punishment(*args, **kwargs):
            return None
        monkeypatch.setattr("backend.api.interactive._send_no_punishment", _fake_no_punishment)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        user_id = "U03JBULT484"
        run_at = datetime.now().replace(microsecond=0)
        commitment = Commitment(
            user_id=user_id,
            task="朝のジム",
            time=run_at.strftime("%H:%M:%S"),
            active=True,
        )
        session.add(commitment)
        session.flush()
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
            comment="朝のジム",
        )
        session.add(schedule)
        session.commit()
        schedule_id = schedule.id
        session.close()

        payload_data = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [{"action_id": "remind_no", "value": f'{{"schedule_id": "{schedule_id}"}}'}],
            "container": {"channel_id": "C123"},
        }

        result = await process_remind_response(payload_data, "NO")
        assert result["status"] == "success"
        assert result.get("detail") == "できませんでした..."
        assert result.get("response_type") == "ephemeral"
        assert result.get("replace_original") is False

        session = Session()
        refreshed = session.get(Schedule, schedule_id)
        assert refreshed is not None
        assert refreshed.state == ScheduleState.DONE
        no_count = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule_id,
                ActionLog.result == ActionResult.NO,
            )
            .count()
        )
        assert no_count == 1
        no_punishments = (
            session.query(Punishment)
            .filter(
                Punishment.schedule_id == schedule_id,
                Punishment.mode == PunishmentMode.NO,
                Punishment.count == 1,
            )
            .count()
        )
        assert no_punishments == 1
        session.close()

    @pytest.mark.asyncio
    async def test_remind_response_reply_uses_commitment_task_name(self, monkeypatch, tmp_path):
        db_path = tmp_path / "remind_task_name.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        captured: dict[str, str] = {}

        async def _fake_notify_remind_result(
            channel_id,
            user_id,
            thread_ts,
            text,
            blocks,
            reason_text="",
        ):
            captured["text"] = text

        monkeypatch.setattr(
            "backend.api.interactive._notify_remind_result",
            _fake_notify_remind_result,
        )

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        user_id = "U03JBULT484"
        run_at = datetime(2026, 2, 16, 7, 0, 0)
        session = Session()
        commitment = Commitment(
            user_id=user_id,
            task="ジム行く",
            time="07:00:00",
            active=True,
        )
        session.add(commitment)
        session.flush()
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
            comment="これはリマインド本文",
        )
        session.add(schedule)
        session.commit()
        schedule_id = schedule.id
        session.close()

        payload_data = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [{"action_id": "remind_yes", "value": f'{{"schedule_id": "{schedule_id}"}}'}],
            "container": {"channel_id": "C123"},
        }

        result = await process_remind_response(payload_data, "YES")
        assert result["status"] == "success"
        await asyncio.sleep(0)

        assert "text" in captured
        assert "ジム行く" in captured["text"]
        assert "これはリマインド本文" not in captured["text"]

    @pytest.mark.asyncio
    async def test_remind_response_first_click_wins(self, monkeypatch, tmp_path):
        db_path = tmp_path / "remind_first_wins.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)
        async def _fake_notify_remind_result(*args, **kwargs):
            return None
        monkeypatch.setattr(
            "backend.api.interactive._notify_remind_result",
            _fake_notify_remind_result,
        )
        async def _fake_no_punishment(*args, **kwargs):
            return None
        monkeypatch.setattr("backend.api.interactive._send_no_punishment", _fake_no_punishment)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        user_id = "U03JBULT484"
        run_at = datetime.now().replace(microsecond=0)
        commitment = Commitment(
            user_id=user_id,
            task="朝のジム",
            time=run_at.strftime("%H:%M:%S"),
            active=True,
        )
        session.add(commitment)
        session.flush()
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
            comment="朝のジム",
        )
        session.add(schedule)
        session.commit()
        schedule_id = schedule.id
        session.close()

        yes_payload = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [{"action_id": "remind_yes", "value": f'{{"schedule_id": "{schedule_id}"}}'}],
            "container": {"channel_id": "C123"},
        }
        no_payload = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [{"action_id": "remind_no", "value": f'{{"schedule_id": "{schedule_id}"}}'}],
            "container": {"channel_id": "C123"},
        }

        first = await process_remind_response(yes_payload, "YES")
        second = await process_remind_response(no_payload, "NO")

        assert first["status"] == "success"
        assert first.get("detail") == "やりました！"
        assert second["status"] == "success"
        assert second.get("detail") == "すでに応答済みです。"

        session = Session()
        refreshed = session.get(Schedule, schedule_id)
        assert refreshed is not None
        assert refreshed.state == ScheduleState.DONE
        yes_count = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule_id,
                ActionLog.result == ActionResult.YES,
            )
            .count()
        )
        no_count = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule_id,
                ActionLog.result == ActionResult.NO,
            )
            .count()
        )
        assert yes_count == 1
        assert no_count == 0
        session.close()

    @pytest.mark.asyncio
    async def test_send_no_punishment_sends_when_daily_limit_not_exceeded(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "send_no_punishment_limit_ok.sqlite3"
        database_url = f"sqlite:///{db_path}"
        invalidate_config_cache()
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        user_id = "U03JBULT484"
        session = Session()
        session.add(
            Configuration(
                user_id=user_id,
                key="LIMIT_DAY_PAVLOK_COUNTS",
                value="1",
                value_type=ConfigValueType.INT,
            )
        )
        run_at = datetime.now().replace(microsecond=0)
        commitment = Commitment(
            user_id=user_id,
            task="タスク",
            time=run_at.strftime("%H:%M:%S"),
            active=True,
        )
        session.add(commitment)
        session.flush()
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at,
            state=ScheduleState.DONE,
        )
        session.add(schedule)
        session.flush()
        session.add(
            Punishment(
                schedule_id=schedule.id,
                mode=PunishmentMode.NO,
                count=1,
            )
        )
        session.commit()
        schedule_id = schedule.id
        session.close()

        calls: list[tuple[str, int, str]] = []

        class _FakePavlokClient:
            def stimulate(self, stimulus_type: str, value: int, reason: str = ""):
                calls.append((stimulus_type, value, reason))
                return {"success": True}

        monkeypatch.setattr("backend.pavlok_lib.PavlokClient", _FakePavlokClient)

        await interactive_api._send_no_punishment(
            user_id=user_id,
            schedule_id=schedule_id,
            punishment={"type": "zap", "value": 45},
        )

        assert calls == [("zap", 45, "remind: タスク")]

    @pytest.mark.asyncio
    async def test_send_no_punishment_skips_when_daily_limit_exceeded(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "send_no_punishment_limit_exceeded.sqlite3"
        database_url = f"sqlite:///{db_path}"
        invalidate_config_cache()
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        user_id = "U03JBULT484"
        session = Session()
        session.add(
            Configuration(
                user_id=user_id,
                key="LIMIT_DAY_PAVLOK_COUNTS",
                value="1",
                value_type=ConfigValueType.INT,
            )
        )
        run_at = datetime.now().replace(microsecond=0)
        commitment = Commitment(
            user_id=user_id,
            task="タスク",
            time=run_at.strftime("%H:%M:%S"),
            active=True,
        )
        session.add(commitment)
        session.flush()
        schedule1 = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at,
            state=ScheduleState.DONE,
        )
        schedule2 = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=run_at + timedelta(minutes=1),
            state=ScheduleState.DONE,
        )
        session.add_all([schedule1, schedule2])
        session.flush()
        session.add_all(
            [
                Punishment(
                    schedule_id=schedule1.id,
                    mode=PunishmentMode.NO,
                    count=1,
                ),
                Punishment(
                    schedule_id=schedule2.id,
                    mode=PunishmentMode.NO,
                    count=1,
                ),
            ]
        )
        session.commit()
        schedule2_id = schedule2.id
        session.close()

        calls: list[tuple[str, int, str]] = []

        class _FakePavlokClient:
            def stimulate(self, stimulus_type: str, value: int, reason: str = ""):
                calls.append((stimulus_type, value, reason))
                return {"success": True}

        monkeypatch.setattr("backend.pavlok_lib.PavlokClient", _FakePavlokClient)

        await interactive_api._send_no_punishment(
            user_id=user_id,
            schedule_id=schedule2_id,
            punishment={"type": "zap", "value": 55},
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_ignore_response_yes(self, v3_db_session, v3_test_data_factory):
        schedule = v3_test_data_factory.create_schedule()

        action_log = ActionLog(
            schedule_id=schedule.id,
            result=ActionResult.YES
        )
        v3_db_session.add(action_log)
        v3_db_session.commit()

        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "ignore_yes", "value": f'{{"schedule_id": "{schedule.id}"}}'}]
        }

        result = await process_ignore_response(payload_data)
        assert result["status"] == "success"
        assert result.get("detail") == "今やりました"

    @pytest.mark.asyncio
    async def test_ignore_response_no(self, v3_db_session, v3_test_data_factory):
        schedule = v3_test_data_factory.create_schedule()

        action_log = ActionLog(
            schedule_id=schedule.id,
            result=ActionResult.NO
        )
        v3_db_session.add(action_log)
        v3_db_session.commit()

        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "ignore_no", "value": f'{{"schedule_id": "{schedule.id}"}}'}]
        }

        result = await process_ignore_response(payload_data)
        assert result["status"] == "success"
        assert result.get("detail") == "やっぱり..."

    @pytest.mark.asyncio
    async def test_commitment_add_row_updates_modal(self):
        modal = base_commit_modal([])
        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "commitment_add_row"}],
            "view": {
                **modal,
                "state": {
                    "values": {
                        "commitment_1": {"task_1": {"type": "plain_text_input", "value": "朝の瞑想"}},
                        "time_1": {"time_1": {"type": "timepicker", "selected_time": "07:00"}},
                        "commitment_2": {"task_2": {"type": "plain_text_input", "value": ""}},
                        "time_2": {"time_2": {"type": "timepicker", "selected_time": None}},
                        "commitment_3": {"task_3": {"type": "plain_text_input", "value": ""}},
                        "time_3": {"time_3": {"type": "timepicker", "selected_time": None}},
                    }
                },
            },
        }

        result = await process_commitment_add_row(payload_data)
        assert result["response_action"] == "update"
        updated_view = result["view"]
        task_blocks = [
            b for b in updated_view["blocks"]
            if b.get("block_id", "").startswith("commitment_")
        ]
        assert len(task_blocks) == 4

    @pytest.mark.asyncio
    async def test_commitment_add_row_stops_at_max(self):
        commitments = [{"task": f"task-{i}", "time": "07:00"} for i in range(1, 11)]
        modal = base_commit_modal(commitments)
        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "commitment_add_row"}],
            "view": {
                **modal,
                "state": {"values": {}},
            },
        }

        result = await process_commitment_add_row(payload_data)
        updated_view = result["view"]
        task_blocks = [
            b for b in updated_view["blocks"]
            if b.get("block_id", "").startswith("commitment_")
        ]
        assert len(task_blocks) == 10

    @pytest.mark.asyncio
    async def test_commitment_remove_row_updates_modal(self):
        commitments = [{"task": f"task-{i}", "time": "07:00"} for i in range(1, 5)]
        modal = base_commit_modal(commitments)
        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "commitment_remove_row"}],
            "view": {
                **modal,
                "state": {"values": {}},
            },
        }

        result = await process_commitment_remove_row(payload_data)
        assert result["response_action"] == "update"
        updated_view = result["view"]
        task_blocks = [
            b for b in updated_view["blocks"]
            if b.get("block_id", "").startswith("commitment_")
        ]
        assert len(task_blocks) == 3

    @pytest.mark.asyncio
    async def test_commitment_remove_row_keeps_min_rows(self):
        modal = base_commit_modal([])
        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "commitment_remove_row"}],
            "view": {
                **modal,
                "state": {"values": {}},
            },
        }

        result = await process_commitment_remove_row(payload_data)
        updated_view = result["view"]
        task_blocks = [
            b for b in updated_view["blocks"]
            if b.get("block_id", "").startswith("commitment_")
        ]
        assert len(task_blocks) == 3
