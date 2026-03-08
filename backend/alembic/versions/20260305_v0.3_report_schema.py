"""Add report schema components for v0.3.1.

Revision ID: 20260305_v0.3_report_schema
Revises: 20260220_v0.3_schedules_commitment_id_order
Create Date: 2026-03-05 19:30:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260305_v0.3_report_schema"
down_revision: str | Sequence[str] | None = "20260220_v0.3_schedules_commitment_id_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE_CHECK_WITH_REPORT = (
    "(upper(event_type) = 'REMIND' AND commitment_id IS NOT NULL) OR "
    "(upper(event_type) IN ('PLAN', 'REPORT') AND commitment_id IS NULL)"
)
SCHEDULE_CHECK_WITHOUT_REPORT = (
    "(upper(event_type) = 'REMIND' AND commitment_id IS NOT NULL) OR "
    "(upper(event_type) = 'PLAN' AND commitment_id IS NULL)"
)
PLAN_ACTIVE_WHERE = "event_type = 'PLAN' AND state IN ('PENDING', 'PROCESSING')"
ACTION_RESULT_CHECK_WITH_REPORT_READ = (
    "upper(result) IN ('YES', 'NO', 'AUTO_IGNORE', 'REPORT_READ')"
)
ACTION_RESULT_CHECK_WITHOUT_REPORT_READ = "upper(result) IN ('YES', 'NO', 'AUTO_IGNORE')"


def _create_schedules_table(table_name: str, with_report: bool) -> None:
    check_expr = SCHEDULE_CHECK_WITH_REPORT if with_report else SCHEDULE_CHECK_WITHOUT_REPORT
    op.create_table(
        table_name,
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("commitment_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("thread_ts", sa.String(length=50), nullable=True),
        sa.Column("input_value", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("yes_comment", sa.Text(), nullable=True),
        sa.Column("no_comment", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["commitment_id"],
            ["commitments.id"],
            name="fk_schedules_commitment_id_commitments",
        ),
        sa.CheckConstraint(
            check_expr,
            name="ck_schedules_event_commitment_id",
        ),
    )


def _create_schedules_indexes() -> None:
    op.create_index(
        "uix_user_plan_date_active",
        "schedules",
        ["user_id", sa.text("date(run_at)")],
        unique=True,
        sqlite_where=sa.text(PLAN_ACTIVE_WHERE),
    )
    op.create_index(
        "ix_schedule_user_event_run_at",
        "schedules",
        ["user_id", "event_type", "run_at"],
        unique=False,
    )
    op.create_index(
        "ix_schedule_commitment_id",
        "schedules",
        ["commitment_id"],
        unique=False,
    )


def _create_action_logs_table(table_name: str, with_report_read: bool) -> None:
    check_expr = (
        ACTION_RESULT_CHECK_WITH_REPORT_READ
        if with_report_read
        else ACTION_RESULT_CHECK_WITHOUT_REPORT_READ
    )
    op.create_table(
        table_name,
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("schedule_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(check_expr, name="ck_action_logs_result"),
    )


def _create_action_logs_indexes() -> None:
    op.create_index(
        "ix_action_logs_schedule_id",
        "action_logs",
        ["schedule_id"],
        unique=False,
    )


def _upsert_report_defaults_for_existing_users() -> None:
    bind = op.get_bind()
    users = (
        bind.execute(
            sa.text(
                """
                SELECT DISTINCT user_id FROM commitments
                UNION
                SELECT DISTINCT user_id FROM schedules
                UNION
                SELECT DISTINCT user_id FROM configurations
                """
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now()
    defaults = [("REPORT_WEEKDAY", "sat"), ("REPORT_TIME", "07:00")]

    for user_id in users:
        if not user_id:
            continue
        for key, value in defaults:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO configurations (
                        id, user_id, key, value, value_type,
                        description, default_value, version, created_at, updated_at
                    )
                    VALUES (
                        :id, :user_id, :key, :value, :value_type,
                        :description, :default_value, :version, :created_at, :updated_at
                    )
                    ON CONFLICT(user_id, key) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": str(user_id),
                    "key": key,
                    "value": value,
                    "value_type": "STR",
                    "description": "Configured by migration for report defaults",
                    "default_value": value,
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                },
            )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    op.create_table(
        "report_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("schedule_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("thread_ts", sa.String(length=50), nullable=True),
        sa.Column("markdown_table", sa.Text(), nullable=False),
        sa.Column("llm_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], name="fk_report_deliveries_schedule_id"),
        sa.UniqueConstraint("schedule_id", name="uix_report_deliveries_schedule_id"),
        sa.UniqueConstraint(
            "user_id",
            "report_type",
            "period_start",
            "period_end",
            name="uix_report_deliveries_user_period",
        ),
        sa.CheckConstraint(
            "lower(report_type) in ('weekly', 'monthly')",
            name="ck_report_deliveries_type",
        ),
    )
    op.create_index(
        "ix_report_deliveries_user_id",
        "report_deliveries",
        ["user_id"],
        unique=False,
    )

    _create_schedules_table("schedules_report", with_report=True)
    op.execute(
        sa.text(
            """
            INSERT INTO schedules_report (
                id,
                commitment_id,
                user_id,
                event_type,
                run_at,
                state,
                thread_ts,
                input_value,
                comment,
                yes_comment,
                no_comment,
                retry_count,
                created_at,
                updated_at
            )
            SELECT
                id,
                commitment_id,
                user_id,
                event_type,
                run_at,
                state,
                thread_ts,
                NULL AS input_value,
                comment,
                yes_comment,
                no_comment,
                retry_count,
                created_at,
                updated_at
            FROM schedules
            """
        )
    )
    op.drop_table("schedules")
    op.rename_table("schedules_report", "schedules")
    _create_schedules_indexes()

    _create_action_logs_table("action_logs_report", with_report_read=True)
    op.execute(
        sa.text(
            """
            INSERT INTO action_logs_report (
                id,
                schedule_id,
                result,
                created_at
            )
            SELECT
                id,
                schedule_id,
                result,
                created_at
            FROM action_logs
            """
        )
    )
    op.drop_table("action_logs")
    op.rename_table("action_logs_report", "action_logs")
    _create_action_logs_indexes()

    _upsert_report_defaults_for_existing_users()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    op.execute(
        sa.text(
            """
            DELETE FROM configurations
            WHERE key IN ('REPORT_WEEKDAY', 'REPORT_TIME')
            """
        )
    )

    op.drop_index("ix_report_deliveries_user_id", table_name="report_deliveries")
    op.drop_table("report_deliveries")

    _create_schedules_table("schedules_pre_report", with_report=False)
    op.execute(
        sa.text(
            """
            INSERT INTO schedules_pre_report (
                id,
                commitment_id,
                user_id,
                event_type,
                run_at,
                state,
                thread_ts,
                comment,
                yes_comment,
                no_comment,
                retry_count,
                created_at,
                updated_at
            )
            SELECT
                id,
                commitment_id,
                user_id,
                event_type,
                run_at,
                state,
                thread_ts,
                comment,
                yes_comment,
                no_comment,
                retry_count,
                created_at,
                updated_at
            FROM schedules
            WHERE upper(event_type) IN ('PLAN', 'REMIND')
            """
        )
    )
    op.drop_table("schedules")
    op.rename_table("schedules_pre_report", "schedules")
    _create_schedules_indexes()

    _create_action_logs_table("action_logs_pre_report", with_report_read=False)
    op.execute(
        sa.text(
            """
            INSERT INTO action_logs_pre_report (
                id,
                schedule_id,
                result,
                created_at
            )
            SELECT
                id,
                schedule_id,
                result,
                created_at
            FROM action_logs
            WHERE upper(result) IN ('YES', 'NO', 'AUTO_IGNORE')
            """
        )
    )
    op.drop_table("action_logs")
    op.rename_table("action_logs_pre_report", "action_logs")
    _create_action_logs_indexes()
