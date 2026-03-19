"""add payload sha256 to stripe webhook events

Revision ID: f6b8d3c42e11
Revises: e5a3d01b1f9a
Create Date: 2026-03-15 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6b8d3c42e11"
down_revision: str | Sequence[str] | None = "e5a3d01b1f9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "stripe_webhook_events",
        sa.Column("payload_sha256", sa.String(length=64), server_default="", nullable=False),
    )
    op.create_index(
        op.f("ix_stripe_webhook_events_payload_sha256"),
        "stripe_webhook_events",
        ["payload_sha256"],
        unique=False,
    )
    op.alter_column("stripe_webhook_events", "payload_sha256", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_stripe_webhook_events_payload_sha256"),
        table_name="stripe_webhook_events",
    )
    op.drop_column("stripe_webhook_events", "payload_sha256")

