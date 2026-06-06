"""merge notifications and workout history heads

Revision ID: fa9c1d2e3b4a
Revises: c3d4e5f6a7b8, e7c4a1b2d9f0
Create Date: 2026-06-06 13:25:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "fa9c1d2e3b4a"
down_revision: str | Sequence[str] | None = ("c3d4e5f6a7b8", "e7c4a1b2d9f0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
