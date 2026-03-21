"""v0.3.2 PFC columns

Revision ID: 22f8f4f0eaf7
Revises: 20260308_v0.3_commitment_active_task_unique
Create Date: 2026-03-20 14:51:02.790919

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "22f8f4f0eaf7"
down_revision: str | Sequence[str] | None = "20260308_v0.3_commitment_active_task_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calorie_records", sa.Column("protein_g", sa.Float(), nullable=True))
    op.add_column("calorie_records", sa.Column("fat_g", sa.Float(), nullable=True))
    op.add_column("calorie_records", sa.Column("carbs_g", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("calorie_records", "carbs_g")
    op.drop_column("calorie_records", "fat_g")
    op.drop_column("calorie_records", "protein_g")
