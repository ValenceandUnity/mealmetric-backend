"""add pt roster categories

Revision ID: 9d4e5f6a7b8c
Revises: 7b3c4d5e6f7a
Create Date: 2026-06-06 17:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4e5f6a7b8c"
down_revision: str | Sequence[str] | None = "7b3c4d5e6f7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _validate_no_roster_category_data_for_downgrade() -> None:
    bind = op.get_bind()
    category_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(1)
            FROM pt_roster_categories
            """
        )
    ).scalar_one()
    assignment_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(1)
            FROM pt_client_links
            WHERE roster_category_id IS NOT NULL
            """
        )
    ).scalar_one()

    if category_count > 0 or assignment_count > 0:
        raise RuntimeError(
            "Cannot downgrade roster categories while roster category data or assignments exist."
        )


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pt_roster_categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
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
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pt_user_id",
            "name",
            name="uq_pt_roster_categories_pt_user_id_name",
        ),
    )
    op.create_index(
        op.f("ix_pt_roster_categories_pt_user_id"),
        "pt_roster_categories",
        ["pt_user_id"],
        unique=False,
    )

    with op.batch_alter_table("pt_client_links") as batch_op:
        batch_op.add_column(sa.Column("roster_category_id", sa.UUID(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_pt_client_links_roster_category_id"),
            ["roster_category_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_pt_client_links_roster_category_id_pt_roster_categories",
            "pt_roster_categories",
            ["roster_category_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    _validate_no_roster_category_data_for_downgrade()

    with op.batch_alter_table("pt_client_links") as batch_op:
        batch_op.drop_constraint(
            "fk_pt_client_links_roster_category_id_pt_roster_categories",
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_pt_client_links_roster_category_id"))
        batch_op.drop_column("roster_category_id")

    op.drop_index(
        op.f("ix_pt_roster_categories_pt_user_id"),
        table_name="pt_roster_categories",
    )
    op.drop_table("pt_roster_categories")
