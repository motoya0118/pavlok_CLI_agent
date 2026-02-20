"""Reorder schedules columns to place commitment_id after id.

Revision ID: 20260220_v0.3_schedules_commitment_id_order
Revises: 20260219_v0.3_schedule_commitment_id
Create Date: 2026-02-20 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260220_v0.3_schedules_commitment_id_order"
down_revision: Union[str, Sequence[str], None] = "20260219_v0.3_schedule_commitment_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHECK_EVENT_COMMITMENT = (
    "(upper(event_type) = 'REMIND' AND commitment_id IS NOT NULL) OR "
    "(upper(event_type) = 'PLAN' AND commitment_id IS NULL)"
)
PLAN_ACTIVE_WHERE = "event_type = 'PLAN' AND state IN ('PENDING', 'PROCESSING')"


def _create_schedules_table(table_name: str, commitment_after_id: bool) -> None:
    columns = [
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("thread_ts", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("yes_comment", sa.Text(), nullable=True),
        sa.Column("no_comment", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]
    commitment_col = sa.Column("commitment_id", sa.String(length=36), nullable=True)
    if commitment_after_id:
        columns.insert(1, commitment_col)
    else:
        columns.append(commitment_col)

    op.create_table(
        table_name,
        *columns,
        sa.ForeignKeyConstraint(
            ["commitment_id"],
            ["commitments.id"],
            name="fk_schedules_commitment_id_commitments",
        ),
        sa.CheckConstraint(
            CHECK_EVENT_COMMITMENT,
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


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    _create_schedules_table("schedules_reordered", commitment_after_id=True)

    op.execute(
        sa.text(
            """
            INSERT INTO schedules_reordered (
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
            """
        )
    )

    op.drop_table("schedules")
    op.rename_table("schedules_reordered", "schedules")
    _create_schedules_indexes()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    _create_schedules_table("schedules_old_order", commitment_after_id=False)

    op.execute(
        sa.text(
            """
            INSERT INTO schedules_old_order (
                id,
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
                updated_at,
                commitment_id
            )
            SELECT
                id,
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
                updated_at,
                commitment_id
            FROM schedules
            """
        )
    )

    op.drop_table("schedules")
    op.rename_table("schedules_old_order", "schedules")
    _create_schedules_indexes()
