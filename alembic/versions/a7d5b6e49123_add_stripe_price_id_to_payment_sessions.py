"""add stripe_price_id to payment_sessions

Revision ID: a7d5b6e49123
Revises: f6b8d3c42e11
Create Date: 2026-03-15 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d5b6e49123"
down_revision: str | Sequence[str] | None = "f6b8d3c42e11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("payment_sessions", sa.Column("stripe_price_id", sa.String(length=255), nullable=True))
    op.create_index(
        op.f("ix_payment_sessions_stripe_price_id"),
        "payment_sessions",
        ["stripe_price_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_payment_sessions_stripe_price_id"), table_name="payment_sessions")
    op.drop_column("payment_sessions", "stripe_price_id")

