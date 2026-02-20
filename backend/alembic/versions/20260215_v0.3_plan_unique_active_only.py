"""Restrict PLAN uniqueness to active states

Keep historical PLAN rows (done/canceled) while enforcing at most one active
PLAN per user per day.

Revision ID: 20260215_v0.3_plan_unique_active_only
Revises: 20260215_v0.3_schedule_index_split
Create Date: 2026-02-15 20:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260215_v0.3_plan_unique_active_only"
down_revision: str | Sequence[str] | None = "20260215_v0.3_schedule_index_split"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uix_user_plan_date", table_name="schedules")
    op.create_index(
        "uix_user_plan_date_active",
        "schedules",
        ["user_id", sa.text("date(run_at)")],
        unique=True,
        sqlite_where=sa.text("event_type = 'PLAN' AND state IN ('PENDING', 'PROCESSING')"),
    )


def downgrade() -> None:
    op.drop_index("uix_user_plan_date_active", table_name="schedules")
    op.create_index(
        "uix_user_plan_date",
        "schedules",
        ["user_id", sa.text("date(run_at)")],
        unique=True,
        sqlite_where=sa.text("event_type = 'PLAN'"),
    )
