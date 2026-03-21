"""add phase 3b bookmarks vendor membership and vendor zip

Revision ID: 6d1f8b42c3aa
Revises: a1e4c9d7f6b2
Create Date: 2026-03-21 08:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d1f8b42c3aa"
down_revision: str | Sequence[str] | None = "a1e4c9d7f6b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("vendors", sa.Column("zip_code", sa.String(length=16), nullable=True))
    op.create_index(op.f("ix_vendors_zip_code"), "vendors", ["zip_code"], unique=False)

    op.create_table(
        "vendor_user_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "vendor_id", name="uq_vendor_user_memberships_user_vendor"),
    )
    op.create_index(
        op.f("ix_vendor_user_memberships_user_id"),
        "vendor_user_memberships",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vendor_user_memberships_vendor_id"),
        "vendor_user_memberships",
        ["vendor_id"],
        unique=False,
    )

    op.create_table(
        "bookmark_folders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_user_id", "name", name="uq_bookmark_folders_client_user_id_name"),
    )
    op.create_index(
        op.f("ix_bookmark_folders_client_user_id"),
        "bookmark_folders",
        ["client_user_id"],
        unique=False,
    )

    op.create_table(
        "bookmark_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("folder_id", sa.UUID(), nullable=False),
        sa.Column("meal_plan_id", sa.UUID(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["folder_id"], ["bookmark_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meal_plan_id"], ["meal_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folder_id", "meal_plan_id", name="uq_bookmark_items_folder_id_meal_plan_id"),
    )
    op.create_index(op.f("ix_bookmark_items_folder_id"), "bookmark_items", ["folder_id"], unique=False)
    op.create_index(
        op.f("ix_bookmark_items_meal_plan_id"),
        "bookmark_items",
        ["meal_plan_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_bookmark_items_meal_plan_id"), table_name="bookmark_items")
    op.drop_index(op.f("ix_bookmark_items_folder_id"), table_name="bookmark_items")
    op.drop_table("bookmark_items")

    op.drop_index(op.f("ix_bookmark_folders_client_user_id"), table_name="bookmark_folders")
    op.drop_table("bookmark_folders")

    op.drop_index(
        op.f("ix_vendor_user_memberships_vendor_id"),
        table_name="vendor_user_memberships",
    )
    op.drop_index(
        op.f("ix_vendor_user_memberships_user_id"),
        table_name="vendor_user_memberships",
    )
    op.drop_table("vendor_user_memberships")

    op.drop_index(op.f("ix_vendors_zip_code"), table_name="vendors")
    op.drop_column("vendors", "zip_code")
