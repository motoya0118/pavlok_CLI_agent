"""Add calorie_records table for /cal feature.

Revision ID: 20260305_v0.3_calorie_schema
Revises: 20260305_v0.3_report_schema
Create Date: 2026-03-05 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260305_v0.3_calorie_schema"
down_revision: str | Sequence[str] | None = "20260305_v0.3_report_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calorie_records",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("food_name", sa.Text(), nullable=False),
        sa.Column("calorie", sa.Integer(), nullable=False),
        sa.Column("llm_raw_response_json", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("calorie >= 0", name="ck_calorie_records_calorie_non_negative"),
        sa.CheckConstraint(
            "lower(provider) in ('openai', 'gemini')",
            name="ck_calorie_records_provider",
        ),
    )
    op.create_index(
        "ix_calorie_records_user_id",
        "calorie_records",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_calorie_records_uploaded_at",
        "calorie_records",
        ["uploaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_calorie_records_uploaded_at", table_name="calorie_records")
    op.drop_index("ix_calorie_records_user_id", table_name="calorie_records")
    op.drop_table("calorie_records")

