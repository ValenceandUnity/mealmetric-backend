"""add workout log exercise entries

Revision ID: b8f9e3c7d4a1
Revises: 6d1f8b42c3aa
Create Date: 2026-03-22 16:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f9e3c7d4a1"
down_revision: str | Sequence[str] | None = "6d1f8b42c3aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workout_log_exercise_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workout_log_id", sa.UUID(), nullable=False),
        sa.Column("exercise_name", sa.String(length=255), nullable=True),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("position >= 0", name="ck_workout_log_exercise_entries_position_non_negative"),
        sa.CheckConstraint("sets IS NULL OR sets >= 0", name="ck_workout_log_exercise_entries_sets_non_negative"),
        sa.CheckConstraint("reps IS NULL OR reps >= 0", name="ck_workout_log_exercise_entries_reps_non_negative"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_workout_log_exercise_entries_duration_seconds_non_negative",
        ),
        sa.ForeignKeyConstraint(["workout_log_id"], ["workout_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workout_log_id",
            "position",
            name="uq_workout_log_exercise_entries_workout_log_id_position",
        ),
    )
    op.create_index(
        op.f("ix_workout_log_exercise_entries_workout_log_id"),
        "workout_log_exercise_entries",
        ["workout_log_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_workout_log_exercise_entries_workout_log_id"),
        table_name="workout_log_exercise_entries",
    )
    op.drop_table("workout_log_exercise_entries")
