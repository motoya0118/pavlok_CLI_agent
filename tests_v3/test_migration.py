"""Tests for v0.3 Alembic Migration

Tests the database schema creation and migration for Oni System v0.3.
"""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect


class TestV3Migration:
    """Test v0.3 database migration."""

    def test_alembic_config_exists(self):
        """Test that alembic.ini exists in backend directory."""
        backend_root = Path(__file__).resolve().parents[1] / "backend"
        alembic_ini = backend_root / "alembic.ini"
        assert alembic_ini.exists(), "alembic.ini should exist in backend directory"

    def test_alembic_env_exists(self):
        """Test that env.py exists in backend/alembic directory."""
        backend_root = Path(__file__).resolve().parents[1] / "backend"
        env_py = backend_root / "alembic" / "env.py"
        assert env_py.exists(), "env.py should exist in backend/alembic directory"

    def test_initial_migration_exists(self):
        """Test that initial migration file exists."""
        backend_root = Path(__file__).resolve().parents[1] / "backend"
        versions_dir = backend_root / "alembic" / "versions"
        migration_files = list(versions_dir.glob("*_v0.3_*.py"))
        assert len(migration_files) > 0, "v0.3 migration file should exist"

    def test_migration_can_be_loaded(self):
        """Test that migration module can be imported."""
        import importlib.util
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[1] / "backend"
        versions_dir = backend_root / "alembic" / "versions"
        migration_files = list(versions_dir.glob("*_v0.3_*.py"))

        if migration_files:
            migration_file = migration_files[0]
            spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
            assert spec is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert hasattr(module, "upgrade")
            assert hasattr(module, "downgrade")

    def test_upgrade_creates_tables(self, tmp_path, monkeypatch):
        """Test that upgrade creates all expected tables."""
        from alembic import command
        from sqlalchemy import create_engine

        backend_root = Path(__file__).resolve().parents[1] / "backend"
        alembic_ini = backend_root / "alembic.ini"

        db_path = tmp_path / "upgrade_creates_tables.db"
        db_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", db_url)

        config = Config(str(alembic_ini))
        command.upgrade(config, "head")

        engine = create_engine(db_url, future=True)
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())

        expected_tables = {
            "commitments",
            "schedules",
            "action_logs",
            "punishments",
            "configurations",
            "config_audit_log",
            "report_deliveries",
            "calorie_records",
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

    def test_upgrade_upserts_report_defaults_for_existing_users(self, tmp_path, monkeypatch):
        """Upgrade should backfill REPORT_* defaults for existing users only when missing."""
        from alembic import command
        from sqlalchemy import create_engine, text

        backend_root = Path(__file__).resolve().parents[1] / "backend"
        alembic_ini = backend_root / "alembic.ini"

        db_path = tmp_path / "upgrade_report_defaults.db"
        db_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", db_url)

        config = Config(str(alembic_ini))
        command.upgrade(config, "20260220_v0.3_schedules_commitment_id_order")

        engine = create_engine(db_url, future=True)
        now = "2026-03-05 07:00:00"
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO commitments (id, user_id, time, task, active, created_at, updated_at)
                    VALUES
                    ('c1', 'U_EXISTING_1', '09:00:00', 'task1', 1, :now, :now)
                    """
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO schedules (
                        id, commitment_id, user_id, event_type, run_at, state,
                        thread_ts, comment, yes_comment, no_comment, retry_count, created_at, updated_at
                    )
                    VALUES
                    ('s1', NULL, 'U_EXISTING_2', 'PLAN', :now, 'PENDING',
                     NULL, NULL, NULL, NULL, 0, :now, :now)
                    """
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO configurations (
                        id, user_id, key, value, value_type,
                        description, default_value, version, created_at, updated_at
                    )
                    VALUES (
                        'cfg1', 'U_EXISTING_1', 'REPORT_TIME', '08:30', 'str',
                        'preset', '08:30', 1, :now, :now
                    )
                    """
                ),
                {"now": now},
            )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT user_id, key, value
                    FROM configurations
                    WHERE user_id IN ('U_EXISTING_1', 'U_EXISTING_2')
                      AND key IN ('REPORT_WEEKDAY', 'REPORT_TIME')
                    ORDER BY user_id, key
                    """
                )
            ).all()

        values = {(row[0], row[1]): row[2] for row in rows}
        assert values[("U_EXISTING_1", "REPORT_TIME")] == "08:30"
        assert values[("U_EXISTING_1", "REPORT_WEEKDAY")] == "sat"
        assert values[("U_EXISTING_2", "REPORT_TIME")] == "07:00"
        assert values[("U_EXISTING_2", "REPORT_WEEKDAY")] == "sat"

    def test_tables_created_by_models(self, v3_db_session):
        """Test that models.create_all() creates expected tables."""

        # Get inspector
        inspector = inspect(v3_db_session.bind)

        # Expected tables in v0.3
        expected_tables = {
            "commitments",
            "schedules",
            "action_logs",
            "punishments",
            "configurations",
            "config_audit_log",
            "report_deliveries",
            "calorie_records",
        }

        # Get actual tables
        actual_tables = set(inspector.get_table_names())

        # Check all expected tables exist
        assert expected_tables.issubset(actual_tables), (
            f"Missing tables: {expected_tables - actual_tables}"
        )

    def test_schedules_table_columns(self, v3_db_session):
        """Test that schedules table has all expected columns."""
        inspector = inspect(v3_db_session.bind)
        columns = {c["name"] for c in inspector.get_columns("schedules")}

        expected_columns = {
            "id",
            "commitment_id",
            "user_id",
            "event_type",
            "run_at",
            "state",
            "thread_ts",
            "input_value",
            "comment",
            "yes_comment",
            "no_comment",
            "retry_count",
            "created_at",
            "updated_at",
        }

        assert expected_columns == columns, (
            f"Columns mismatch. Expected: {expected_columns}, Got: {columns}"
        )

    def test_schedules_table_column_order_after_migration(self, tmp_path, monkeypatch):
        """Test schedules column order after running Alembic migrations."""
        from alembic import command
        from sqlalchemy import create_engine

        backend_root = Path(__file__).resolve().parents[1] / "backend"
        alembic_ini = backend_root / "alembic.ini"

        db_path = tmp_path / "migration_order.db"
        db_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", db_url)

        config = Config(str(alembic_ini))
        command.upgrade(config, "head")

        engine = create_engine(db_url, future=True)
        with engine.connect() as connection:
            inspector = inspect(connection)
            columns = [c["name"] for c in inspector.get_columns("schedules")]

        expected_columns = [
            "id",
            "commitment_id",
            "user_id",
            "event_type",
            "run_at",
            "state",
            "thread_ts",
            "input_value",
            "comment",
            "yes_comment",
            "no_comment",
            "retry_count",
            "created_at",
            "updated_at",
        ]

        assert expected_columns == columns, (
            f"Columns mismatch. Expected: {expected_columns}, Got: {columns}"
        )

    def test_commitments_table_columns(self, v3_db_session):
        """Test that commitments table has all expected columns."""
        inspector = inspect(v3_db_session.bind)
        columns = {c["name"] for c in inspector.get_columns("commitments")}

        expected_columns = {"id", "user_id", "time", "task", "active", "created_at", "updated_at"}

        assert expected_columns == columns, (
            f"Columns mismatch. Expected: {expected_columns}, Got: {columns}"
        )

    def test_punishments_unique_constraint(self, v3_db_session):
        """Test that punishments table has unique constraint on (schedule_id, mode, count)."""
        inspector = inspect(v3_db_session.bind)
        constraints = inspector.get_unique_constraints("punishments")

        # Check for unique constraint
        constraint_names = {c["name"] for c in constraints}
        assert "uix_schedule_mode_count" in constraint_names or any(
            "schedule_id" in str(c.get("column_names", [])) for c in constraints
        ), "punishments should have unique constraint on (schedule_id, mode, count)"

    def test_configurations_unique_constraint(self, v3_db_session):
        """Test that configurations table has unique constraint on (user_id, key)."""
        inspector = inspect(v3_db_session.bind)
        constraints = inspector.get_unique_constraints("configurations")

        # Check for unique constraint
        constraint_names = {c["name"] for c in constraints}
        assert "uix_user_key" in constraint_names or any(
            "user_id" in str(c.get("column_names", [])) for c in constraints
        ), "configurations should have unique constraint on (user_id, key)"

    def test_schedule_state_enum_values(self, v3_db_session):
        """Test that schedule_state_enum has all expected values."""
        from backend.models import ScheduleState

        # Check enum values are defined
        expected_values = {"pending", "processing", "done", "skipped", "failed", "canceled"}
        actual_values = {e.value for e in ScheduleState}

        assert expected_values == actual_values, (
            f"Enum values mismatch. Expected: {expected_values}, Got: {actual_values}"
        )

    def test_foreign_keys(self, v3_db_session, v3_test_data_factory):
        """Test that foreign key relationships are correct."""

        # Create a schedule
        schedule = v3_test_data_factory.create_schedule()

        # Create action_log with schedule_id
        log = v3_test_data_factory.create_action_log(schedule_id=schedule.id)

        # Create punishment with schedule_id
        punishment = v3_test_data_factory.create_punishment(schedule_id=schedule.id)

        # Verify relationships
        assert log.schedule_id == schedule.id
        assert punishment.schedule_id == schedule.id
