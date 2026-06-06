"""allow standalone client workout logs

Revision ID: 7b3c4d5e6f7a
Revises: fa9c1d2e3b4a
Create Date: 2026-06-06 15:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b3c4d5e6f7a"
down_revision: str | Sequence[str] | None = "fa9c1d2e3b4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _validate_no_standalone_workout_logs_for_downgrade() -> None:
    bind = op.get_bind()
    standalone_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(1)
            FROM workout_logs
            WHERE assignment_id IS NULL
              AND routine_id IS NULL
            """
        )
    ).scalar_one()
    if standalone_count > 0:
        raise RuntimeError("invalid_existing_standalone_workout_logs")

    null_pt_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(1)
            FROM workout_logs
            WHERE pt_user_id IS NULL
            """
        )
    ).scalar_one()
    if null_pt_count > 0:
        raise RuntimeError("invalid_existing_workout_logs_without_pt")


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("workout_logs") as batch_op:
        batch_op.drop_constraint(
            "ck_workout_logs_assignment_or_routine_required",
            type_="check",
        )
        batch_op.alter_column(
            "pt_user_id",
            existing_type=sa.UUID(),
            nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    _validate_no_standalone_workout_logs_for_downgrade()

    with op.batch_alter_table("workout_logs") as batch_op:
        batch_op.alter_column(
            "pt_user_id",
            existing_type=sa.UUID(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_workout_logs_assignment_or_routine_required",
            "assignment_id IS NOT NULL OR routine_id IS NOT NULL",
        )
