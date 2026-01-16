"""v0.2 schema updates

Revision ID: 20260112_v02
Revises: 6500371f746a
Create Date: 2026-01-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260112_v02"
down_revision: Union[str, Sequence[str], None] = "6500371f746a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


schedule_state_enum = sa.Enum("pending", "running", "done", "failed", name="schedule_state_enum")
punishment_state_enum = sa.Enum("pending", "running", "done", "failed", name="punishment_state_enum")


def upgrade() -> None:
    op.create_table(
        "slack_ignore_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slack_message_ts", sa.String(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_message_ts"),
    )

    op.create_table(
        "daily_punishments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ignore_count", sa.Integer(), nullable=False),
        sa.Column("punishment_count", sa.Integer(), nullable=False),
        sa.Column("executed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("state", punishment_state_enum, server_default="pending", nullable=False),
        sa.Column("last_executed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )

    op.create_table(
        "pavlok_counts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("zap_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.alter_column("script_name", new_column_name="prompt_name", existing_type=sa.String())
        batch_op.add_column(sa.Column("state", schedule_state_enum, server_default="pending", nullable=False))
        batch_op.add_column(sa.Column("last_result", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))

    op.execute("UPDATE schedules SET state='done' WHERE is_execute = 1")

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.drop_column("is_execute")

    with op.batch_alter_table("behavior_logs") as batch_op:
        batch_op.add_column(sa.Column("related_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))



def downgrade() -> None:
    with op.batch_alter_table("behavior_logs") as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("related_date")

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.add_column(sa.Column("is_execute", sa.Boolean(), server_default=sa.text("0"), nullable=False))

    op.execute("UPDATE schedules SET is_execute = CASE WHEN state = 'done' THEN 1 ELSE 0 END")

    with op.batch_alter_table("schedules") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("last_error")
        batch_op.drop_column("last_result")
        batch_op.drop_column("state")
        batch_op.alter_column("prompt_name", new_column_name="script_name", existing_type=sa.String())

    op.drop_table("pavlok_counts")
    op.drop_table("daily_punishments")
    op.drop_table("slack_ignore_events")
