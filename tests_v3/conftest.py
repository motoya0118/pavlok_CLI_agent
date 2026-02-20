# v0.3 Test Configuration
# TDD development fixtures and configuration
import os
import sys
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Set test environment variables
os.environ.setdefault("TIMEZONE", "Asia/Tokyo")


# ============================================================================
# v0.3 DB Fixtures
# ============================================================================


@pytest.fixture()
def v3_db_engine():
    """In-memory SQLite engine for v0.3 models."""
    from backend.models import Base

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, future=True
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def v3_db_session(v3_db_engine) -> Generator:
    """DB session for v0.3 models."""
    session_factory = sessionmaker(bind=v3_db_engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture()
def v3_test_user_id() -> str:
    """Test user ID fixture."""
    return str(uuid4())


@pytest.fixture
def v3_test_data_factory(v3_db_session, v3_test_user_id):
    """Helper class for creating v0.3 test data."""
    from backend.models import (
        ActionLog,
        ActionResult,
        Commitment,
        Configuration,
        ConfigValueType,
        EventType,
        Punishment,
        PunishmentMode,
        Schedule,
        ScheduleState,
    )

    class TestDataFactory:
        def __init__(self, session, user_id: str):
            self.session = session
            self.user_id = user_id

        def create_commitment(
            self,
            time: str = "09:00:00",
            task: str = "test task",
            active: bool = True,
        ) -> Commitment:
            commitment = Commitment(
                user_id=self.user_id,
                time=time,
                task=task,
                active=active,
            )
            self.session.add(commitment)
            self.session.commit()
            self.session.refresh(commitment)
            return commitment

        def create_schedule(
            self,
            event_type: EventType = EventType.PLAN,
            run_at: datetime | None = None,
            state: ScheduleState = ScheduleState.PENDING,
            thread_ts: str | None = None,
            retry_count: int = 0,
            commitment_id: str | None = None,
            comment: str | None = None,
        ) -> Schedule:
            if run_at is None:
                run_at = datetime.now() + timedelta(hours=1)

            resolved_commitment_id = commitment_id
            resolved_comment = comment
            if event_type == EventType.REMIND:
                commitment = None
                if not resolved_commitment_id:
                    run_time = run_at.strftime("%H:%M:%S")
                    commitment = (
                        self.session.query(Commitment)
                        .filter(
                            Commitment.user_id == self.user_id,
                            Commitment.active.is_(True),
                            Commitment.time == run_time,
                        )
                        .order_by(Commitment.updated_at.desc(), Commitment.created_at.desc())
                        .first()
                    )
                    if commitment is None:
                        commitment = Commitment(
                            user_id=self.user_id,
                            time=run_time,
                            task=resolved_comment or "test task",
                            active=True,
                        )
                        self.session.add(commitment)
                        self.session.flush()
                    resolved_commitment_id = str(commitment.id)

                if not resolved_comment and commitment is not None:
                    resolved_comment = commitment.task

            schedule = Schedule(
                user_id=self.user_id,
                event_type=event_type,
                commitment_id=resolved_commitment_id if event_type == EventType.REMIND else None,
                run_at=run_at,
                state=state,
                thread_ts=thread_ts,
                comment=resolved_comment,
                retry_count=retry_count,
            )
            self.session.add(schedule)
            self.session.commit()
            self.session.refresh(schedule)
            return schedule

        def create_action_log(
            self,
            schedule_id: str,
            result: ActionResult = ActionResult.YES,
        ) -> ActionLog:
            log = ActionLog(
                schedule_id=schedule_id,
                result=result,
            )
            self.session.add(log)
            self.session.commit()
            self.session.refresh(log)
            return log

        def create_punishment(
            self,
            schedule_id: str,
            mode: PunishmentMode = PunishmentMode.IGNORE,
            count: int = 1,
        ) -> Punishment:
            punishment = Punishment(
                schedule_id=schedule_id,
                mode=mode,
                count=count,
            )
            self.session.add(punishment)
            self.session.commit()
            self.session.refresh(punishment)
            return punishment

        def create_configuration(
            self,
            key: str = "TEST_CONFIG",
            value: str = "test_value",
            value_type: ConfigValueType = ConfigValueType.STR,
            description: str | None = None,
            min_value: float | None = None,
            max_value: float | None = None,
        ) -> Configuration:
            config = Configuration(
                user_id=self.user_id,
                key=key,
                value=value,
                value_type=value_type,
                description=description,
                min_value=min_value,
                max_value=max_value,
            )
            self.session.add(config)
            self.session.commit()
            self.session.refresh(config)
            return config

    return TestDataFactory(v3_db_session, v3_test_user_id)


# ============================================================================
# v0.3 Mock Fixtures
# ============================================================================


@pytest.fixture()
def mock_slack_client():
    """Advanced SlackClient mock with call recording."""
    from tests_v3.mocks import MockSlackClient

    return MockSlackClient()


@pytest.fixture()
def mock_pavlok_client():
    """Advanced PavlokClient mock with call recording."""
    from tests_v3.mocks import MockPavlokClient

    return MockPavlokClient()


@pytest.fixture()
def mock_agent_client():
    """Agent (Claude/codex) mock with call recording."""
    from tests_v3.mocks import MockAgentClient

    return MockAgentClient()


# ============================================================================
# Helper Functions
# ============================================================================


@pytest.fixture()
def assert_schedule_state():
    """Helper function to assert schedule state."""
    from backend.models import Schedule, ScheduleState

    def _assert(session, schedule_id: str, expected_state: ScheduleState):
        schedule = session.get(Schedule, schedule_id)
        assert schedule is not None
        assert schedule.state == expected_state

    return _assert


@pytest.fixture()
def count_punishments():
    """Helper function to count punishments."""
    from backend.models import Punishment, PunishmentMode

    def _count(session, schedule_id: str, mode: PunishmentMode | None = None) -> int:
        query = session.query(Punishment).filter_by(schedule_id=schedule_id)
        if mode:
            query = query.filter_by(mode=mode)
        return query.count()

    return _count


# ============================================================================
# pytest configuration
# ============================================================================

pytest_plugins = []


def pytest_configure(config):
    """Configure pytest settings."""
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
