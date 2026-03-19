"""add phase j vendor domain schema

Revision ID: 1c2d4e6f8a9b
Revises: b91f4f3b2c8d, 9f3a2d7c1b4e
Create Date: 2026-03-16 18:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c2d4e6f8a9b"
down_revision: str | Sequence[str] | None = ("b91f4f3b2c8d", "9f3a2d7c1b4e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

vendor_status_enum = sa.Enum(
    "draft",
    "active",
    "inactive",
    "archived",
    name="vendor_status",
    native_enum=False,
    create_constraint=True,
)

vendor_menu_item_status_enum = sa.Enum(
    "draft",
    "active",
    "inactive",
    "archived",
    name="vendor_menu_item_status",
    native_enum=False,
    create_constraint=True,
)

meal_plan_status_enum = sa.Enum(
    "draft",
    "published",
    "unpublished",
    "archived",
    name="meal_plan_status",
    native_enum=False,
    create_constraint=True,
)

vendor_pickup_window_status_enum = sa.Enum(
    "scheduled",
    "open",
    "closed",
    "cancelled",
    name="vendor_pickup_window_status",
    native_enum=False,
    create_constraint=True,
)

meal_plan_availability_status_enum = sa.Enum(
    "scheduled",
    "available",
    "sold_out",
    "unavailable",
    "cancelled",
    name="meal_plan_availability_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vendors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", vendor_status_enum, server_default="draft", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_vendors_slug"),
        sa.UniqueConstraint("id", "slug", name="uq_vendors_id_slug"),
    )
    op.create_index(op.f("ix_vendors_slug"), "vendors", ["slug"], unique=False)
    op.create_index(op.f("ix_vendors_status"), "vendors", ["status"], unique=False)

    op.create_table(
        "vendor_menu_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            vendor_menu_item_status_enum,
            server_default="draft",
            nullable=False,
        ),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("protein_grams", sa.Integer(), nullable=True),
        sa.Column("carbs_grams", sa.Integer(), nullable=True),
        sa.Column("fat_grams", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("price_cents >= 0", name="ck_vendor_menu_items_price_cents_non_negative"),
        sa.CheckConstraint("calories IS NULL OR calories >= 0", name="ck_vendor_menu_items_calories_non_negative"),
        sa.CheckConstraint(
            "protein_grams IS NULL OR protein_grams >= 0",
            name="ck_vendor_menu_items_protein_grams_non_negative",
        ),
        sa.CheckConstraint(
            "carbs_grams IS NULL OR carbs_grams >= 0",
            name="ck_vendor_menu_items_carbs_grams_non_negative",
        ),
        sa.CheckConstraint(
            "fat_grams IS NULL OR fat_grams >= 0",
            name="ck_vendor_menu_items_fat_grams_non_negative",
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_id", "slug", name="uq_vendor_menu_items_vendor_id_slug"),
        sa.UniqueConstraint("id", "vendor_id", name="uq_vendor_menu_items_id_vendor_id"),
    )
    op.create_index(
        op.f("ix_vendor_menu_items_vendor_id"),
        "vendor_menu_items",
        ["vendor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vendor_menu_items_status"),
        "vendor_menu_items",
        ["status"],
        unique=False,
    )

    op.create_table(
        "meal_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", meal_plan_status_enum, server_default="draft", nullable=False),
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
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_id", "slug", name="uq_meal_plans_vendor_id_slug"),
        sa.UniqueConstraint("id", "vendor_id", name="uq_meal_plans_id_vendor_id"),
    )
    op.create_index(op.f("ix_meal_plans_vendor_id"), "meal_plans", ["vendor_id"], unique=False)
    op.create_index(op.f("ix_meal_plans_status"), "meal_plans", ["status"], unique=False)

    op.create_table(
        "vendor_pickup_windows",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            vendor_pickup_window_status_enum,
            server_default="scheduled",
            nullable=False,
        ),
        sa.Column("pickup_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pickup_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "pickup_end_at > pickup_start_at",
            name="ck_vendor_pickup_windows_pickup_window_ordered",
        ),
        sa.CheckConstraint(
            "order_cutoff_at IS NULL OR order_cutoff_at <= pickup_start_at",
            name="ck_vendor_pickup_windows_order_cutoff_before_pickup_start",
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "vendor_id", name="uq_vendor_pickup_windows_id_vendor_id"),
    )
    op.create_index(
        op.f("ix_vendor_pickup_windows_vendor_id"),
        "vendor_pickup_windows",
        ["vendor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vendor_pickup_windows_status"),
        "vendor_pickup_windows",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vendor_pickup_windows_pickup_start_at"),
        "vendor_pickup_windows",
        ["pickup_start_at"],
        unique=False,
    )

    op.create_table(
        "meal_plan_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("meal_plan_id", sa.UUID(), nullable=False),
        sa.Column("vendor_menu_item_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_meal_plan_items_quantity_positive"),
        sa.CheckConstraint("position >= 0", name="ck_meal_plan_items_position_non_negative"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["meal_plan_id", "vendor_id"],
            ["meal_plans.id", "meal_plans.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_items_meal_plan_vendor_pair",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_menu_item_id", "vendor_id"],
            ["vendor_menu_items.id", "vendor_menu_items.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_items_menu_item_vendor_pair",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meal_plan_id", "position", name="uq_meal_plan_items_meal_plan_id_position"),
        sa.UniqueConstraint(
            "meal_plan_id",
            "vendor_menu_item_id",
            name="uq_meal_plan_items_meal_plan_id_vendor_menu_item_id",
        ),
    )
    op.create_index(
        op.f("ix_meal_plan_items_vendor_id"),
        "meal_plan_items",
        ["vendor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_items_meal_plan_id"),
        "meal_plan_items",
        ["meal_plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_items_vendor_menu_item_id"),
        "meal_plan_items",
        ["vendor_menu_item_id"],
        unique=False,
    )

    op.create_table(
        "meal_plan_availability",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=False),
        sa.Column("meal_plan_id", sa.UUID(), nullable=False),
        sa.Column("pickup_window_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            meal_plan_availability_status_enum,
            server_default="scheduled",
            nullable=False,
        ),
        sa.Column("inventory_count", sa.Integer(), nullable=True),
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
        sa.CheckConstraint(
            "inventory_count IS NULL OR inventory_count >= 0",
            name="ck_meal_plan_availability_inventory_count_non_negative",
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["meal_plan_id", "vendor_id"],
            ["meal_plans.id", "meal_plans.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_availability_meal_plan_vendor_pair",
        ),
        sa.ForeignKeyConstraint(
            ["pickup_window_id", "vendor_id"],
            ["vendor_pickup_windows.id", "vendor_pickup_windows.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_availability_pickup_window_vendor_pair",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "meal_plan_id",
            "pickup_window_id",
            name="uq_meal_plan_availability_meal_plan_id_pickup_window_id",
        ),
    )
    op.create_index(
        op.f("ix_meal_plan_availability_vendor_id"),
        "meal_plan_availability",
        ["vendor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_availability_meal_plan_id"),
        "meal_plan_availability",
        ["meal_plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_availability_pickup_window_id"),
        "meal_plan_availability",
        ["pickup_window_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_availability_status"),
        "meal_plan_availability",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_meal_plan_availability_status"), table_name="meal_plan_availability")
    op.drop_index(
        op.f("ix_meal_plan_availability_pickup_window_id"),
        table_name="meal_plan_availability",
    )
    op.drop_index(op.f("ix_meal_plan_availability_meal_plan_id"), table_name="meal_plan_availability")
    op.drop_index(op.f("ix_meal_plan_availability_vendor_id"), table_name="meal_plan_availability")
    op.drop_table("meal_plan_availability")

    op.drop_index(op.f("ix_meal_plan_items_vendor_menu_item_id"), table_name="meal_plan_items")
    op.drop_index(op.f("ix_meal_plan_items_meal_plan_id"), table_name="meal_plan_items")
    op.drop_index(op.f("ix_meal_plan_items_vendor_id"), table_name="meal_plan_items")
    op.drop_table("meal_plan_items")

    op.drop_index(
        op.f("ix_vendor_pickup_windows_pickup_start_at"),
        table_name="vendor_pickup_windows",
    )
    op.drop_index(op.f("ix_vendor_pickup_windows_status"), table_name="vendor_pickup_windows")
    op.drop_index(op.f("ix_vendor_pickup_windows_vendor_id"), table_name="vendor_pickup_windows")
    op.drop_table("vendor_pickup_windows")

    op.drop_index(op.f("ix_meal_plans_status"), table_name="meal_plans")
    op.drop_index(op.f("ix_meal_plans_vendor_id"), table_name="meal_plans")
    op.drop_table("meal_plans")

    op.drop_index(op.f("ix_vendor_menu_items_status"), table_name="vendor_menu_items")
    op.drop_index(op.f("ix_vendor_menu_items_vendor_id"), table_name="vendor_menu_items")
    op.drop_table("vendor_menu_items")

    op.drop_index(op.f("ix_vendors_status"), table_name="vendors")
    op.drop_index(op.f("ix_vendors_slug"), table_name="vendors")
    op.drop_table("vendors")
