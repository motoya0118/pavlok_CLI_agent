"""v0.3 Initial Schema

Oni System v0.3用の初期スキーマ。全テーブルを新規作成。

Revision ID: 20260214_v0.3_init
Revises:
Create Date: 2026-02-14 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260214_v0.3_init"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enums
    schedule_state_enum = sa.Enum(
        "pending", "processing", "done", "skipped", "failed", "canceled", name="schedule_state_enum"
    )
    schedule_state_enum.create(op.get_bind(), checkfirst=False)

    event_type_enum = sa.Enum("plan", "remind", name="event_type_enum")
    event_type_enum.create(op.get_bind(), checkfirst=False)

    action_result_enum = sa.Enum("YES", "NO", "AUTO_IGNORE", name="action_result_enum")
    action_result_enum.create(op.get_bind(), checkfirst=False)

    punishment_mode_enum = sa.Enum("ignore", "no", name="punishment_mode_enum")
    punishment_mode_enum.create(op.get_bind(), checkfirst=False)

    config_value_type_enum = sa.Enum(
        "int", "float", "str", "json", "bool", name="config_value_type_enum"
    )
    config_value_type_enum.create(op.get_bind(), checkfirst=False)

    change_source_enum = sa.Enum(
        "slack_command", "rollback", "reset", "migration", name="change_source_enum"
    )
    change_source_enum.create(op.get_bind(), checkfirst=False)

    # commitments (新規)
    op.create_table(
        "commitments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("time", sa.String(8), nullable=False),  # HH:MM:SS
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # schedules (再設計)
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("event_type", event_type_enum, nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("state", schedule_state_enum, nullable=False, default="pending"),
        sa.Column("thread_ts", sa.String(50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("yes_comment", sa.Text(), nullable=True),
        sa.Column("no_comment", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Unique constraint for schedules
    op.create_index(
        "uix_user_date_event",
        "schedules",
        ["user_id", sa.text("date(run_at)"), "event_type"],
        unique=True,
    )

    # action_logs (再設計)
    op.create_table(
        "action_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schedule_id", sa.String(36), nullable=False, index=True),
        sa.Column("result", action_result_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # punishments (新規)
    op.create_table(
        "punishments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schedule_id", sa.String(36), nullable=False, index=True),
        sa.Column("mode", punishment_mode_enum, nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # Unique constraint for punishments
    op.create_index(
        "uix_schedule_mode_count",
        "punishments",
        ["schedule_id", "mode", "count"],
        unique=True,
    )

    # configurations (新規)
    op.create_table(
        "configurations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", config_value_type_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("min_value", sa.Integer(), nullable=True),
        sa.Column("max_value", sa.Integer(), nullable=True),
        sa.Column("valid_values", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Unique constraint for configurations
    op.create_index(
        "uix_user_key",
        "configurations",
        ["user_id", "key"],
        unique=True,
    )

    # config_audit_log (新規)
    op.create_table(
        "config_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("config_key", sa.String(100), nullable=False, index=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(50), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("change_source", change_source_enum, nullable=False),
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("config_audit_log")
    op.drop_table("configurations")
    op.drop_table("punishments")
    op.drop_table("action_logs")
    op.drop_table("schedules")
    op.drop_table("commitments")

    # Drop enums
    sa.Enum(name="change_source_enum").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="config_value_type_enum").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="punishment_mode_enum").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="action_result_enum").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="event_type_enum").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="schedule_state_enum").drop(op.get_bind(), checkfirst=False)
