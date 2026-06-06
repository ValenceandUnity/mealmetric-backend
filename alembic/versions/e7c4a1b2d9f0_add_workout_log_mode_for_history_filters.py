"""add workout log mode for history filters

Revision ID: e7c4a1b2d9f0
Revises: b8f9e3c7d4a1
Create Date: 2026-06-06 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c4a1b2d9f0"
down_revision: str | Sequence[str] | None = "b8f9e3c7d4a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

workout_log_mode_enum = sa.Enum(
    "rep",
    "set",
    "general_workout",
    name="workout_log_mode",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    workout_log_mode_enum.create(bind, checkfirst=True)
    op.add_column("workout_logs", sa.Column("mode", workout_log_mode_enum, nullable=True))
    op.create_index(op.f("ix_workout_logs_mode"), "workout_logs", ["mode"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    op.drop_index(op.f("ix_workout_logs_mode"), table_name="workout_logs")
    op.drop_column("workout_logs", "mode")
    workout_log_mode_enum.drop(bind, checkfirst=True)
