"""Add schedules.commitment_id and enforce event/commitment consistency

Revision ID: 20260219_v0.3_schedule_commitment_id
Revises: 20260215_v0.3_plan_unique_active_only
Create Date: 2026-02-19 11:10:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260219_v0.3_schedule_commitment_id"
down_revision: str | Sequence[str] | None = "20260215_v0.3_plan_unique_active_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _to_hhmmss(value: object) -> str:
    """Best-effort conversion from run_at to HH:MM:SS."""
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")

    raw = str(value or "").strip()
    if not raw:
        return "00:00:00"

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%H:%M:%S")
    except ValueError:
        pass

    if "T" in raw:
        raw = raw.split("T", 1)[1]
    elif " " in raw:
        raw = raw.split(" ", 1)[1]

    return raw[:8] if len(raw) >= 8 else "00:00:00"


def upgrade() -> None:
    with op.batch_alter_table("schedules") as batch_op:
        batch_op.add_column(sa.Column("commitment_id", sa.String(length=36), nullable=True))

    op.create_index("ix_schedule_commitment_id", "schedules", ["commitment_id"], unique=False)

    bind = op.get_bind()
    schedules = sa.table(
        "schedules",
        sa.column("id", sa.String(length=36)),
        sa.column("user_id", sa.String(length=36)),
        sa.column("event_type", sa.String(length=16)),
        sa.column("commitment_id", sa.String(length=36)),
        sa.column("run_at", sa.DateTime()),
        sa.column("comment", sa.Text()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    commitments = sa.table(
        "commitments",
        sa.column("id", sa.String(length=36)),
        sa.column("user_id", sa.String(length=36)),
        sa.column("time", sa.String(length=8)),
        sa.column("task", sa.Text()),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )

    remind_rows = (
        bind.execute(
            sa.select(
                schedules.c.id,
                schedules.c.user_id,
                schedules.c.run_at,
                schedules.c.comment,
                schedules.c.created_at,
                schedules.c.updated_at,
            ).where(sa.func.upper(schedules.c.event_type) == "REMIND")
        )
        .mappings()
        .all()
    )

    now = datetime.now()
    for row in remind_rows:
        schedule_id = str(row["id"])
        user_id = str(row["user_id"] or "")
        run_time = _to_hhmmss(row["run_at"])
        comment_text = str(row["comment"] or "").strip()

        commitment_id = bind.execute(
            sa.select(commitments.c.id)
            .where(
                commitments.c.user_id == user_id,
                commitments.c.active.is_(True),
                commitments.c.time == run_time,
            )
            .order_by(commitments.c.updated_at.desc(), commitments.c.created_at.desc())
            .limit(1)
        ).scalar()

        if not commitment_id and comment_text:
            commitment_id = bind.execute(
                sa.select(commitments.c.id)
                .where(
                    commitments.c.user_id == user_id,
                    commitments.c.active.is_(True),
                    commitments.c.task == comment_text,
                )
                .order_by(commitments.c.updated_at.desc(), commitments.c.created_at.desc())
                .limit(1)
            ).scalar()

        if not commitment_id:
            placeholder_id = str(uuid.uuid4())
            created_at = row["created_at"] if isinstance(row["created_at"], datetime) else now
            updated_at = row["updated_at"] if isinstance(row["updated_at"], datetime) else now
            bind.execute(
                commitments.insert().values(
                    id=placeholder_id,
                    user_id=user_id,
                    time=run_time,
                    task=comment_text or "タスク",
                    active=False,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            commitment_id = placeholder_id

        bind.execute(
            schedules.update()
            .where(schedules.c.id == schedule_id)
            .values(commitment_id=str(commitment_id))
        )

    # PLAN rows are explicitly null by design.
    bind.execute(
        schedules.update()
        .where(sa.func.upper(schedules.c.event_type) == "PLAN")
        .values(commitment_id=None)
    )

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.create_foreign_key(
            "fk_schedules_commitment_id_commitments",
            "commitments",
            ["commitment_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_schedules_event_commitment_id",
            "(upper(event_type) = 'REMIND' AND commitment_id IS NOT NULL) OR "
            "(upper(event_type) = 'PLAN' AND commitment_id IS NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("schedules") as batch_op:
        batch_op.drop_constraint("ck_schedules_event_commitment_id", type_="check")
        batch_op.drop_constraint("fk_schedules_commitment_id_commitments", type_="foreignkey")

    op.drop_index("ix_schedule_commitment_id", table_name="schedules")

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.drop_column("commitment_id")
