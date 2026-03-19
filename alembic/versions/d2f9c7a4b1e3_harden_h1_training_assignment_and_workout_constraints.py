"""harden h1 training assignment and workout constraints

Revision ID: d2f9c7a4b1e3
Revises: 8c0a5f7d2c19
Create Date: 2026-03-16 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2f9c7a4b1e3"
down_revision: str | Sequence[str] | None = "8c0a5f7d2c19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _validate_assignment_link_consistency() -> None:
    bind = op.get_bind()
    mismatched_count = bind.execute(sa.text("""
            SELECT COUNT(1)
            FROM client_training_package_assignments a
            LEFT JOIN pt_client_links l
              ON l.id = a.pt_client_link_id
             AND l.pt_user_id = a.pt_user_id
             AND l.client_user_id = a.client_user_id
            WHERE l.id IS NULL
            """)).scalar_one()
    if mismatched_count > 0:
        raise RuntimeError("invalid_existing_assignment_link_pair")


def _validate_workout_log_anchors() -> None:
    bind = op.get_bind()
    orphan_count = bind.execute(sa.text("""
            SELECT COUNT(1)
            FROM workout_logs
            WHERE assignment_id IS NULL
              AND routine_id IS NULL
            """)).scalar_one()
    if orphan_count > 0:
        raise RuntimeError("invalid_existing_orphan_workout_logs")


def upgrade() -> None:
    """Upgrade schema."""
    _validate_assignment_link_consistency()
    _validate_workout_log_anchors()

    with op.batch_alter_table("pt_client_links") as batch_op:
        batch_op.create_unique_constraint(
            "uq_pt_client_links_id_pt_user_id_client_user_id",
            ["id", "pt_user_id", "client_user_id"],
        )

    with op.batch_alter_table("client_training_package_assignments") as batch_op:
        batch_op.create_foreign_key(
            "fk_client_training_package_assignments_link_triplet",
            "pt_client_links",
            ["pt_client_link_id", "pt_user_id", "client_user_id"],
            ["id", "pt_user_id", "client_user_id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("workout_logs") as batch_op:
        batch_op.create_check_constraint(
            "ck_workout_logs_assignment_or_routine_required",
            "assignment_id IS NOT NULL OR routine_id IS NOT NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("workout_logs") as batch_op:
        batch_op.drop_constraint(
            "ck_workout_logs_assignment_or_routine_required",
            type_="check",
        )

    with op.batch_alter_table("client_training_package_assignments") as batch_op:
        batch_op.drop_constraint(
            "fk_client_training_package_assignments_link_triplet",
            type_="foreignkey",
        )

    with op.batch_alter_table("pt_client_links") as batch_op:
        batch_op.drop_constraint(
            "uq_pt_client_links_id_pt_user_id_client_user_id",
            type_="unique",
        )
