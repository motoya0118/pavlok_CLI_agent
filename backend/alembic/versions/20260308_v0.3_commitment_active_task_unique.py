"""Enforce active commitment uniqueness by user/task.

Revision ID: 20260308_v0.3_commitment_active_task_unique
Revises: 20260305_v0.3_calorie_schema
Create Date: 2026-03-08 16:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260308_v0.3_commitment_active_task_unique"
down_revision: str | Sequence[str] | None = "20260305_v0.3_calorie_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_existing_tasks() -> None:
    bind = op.get_bind()
    now = datetime.now()

    bind.execute(
        sa.text(
            """
            UPDATE commitments
            SET task = trim(task),
                updated_at = :now
            WHERE task != trim(task)
            """
        ),
        {"now": now},
    )

    bind.execute(
        sa.text(
            """
            UPDATE commitments
            SET active = 0,
                updated_at = :now
            WHERE active = 1
              AND trim(coalesce(task, '')) = ''
            """
        ),
        {"now": now},
    )

    rows = (
        bind.execute(
            sa.text(
                """
                SELECT id, user_id, task
                FROM commitments
                WHERE active = 1
                ORDER BY
                    user_id ASC,
                    task ASC,
                    updated_at DESC,
                    created_at DESC,
                    id DESC
                """
            )
        )
        .mappings()
        .all()
    )

    seen: set[tuple[str, str]] = set()
    duplicate_ids: list[str] = []
    for row in rows:
        user_id = str(row["user_id"] or "").strip()
        task = str(row["task"] or "").strip()
        key = (user_id, task)
        if key in seen:
            duplicate_ids.append(str(row["id"]))
            continue
        seen.add(key)

    if duplicate_ids:
        bind.execute(
            sa.text(
                """
                UPDATE commitments
                SET active = 0,
                    updated_at = :now
                WHERE id = :commitment_id
                """
            ),
            [{"commitment_id": commitment_id, "now": now} for commitment_id in duplicate_ids],
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    _normalize_existing_tasks()
    op.create_index(
        "uix_commitments_user_task_active",
        "commitments",
        ["user_id", "task"],
        unique=True,
        sqlite_where=sa.text("active = 1"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    op.drop_index("uix_commitments_user_task_active", table_name="commitments")
