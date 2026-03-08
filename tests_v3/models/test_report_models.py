# v0.3 Report Model/Repository Layer Tests
from datetime import date, datetime

from backend.models import (
    ActionLog,
    ActionResult,
    EventType,
    ReportDelivery,
    ScheduleState,
    deserialize_report_input_value,
    serialize_report_input_value,
)


class TestReportModelLayer:
    def test_event_type_report_and_action_result_report_read_available(self):
        """Report-specific enums are available from model definitions."""
        assert EventType.REPORT.value == "report"
        assert ActionResult.REPORT_READ.value == "REPORT_READ"

    def test_report_schedule_input_value_round_trip(self):
        """Report input_value JSON contract can be saved and loaded."""
        raw = serialize_report_input_value(
            ui_date="today",
            ui_time="07:00",
            updated_at="2026-03-05T07:10:00+09:00",
        )
        parsed = deserialize_report_input_value(raw)

        assert parsed == {
            "ui_date": "today",
            "ui_time": "07:00",
            "updated_at": "2026-03-05T07:10:00+09:00",
        }

    def test_report_schedule_input_value_invalid_returns_none(self):
        """Invalid JSON or missing keys should be treated as unreadable payload."""
        assert deserialize_report_input_value(None) is None
        assert deserialize_report_input_value("not json") is None
        assert deserialize_report_input_value("{}") is None
        assert deserialize_report_input_value('{"ui_date":"today","ui_time":"07:00"}') is None

    def test_schedule_report_input_helpers(self, v3_db_session, v3_test_data_factory):
        """Schedule helper methods store/load report UI values via input_value."""
        schedule = v3_test_data_factory.create_schedule(
            event_type=EventType.REPORT,
            state=ScheduleState.PENDING,
        )

        schedule.set_report_input_value(
            ui_date="tomorrow",
            ui_time="06:45",
            updated_at=datetime(2026, 3, 5, 8, 0, 0),
        )
        v3_db_session.commit()
        v3_db_session.refresh(schedule)

        assert schedule.get_report_input_value() == {
            "ui_date": "tomorrow",
            "ui_time": "06:45",
            "updated_at": "2026-03-05T08:00:00",
        }

    def test_report_delivery_crud(self, v3_db_session, v3_test_data_factory):
        """ReportDelivery is available from ORM and supports CRUD."""
        schedule = v3_test_data_factory.create_schedule(
            event_type=EventType.REPORT,
            state=ScheduleState.PROCESSING,
        )

        delivery = ReportDelivery(
            schedule_id=schedule.id,
            user_id=schedule.user_id,
            report_type="weekly",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 7),
            posted_at=datetime(2026, 3, 8, 7, 0, 0),
            thread_ts="1740000000.000100",
            markdown_table="| metric | value |\n|---|---:|\n| success | 5 |",
            llm_comment="Good progress.",
        )
        v3_db_session.add(delivery)
        v3_db_session.commit()

        loaded = v3_db_session.query(ReportDelivery).filter_by(schedule_id=schedule.id).one()
        assert loaded.user_id == schedule.user_id
        assert loaded.report_type == "weekly"
        assert loaded.period_start == date(2026, 3, 1)
        assert loaded.period_end == date(2026, 3, 7)

    def test_action_log_can_store_report_read(self, v3_db_session, v3_test_data_factory):
        """action_logs can persist REPORT_READ result."""
        schedule = v3_test_data_factory.create_schedule(
            event_type=EventType.REPORT,
            state=ScheduleState.PROCESSING,
        )

        action_log = ActionLog(
            schedule_id=schedule.id,
            result=ActionResult.REPORT_READ,
        )
        v3_db_session.add(action_log)
        v3_db_session.commit()

        loaded = (
            v3_db_session.query(ActionLog)
            .filter_by(schedule_id=schedule.id, result=ActionResult.REPORT_READ)
            .one()
        )
        assert loaded.id is not None
