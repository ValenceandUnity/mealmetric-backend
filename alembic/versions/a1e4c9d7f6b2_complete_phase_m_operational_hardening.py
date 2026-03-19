"""complete phase m operational hardening

Revision ID: a1e4c9d7f6b2
Revises: f1a2b3c4d5e6
Create Date: 2026-03-17 10:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1e4c9d7f6b2"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("users", "token_version", server_default=None)

    op.create_table(
        "auth_failure_trackers",
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_emitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_request_id", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("subject"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("auth_failure_trackers")
    op.drop_column("users", "token_version")
