"""add direct order ownership to orders

Revision ID: b91f4f3b2c8d
Revises: c4b7d8e921af
Create Date: 2026-03-15 23:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b91f4f3b2c8d"
down_revision: str | Sequence[str] | None = "c4b7d8e921af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("orders", sa.Column("client_user_id", sa.UUID(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE orders
            SET client_user_id = (
                SELECT payment_sessions.user_id
                FROM payment_sessions
                WHERE payment_sessions.id = orders.payment_session_id
            )
            """
        )
    )

    bind = op.get_bind()
    missing_owner_count = bind.execute(
        sa.text("SELECT COUNT(1) FROM orders WHERE client_user_id IS NULL")
    ).scalar_one()
    if missing_owner_count > 0:
        raise RuntimeError("orders_with_missing_client_user_id")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("client_user_id", existing_type=sa.UUID(), nullable=False)
        batch_op.create_foreign_key(
            "fk_orders_client_user_id_users",
            "users",
            ["client_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            batch_op.f("ix_orders_client_user_id"),
            ["client_user_id"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_index(batch_op.f("ix_orders_client_user_id"))
        batch_op.drop_constraint("fk_orders_client_user_id_users", type_="foreignkey")
        batch_op.drop_column("client_user_id")
