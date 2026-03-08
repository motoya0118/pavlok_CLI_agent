# v0.3 Interactive API Tests
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.api.interactive as interactive_api
from backend.api.interactive import (
    process_calorie_submit,
    process_commitment_add_row,
    process_commitment_remove_row,
    process_ignore_response,
    process_plan_modal_submit,
    process_plan_open_modal,
    process_plan_submit,
    process_remind_response,
    process_report_read_response,
)
from backend.models import (
    ActionLog,
    ActionResult,
    Base,
    CalorieRecord,
    Commitment,
    Configuration,
    ConfigValueType,
    EventType,
    Punishment,
    PunishmentMode,
    ReportDelivery,
    Schedule,
    ScheduleState,
    serialize_report_input_value,
)
from backend.slack_ui import base_commit_modal
from backend.worker.config_cache import invalidate_config_cache


async def _wait_until(predicate, timeout: float = 1.0, interval: float = 0.01) -> bool:
    """Wait until predicate returns True or timeout expires."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


@pytest.mark.asyncio
class TestInteractiveApi:
    @pytest.mark.asyncio
    async def test_plan_submit(self, monkeypatch, tmp_path):
        db_path = tmp_path / "plan_submit_legacy.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)

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
                        "next_plan": {"date": "tomorrow", "time": "07:00"},
                    }
                },
            },
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
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
        session.add_all([old_pending_plan, old_pending_remind])
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

        session = session_factory()
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
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

        session = session_factory()
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
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

        session = session_factory()
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
    async def test_plan_modal_submit_upserts_pending_report(self, monkeypatch, tmp_path):
        db_path = tmp_path / "plan_report_upsert.sqlite3"
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        opened_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PROCESSING,
        )
        session.add(opened_plan)
        session.add(
            Commitment(user_id=user_id, task="朝やる", time="06:00:00", active=True),
        )
        pending_report = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=datetime.now().replace(hour=6, minute=0, second=0, microsecond=0),
            state=ScheduleState.PENDING,
            retry_count=0,
            comment="report",
            input_value=serialize_report_input_value(
                ui_date="today",
                ui_time="06:00",
                updated_at="2026-03-05T06:00:00",
            ),
        )
        session.add(pending_report)
        session.commit()
        opened_plan_id = opened_plan.id
        pending_report_id = pending_report.id
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
                        "report_date": {
                            "date": {
                                "selected_option": {
                                    "value": "tomorrow",
                                }
                            }
                        },
                        "report_time": {
                            "time": {
                                "selected_time": "08:45",
                            }
                        },
                    }
                },
            },
        }

        result = await process_plan_modal_submit(payload_data)
        assert result["response_action"] == "clear"

        session = session_factory()
        reports = (
            session.query(Schedule)
            .filter(
                Schedule.user_id == user_id,
                Schedule.event_type == EventType.REPORT,
                Schedule.state == ScheduleState.PENDING,
            )
            .all()
        )
        assert len(reports) == 1
        assert reports[0].id == pending_report_id
        assert reports[0].run_at.strftime("%H:%M:%S") == "08:45:00"
        parsed = reports[0].get_report_input_value()
        assert parsed is not None
        assert parsed["ui_date"] == "tomorrow"
        assert parsed["ui_time"] == "08:45"
        assert parsed["updated_at"]
        session.close()

    @pytest.mark.asyncio
    async def test_plan_modal_submit_without_report_fields_keeps_pending_report(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "plan_report_keep.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        notified: dict[str, Any] = {}

        async def _fake_notify_plan_saved(*args, **kwargs):
            notified.update(kwargs)
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        opened_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PROCESSING,
        )
        session.add(opened_plan)
        session.add(
            Commitment(user_id=user_id, task="朝やる", time="06:00:00", active=True),
        )
        original_run_at = (datetime.now() + timedelta(days=1)).replace(
            hour=6, minute=30, second=0, microsecond=0
        )
        original_input_value = serialize_report_input_value(
            ui_date="tomorrow",
            ui_time="06:30",
            updated_at="2026-03-05T06:30:00",
        )
        pending_report = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=original_run_at,
            state=ScheduleState.PENDING,
            retry_count=0,
            comment="report",
            input_value=original_input_value,
        )
        session.add(pending_report)
        session.commit()
        opened_plan_id = opened_plan.id
        pending_report_id = pending_report.id
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

        session = session_factory()
        report = session.get(Schedule, pending_report_id)
        assert report is not None
        assert report.state == ScheduleState.PENDING
        assert report.run_at == original_run_at
        assert report.input_value == original_input_value
        session.close()

        await asyncio.sleep(0)
        report_plan = notified.get("report_plan")
        assert report_plan is None

    @pytest.mark.asyncio
    async def test_plan_modal_submit_wash_does_not_cancel_processing_report(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "plan_report_wash.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        notified: dict[str, Any] = {}

        async def _fake_notify_plan_saved(*args, **kwargs):
            notified.update(kwargs)
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        opened_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PROCESSING,
        )
        old_pending_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() + timedelta(hours=2),
            state=ScheduleState.PENDING,
        )
        commitment = Commitment(user_id=user_id, task="朝やる", time="06:00:00", active=True)
        session.add_all([opened_plan, old_pending_plan, commitment])
        session.flush()
        old_pending_remind = Schedule(
            user_id=user_id,
            event_type=EventType.REMIND,
            commitment_id=commitment.id,
            run_at=datetime.now() + timedelta(hours=1),
            state=ScheduleState.PENDING,
        )
        processing_report = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=datetime.now() + timedelta(hours=3),
            state=ScheduleState.PROCESSING,
            input_value=serialize_report_input_value("today", "07:00", "2026-03-05T07:00:00"),
        )
        session.add_all([old_pending_remind, processing_report])
        session.commit()
        opened_plan_id = opened_plan.id
        old_pending_plan_id = old_pending_plan.id
        old_pending_remind_id = old_pending_remind.id
        processing_report_id = processing_report.id
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

        session = session_factory()
        old_plan_row = session.get(Schedule, old_pending_plan_id)
        old_remind_row = session.get(Schedule, old_pending_remind_id)
        report_row = session.get(Schedule, processing_report_id)
        assert old_plan_row is not None
        assert old_remind_row is not None
        assert report_row is not None
        assert old_plan_row.state == ScheduleState.CANCELED
        assert old_remind_row.state == ScheduleState.CANCELED
        assert report_row.state == ScheduleState.PROCESSING
        session.close()

        await asyncio.sleep(0)
        report_plan = notified.get("report_plan")
        assert report_plan is None

    @pytest.mark.asyncio
    async def test_plan_modal_submit_without_report_fields_hides_done_report_from_message(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "plan_report_done_for_message.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        notified: dict[str, Any] = {}

        async def _fake_notify_plan_saved(*args, **kwargs):
            notified.update(kwargs)
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        opened_plan = Schedule(
            user_id=user_id,
            event_type=EventType.PLAN,
            run_at=datetime.now() - timedelta(minutes=1),
            state=ScheduleState.PROCESSING,
        )
        done_report_run_at = datetime.now().replace(second=0, microsecond=0)
        done_report = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=done_report_run_at,
            state=ScheduleState.DONE,
            retry_count=0,
            comment="report",
            thread_ts="1710000000.000001",
            input_value=serialize_report_input_value(
                ui_date="today",
                ui_time=done_report_run_at.strftime("%H:%M"),
                updated_at=done_report_run_at.isoformat(timespec="seconds"),
            ),
        )
        session.add_all(
            [
                opened_plan,
                done_report,
                Commitment(user_id=user_id, task="朝やる", time="06:00:00", active=True),
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

        await asyncio.sleep(0)
        report_plan = notified.get("report_plan")
        assert report_plan is None

    @pytest.mark.asyncio
    async def test_plan_open_modal_includes_report_input_from_config(self, monkeypatch, tmp_path):
        db_path = tmp_path / "plan_open_modal_report.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        now = datetime.now()
        weekday_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
        today_token = weekday_map[now.weekday()]

        session = session_factory()
        user_id = "U03JBULT484"
        session.add(Commitment(user_id=user_id, task="朝やる", time="06:00:00", active=True))
        session.add(
            Configuration(
                user_id=user_id,
                key="REPORT_WEEKDAY",
                value=today_token,
                value_type=ConfigValueType.STR,
            )
        )
        session.add(
            Configuration(
                user_id=user_id,
                key="REPORT_TIME",
                value="06:30",
                value_type=ConfigValueType.STR,
            )
        )
        session.commit()
        session.close()

        captured: dict = {}

        def _fake_open_slack_modal(trigger_id: str, view: dict):
            captured["trigger_id"] = trigger_id
            captured["view"] = view
            return True, "ok"

        monkeypatch.setattr("backend.api.interactive._open_slack_modal", _fake_open_slack_modal)

        payload_data = {
            "type": "block_actions",
            "trigger_id": "TRIGGER_ID",
            "user": {"id": user_id},
            "container": {"channel_id": "C123"},
            "actions": [{"action_id": "plan_open_modal", "value": '{"schedule_id":"S1"}'}],
        }

        result = await process_plan_open_modal(payload_data)
        assert result["status"] == "success"
        assert captured["trigger_id"] == "TRIGGER_ID"
        blocks = captured["view"]["blocks"]
        report_date = next((b for b in blocks if b.get("block_id") == "report_date"), None)
        report_time = next((b for b in blocks if b.get("block_id") == "report_time"), None)
        assert report_date is not None
        assert report_time is not None
        assert report_date["element"]["initial_option"]["value"] == "today"
        assert report_time["element"]["initial_time"] == "06:30"

    async def test_extract_calorie_file_id_from_state_supports_selected_files(self):
        state_values = {
            "calorie_image": {
                "image": {
                    "type": "file_input",
                    "selected_files": ["F_SELECTED_1"],
                }
            }
        }
        file_id = interactive_api._extract_calorie_file_id_from_state(state_values)
        assert file_id == "F_SELECTED_1"

    @pytest.mark.asyncio
    async def test_calorie_submit_saves_rows_and_notifies(self, monkeypatch, tmp_path):
        db_path = tmp_path / "calorie_submit_success.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("SLACK_BOT_USER_OAUTH_TOKEN", "xoxb-test")
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        notified: list[dict[str, object]] = []

        async def _fake_notify_calorie_result(channel_id, user_id, message, blocks=None):
            notified.append(
                {
                    "channel_id": channel_id,
                    "user_id": user_id,
                    "message": message,
                    "blocks": blocks,
                }
            )

        def _fake_fetch_slack_file_info(file_id: str, bot_token: str):
            assert file_id == "F123"
            assert bot_token == "xoxb-test"
            return {
                "id": file_id,
                "size": 1024,
                "mimetype": "image/jpeg",
                "url_private_download": "https://files.slack.test/F123.jpg",
            }

        def _fake_download_slack_file_bytes(download_url: str, bot_token: str):
            assert download_url.endswith("/F123.jpg")
            assert bot_token == "xoxb-test"
            return b"fake-image-bytes"

        def _fake_analyze_calorie(image_bytes: bytes, mime_type: str):
            assert image_bytes == b"fake-image-bytes"
            assert mime_type == "image/jpeg"
            return (
                {
                    "schema_version": "calorie_v1",
                    "items": [
                        {"food_name": "バナナ", "calorie": 95},
                        {"food_name": None, "calorie": "120"},
                    ],
                    "total_calorie": 215,
                },
                '{"schema_version":"calorie_v1","items":[{"food_name":"バナナ","calorie":95},{"food_name":null,"calorie":120}],"total_calorie":215}',
                "openai",
                "gpt-4o-mini",
            )

        monkeypatch.setattr(
            "backend.api.interactive._notify_calorie_result",
            _fake_notify_calorie_result,
        )
        monkeypatch.setattr(
            "backend.api.interactive._fetch_slack_file_info", _fake_fetch_slack_file_info
        )
        monkeypatch.setattr(
            "backend.api.interactive._download_slack_file_bytes",
            _fake_download_slack_file_bytes,
        )
        monkeypatch.setattr("backend.api.interactive.analyze_calorie", _fake_analyze_calorie)

        payload_data = {
            "type": "view_submission",
            "user": {"id": "U03THHYBETW"},
            "view": {
                "callback_id": "calorie_submit",
                "private_metadata": json.dumps({"channel_id": "C_CAL"}),
                "state": {
                    "values": {
                        "calorie_image": {
                            "calorie_image_input": {
                                "type": "file_input",
                                "files": ["F123"],
                            }
                        }
                    }
                },
            },
        }

        result = await process_calorie_submit(payload_data)
        assert result == {"response_action": "clear"}

        done = await _wait_until(lambda: len(notified) == 1, timeout=1.0)
        assert done is True

        session = session_factory()
        rows = (
            session.query(CalorieRecord)
            .filter(CalorieRecord.user_id == "U03THHYBETW")
            .order_by(CalorieRecord.created_at.asc())
            .all()
        )
        assert len(rows) == 2
        assert [r.food_name for r in rows] == ["バナナ", "不明"]
        assert [r.calorie for r in rows] == [95, 120]
        assert all(r.llm_raw_response_json for r in rows)
        assert all(r.provider == "openai" for r in rows)
        assert all(r.model == "gpt-4o-mini" for r in rows)
        session.close()

        assert len(notified) == 1
        assert notified[0]["channel_id"] == "C_CAL"
        assert notified[0]["user_id"] == "U03THHYBETW"
        assert notified[0]["message"] == "カロリー解析結果を記録しました"
        assert isinstance(notified[0]["blocks"], list)

    @pytest.mark.asyncio
    async def test_calorie_submit_rejects_over_10mb(self, monkeypatch, tmp_path):
        db_path = tmp_path / "calorie_submit_too_large.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("SLACK_BOT_USER_OAUTH_TOKEN", "xoxb-test")
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        notified: list[str] = []
        analyze_called = False

        async def _fake_notify_calorie_result(channel_id, user_id, message, blocks=None):
            notified.append(message)

        def _fake_fetch_slack_file_info(file_id: str, bot_token: str):
            return {
                "id": file_id,
                "size": 10 * 1024 * 1024 + 1,
                "mimetype": "image/png",
                "url_private_download": "https://files.slack.test/F_LARGE.png",
            }

        def _fake_analyze_calorie(image_bytes: bytes, mime_type: str):
            nonlocal analyze_called
            analyze_called = True
            return {}, "{}", "openai", "gpt-4o-mini"

        monkeypatch.setattr(
            "backend.api.interactive._notify_calorie_result",
            _fake_notify_calorie_result,
        )
        monkeypatch.setattr(
            "backend.api.interactive._fetch_slack_file_info", _fake_fetch_slack_file_info
        )
        monkeypatch.setattr("backend.api.interactive.analyze_calorie", _fake_analyze_calorie)

        payload_data = {
            "type": "view_submission",
            "user": {"id": "U03THHYBETW"},
            "view": {
                "callback_id": "calorie_submit",
                "private_metadata": json.dumps({"channel_id": "C_CAL"}),
                "state": {
                    "values": {
                        "calorie_image": {
                            "calorie_image_input": {
                                "type": "file_input",
                                "files": ["F_LARGE"],
                            }
                        }
                    }
                },
            },
        }

        result = await process_calorie_submit(payload_data)
        assert result == {"response_action": "clear"}

        done = await _wait_until(lambda: len(notified) == 1, timeout=1.0)
        assert done is True

        assert analyze_called is False
        assert notified == [
            "画像サイズが大きすぎるので、10MB以下の画像サイズにしてリトライしてください"
        ]

        session = session_factory()
        assert session.query(CalorieRecord).count() == 0
        session.close()

    @pytest.mark.asyncio
    async def test_calorie_submit_parse_error_notifies_user(self, monkeypatch, tmp_path):
        db_path = tmp_path / "calorie_submit_parse_error.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("SLACK_BOT_USER_OAUTH_TOKEN", "xoxb-test")
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        notified: list[str] = []

        async def _fake_notify_calorie_result(channel_id, user_id, message, blocks=None):
            notified.append(message)

        def _fake_fetch_slack_file_info(file_id: str, bot_token: str):
            return {
                "id": file_id,
                "size": 2048,
                "mimetype": "image/png",
                "url_private_download": "https://files.slack.test/F_PARSE.png",
            }

        def _fake_download_slack_file_bytes(download_url: str, bot_token: str):
            return b"fake-image-bytes"

        def _fake_analyze_calorie(image_bytes: bytes, mime_type: str):
            raise interactive_api.CalorieImageParseError("failed to parse image")

        monkeypatch.setattr(
            "backend.api.interactive._notify_calorie_result",
            _fake_notify_calorie_result,
        )
        monkeypatch.setattr(
            "backend.api.interactive._fetch_slack_file_info", _fake_fetch_slack_file_info
        )
        monkeypatch.setattr(
            "backend.api.interactive._download_slack_file_bytes",
            _fake_download_slack_file_bytes,
        )
        monkeypatch.setattr("backend.api.interactive.analyze_calorie", _fake_analyze_calorie)

        payload_data = {
            "type": "view_submission",
            "user": {"id": "U03THHYBETW"},
            "view": {
                "callback_id": "calorie_submit",
                "private_metadata": json.dumps({"channel_id": "C_CAL"}),
                "state": {
                    "values": {
                        "calorie_image": {
                            "calorie_image_input": {
                                "type": "file_input",
                                "files": ["F_PARSE"],
                            }
                        }
                    }
                },
            },
        }

        result = await process_calorie_submit(payload_data)
        assert result == {"response_action": "clear"}

        done = await _wait_until(lambda: len(notified) == 1, timeout=1.0)
        assert done is True

        assert notified == ["画像解析に失敗しました"]
        session = session_factory()
        assert session.query(CalorieRecord).count() == 0
        session.close()

    @pytest.mark.asyncio
    async def test_calorie_submit_non_food_image_notifies_user(self, monkeypatch, tmp_path):
        db_path = tmp_path / "calorie_submit_non_food.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("SLACK_BOT_USER_OAUTH_TOKEN", "xoxb-test")
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        notified: list[str] = []

        async def _fake_notify_calorie_result(channel_id, user_id, message, blocks=None):
            notified.append(message)

        def _fake_fetch_slack_file_info(file_id: str, bot_token: str):
            return {
                "id": file_id,
                "size": 2048,
                "mimetype": "image/png",
                "url_private_download": "https://files.slack.test/F_NON_FOOD.png",
            }

        def _fake_download_slack_file_bytes(download_url: str, bot_token: str):
            return b"fake-image-bytes"

        def _fake_analyze_calorie(image_bytes: bytes, mime_type: str):
            raise interactive_api.CalorieImageParseError("items was empty")

        monkeypatch.setattr(
            "backend.api.interactive._notify_calorie_result",
            _fake_notify_calorie_result,
        )
        monkeypatch.setattr(
            "backend.api.interactive._fetch_slack_file_info", _fake_fetch_slack_file_info
        )
        monkeypatch.setattr(
            "backend.api.interactive._download_slack_file_bytes",
            _fake_download_slack_file_bytes,
        )
        monkeypatch.setattr("backend.api.interactive.analyze_calorie", _fake_analyze_calorie)

        payload_data = {
            "type": "view_submission",
            "user": {"id": "U03THHYBETW"},
            "view": {
                "callback_id": "calorie_submit",
                "private_metadata": json.dumps({"channel_id": "C_CAL"}),
                "state": {
                    "values": {
                        "calorie_image": {
                            "calorie_image_input": {
                                "type": "file_input",
                                "files": ["F_NON_FOOD"],
                            }
                        }
                    }
                },
            },
        }

        result = await process_calorie_submit(payload_data)
        assert result == {"response_action": "clear"}

        done = await _wait_until(lambda: len(notified) == 1, timeout=1.0)
        assert done is True

        assert notified == ["upload画像はカロリー算出不可です。"]
        session = session_factory()
        assert session.query(CalorieRecord).count() == 0
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
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
            "actions": [
                {"action_id": "remind_yes", "value": f'{{"schedule_id": "{schedule_id}"}}'}
            ],
            "container": {"channel_id": "C123"},
        }

        result = await process_remind_response(payload_data, "YES")
        assert result["status"] == "success"
        assert result.get("detail") == "やりました！"
        assert result.get("response_type") == "ephemeral"
        assert result.get("replace_original") is False

        session = session_factory()
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
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

        session = session_factory()
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
        session_factory = sessionmaker(bind=engine)

        user_id = "U03JBULT484"
        run_at = datetime(2026, 2, 16, 7, 0, 0)
        session = session_factory()
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
            "actions": [
                {"action_id": "remind_yes", "value": f'{{"schedule_id": "{schedule_id}"}}'}
            ],
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
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
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
            "actions": [
                {"action_id": "remind_yes", "value": f'{{"schedule_id": "{schedule_id}"}}'}
            ],
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

        session = session_factory()
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
    async def test_report_read_response_first_click_updates_delivery_and_schedule(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "report_read_first.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        notified: dict[str, object] = {}

        async def _fake_notify_report_read_result(
            channel_id, user_id, thread_ts, text, blocks, reason_text=""
        ):
            notified["channel_id"] = channel_id
            notified["user_id"] = user_id
            notified["thread_ts"] = thread_ts
            notified["text"] = text
            notified["blocks"] = blocks
            notified["reason_text"] = reason_text

        monkeypatch.setattr(
            "backend.api.interactive._notify_report_read_result",
            _fake_notify_report_read_result,
        )

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        run_at = datetime.now().replace(microsecond=0)
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
            thread_ts="1700000000.123456",
        )
        session.add(schedule)
        session.flush()
        delivery = ReportDelivery(
            schedule_id=schedule.id,
            user_id=user_id,
            report_type="monthly",
            period_start=datetime(2026, 2, 1).date(),
            period_end=datetime(2026, 2, 28).date(),
            posted_at=run_at,
            read_at=None,
            thread_ts=schedule.thread_ts,
            markdown_table="| 指標 | 値 |",
            llm_comment="comment",
        )
        session.add(delivery)
        session.commit()
        schedule_id = schedule.id
        session.close()

        payload_data = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [
                {"action_id": "report_read", "value": f'{{"schedule_id": "{schedule_id}"}}'}
            ],
            "container": {
                "channel_id": "C_REPORT",
                "thread_ts": "1700000000.123456",
            },
        }

        result = await process_report_read_response(payload_data)
        assert result["status"] == "success"
        assert result.get("detail") == "読みました！"
        assert result.get("response_type") == "ephemeral"
        assert result.get("replace_original") is False

        await asyncio.sleep(0)
        assert notified["channel_id"] == "C_REPORT"
        assert notified["user_id"] == user_id
        assert notified["thread_ts"] == "1700000000.123456"
        assert notified["text"] == "来月も頑張りましょう"
        assert notified["reason_text"] == "report: 月次レポートを確認しました"

        session = session_factory()
        refreshed_schedule = session.get(Schedule, schedule_id)
        refreshed_delivery = (
            session.query(ReportDelivery).filter(ReportDelivery.schedule_id == schedule_id).first()
        )
        read_count = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule_id,
                ActionLog.result == ActionResult.REPORT_READ,
            )
            .count()
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.state == ScheduleState.DONE
        assert refreshed_delivery is not None
        assert refreshed_delivery.read_at is not None
        assert read_count == 1
        session.close()

    @pytest.mark.asyncio
    async def test_report_read_response_second_click_is_ignored(self, monkeypatch, tmp_path):
        db_path = tmp_path / "report_read_second.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        notified_calls = 0

        async def _fake_notify_report_read_result(*args, **kwargs):
            nonlocal notified_calls
            notified_calls += 1

        monkeypatch.setattr(
            "backend.api.interactive._notify_report_read_result",
            _fake_notify_report_read_result,
        )

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        run_at = datetime.now().replace(microsecond=0)
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
        )
        session.add(schedule)
        session.flush()
        session.add(
            ReportDelivery(
                schedule_id=schedule.id,
                user_id=user_id,
                report_type="weekly",
                period_start=datetime(2026, 3, 1).date(),
                period_end=datetime(2026, 3, 7).date(),
                posted_at=run_at,
                read_at=None,
                thread_ts="1700000000.777777",
                markdown_table="| 指標 | 値 |",
                llm_comment=None,
            )
        )
        session.commit()
        schedule_id = schedule.id
        session.close()

        payload_data = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [
                {"action_id": "report_read", "value": f'{{"schedule_id": "{schedule_id}"}}'}
            ],
            "container": {"channel_id": "C_REPORT"},
        }

        first = await process_report_read_response(payload_data)
        second = await process_report_read_response(payload_data)

        assert first["status"] == "success"
        assert first.get("detail") == "読みました！"
        assert second["status"] == "success"
        assert second.get("detail") == "すでに確認済みです。"

        await asyncio.sleep(0)
        assert notified_calls == 1

        session = session_factory()
        refreshed_delivery = (
            session.query(ReportDelivery).filter(ReportDelivery.schedule_id == schedule_id).first()
        )
        read_at = refreshed_delivery.read_at if refreshed_delivery is not None else None
        read_count = (
            session.query(ActionLog)
            .filter(
                ActionLog.schedule_id == schedule_id,
                ActionLog.result == ActionResult.REPORT_READ,
            )
            .count()
        )
        assert read_at is not None
        assert read_count == 1
        session.close()

    @pytest.mark.asyncio
    async def test_report_read_response_second_click_backfills_read_at_if_missing(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "report_read_backfill.sqlite3"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setattr("backend.api.interactive._SESSION_FACTORY", None)
        monkeypatch.setattr("backend.api.interactive._SESSION_DB_URL", None)

        notified_calls = 0

        async def _fake_notify_report_read_result(*args, **kwargs):
            nonlocal notified_calls
            notified_calls += 1

        monkeypatch.setattr(
            "backend.api.interactive._notify_report_read_result",
            _fake_notify_report_read_result,
        )

        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)

        session = session_factory()
        user_id = "U03JBULT484"
        run_at = datetime.now().replace(microsecond=0)
        schedule = Schedule(
            user_id=user_id,
            event_type=EventType.REPORT,
            run_at=run_at,
            state=ScheduleState.PROCESSING,
        )
        session.add(schedule)
        session.flush()
        session.add(
            ReportDelivery(
                schedule_id=schedule.id,
                user_id=user_id,
                report_type="weekly",
                period_start=datetime(2026, 3, 1).date(),
                period_end=datetime(2026, 3, 7).date(),
                posted_at=run_at,
                read_at=None,
                thread_ts="1700000000.777777",
                markdown_table="| 指標 | 値 |",
                llm_comment=None,
            )
        )
        session.add(
            ActionLog(
                schedule_id=schedule.id,
                result=ActionResult.REPORT_READ,
            )
        )
        session.commit()
        schedule_id = schedule.id
        session.close()

        payload_data = {
            "type": "block_actions",
            "user": {"id": user_id},
            "actions": [
                {"action_id": "report_read", "value": f'{{"schedule_id": "{schedule_id}"}}'}
            ],
            "container": {"channel_id": "C_REPORT"},
        }

        result = await process_report_read_response(payload_data)

        assert result["status"] == "success"
        assert result.get("detail") == "すでに確認済みです。"
        await asyncio.sleep(0)
        assert notified_calls == 0

        session = session_factory()
        refreshed_schedule = session.get(Schedule, schedule_id)
        refreshed_delivery = (
            session.query(ReportDelivery).filter(ReportDelivery.schedule_id == schedule_id).first()
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.state == ScheduleState.DONE
        assert refreshed_delivery is not None
        assert refreshed_delivery.read_at is not None
        session.close()

    @pytest.mark.asyncio
    async def test_notify_report_read_result_sends_notification_stimulus_on_success(
        self, monkeypatch
    ):
        monkeypatch.setenv("SLACK_BOT_USER_OAUTH_TOKEN", "xoxb-test")

        posted: dict[str, object] = {}
        stimulated: dict[str, str] = {}

        class _FakePostResponse:
            def json(self):
                return {"ok": True, "ts": "1700000000.999999"}

        def _fake_post(url, headers=None, json=None, timeout=None):
            posted["url"] = url
            posted["payload"] = json or {}
            return _FakePostResponse()

        async def _fake_send_notification_stimulus(user_id: str, source: str, reason: str = ""):
            stimulated["user_id"] = user_id
            stimulated["source"] = source
            stimulated["reason"] = reason

        monkeypatch.setattr("backend.api.interactive.requests.post", _fake_post)
        monkeypatch.setattr(
            "backend.api.interactive._send_notification_stimulus",
            _fake_send_notification_stimulus,
        )

        await interactive_api._notify_report_read_result(
            channel_id="C_REPORT",
            user_id="U03JBULT484",
            thread_ts="1700000000.123456",
            text="来週も頑張りましょう",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "ok"}}],
            reason_text="report: 週次レポートを確認しました",
        )

        assert posted["url"] == "https://slack.com/api/chat.postMessage"
        payload = posted["payload"]
        assert isinstance(payload, dict)
        assert payload["channel"] == "C_REPORT"
        assert payload["thread_ts"] == "1700000000.123456"
        assert stimulated == {
            "user_id": "U03JBULT484",
            "source": "report-read-result",
            "reason": "report: 週次レポートを確認しました",
        }

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
        session_factory = sessionmaker(bind=engine)

        user_id = "U03JBULT484"
        session = session_factory()
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
    async def test_send_no_punishment_skips_when_daily_limit_exceeded(self, monkeypatch, tmp_path):
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
        session_factory = sessionmaker(bind=engine)

        user_id = "U03JBULT484"
        session = session_factory()
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

        action_log = ActionLog(schedule_id=schedule.id, result=ActionResult.YES)
        v3_db_session.add(action_log)
        v3_db_session.commit()

        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [
                {"action_id": "ignore_yes", "value": f'{{"schedule_id": "{schedule.id}"}}'}
            ],
        }

        result = await process_ignore_response(payload_data)
        assert result["status"] == "success"
        assert result.get("detail") == "今やりました"

    @pytest.mark.asyncio
    async def test_ignore_response_no(self, v3_db_session, v3_test_data_factory):
        schedule = v3_test_data_factory.create_schedule()

        action_log = ActionLog(schedule_id=schedule.id, result=ActionResult.NO)
        v3_db_session.add(action_log)
        v3_db_session.commit()

        payload_data = {
            "type": "block_actions",
            "user": {"id": "U03JBULT484"},
            "actions": [{"action_id": "ignore_no", "value": f'{{"schedule_id": "{schedule.id}"}}'}],
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
                        "commitment_1": {
                            "task_1": {"type": "plain_text_input", "value": "朝の瞑想"}
                        },
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
            b for b in updated_view["blocks"] if b.get("block_id", "").startswith("commitment_")
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
            b for b in updated_view["blocks"] if b.get("block_id", "").startswith("commitment_")
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
            b for b in updated_view["blocks"] if b.get("block_id", "").startswith("commitment_")
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
            b for b in updated_view["blocks"] if b.get("block_id", "").startswith("commitment_")
        ]
        assert len(task_blocks) == 3
