"""add order persistence tables for phase f

Revision ID: c4b7d8e921af
Revises: a7d5b6e49123
Create Date: 2026-03-15 17:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4b7d8e921af"
down_revision: str | Sequence[str] | None = "a7d5b6e49123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


order_payment_status_enum = sa.Enum(
    "pending",
    "paid",
    "failed",
    name="order_payment_status",
    native_enum=False,
)

order_fulfillment_status_enum = sa.Enum(
    "unfulfilled",
    "fulfilled",
    "canceled",
    name="order_fulfillment_status",
    native_enum=False,
)

order_item_type_enum = sa.Enum(
    "product",
    "adjustment",
    name="order_item_type",
    native_enum=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "payment_sessions",
        sa.Column(
            "basket_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_session_id", sa.UUID(), nullable=False),
        sa.Column(
            "order_payment_status",
            order_payment_status_enum,
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "fulfillment_status",
            order_fulfillment_status_enum,
            server_default="unfulfilled",
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_amount_cents", sa.Integer(), nullable=False),
        sa.Column("tax_amount_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_amount_cents", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["payment_session_id"], ["payment_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_session_id", name="uq_orders_payment_session_id"),
    )
    op.create_index(
        op.f("ix_orders_payment_session_id"), "orders", ["payment_session_id"], unique=False
    )
    op.create_index(
        op.f("ix_orders_order_payment_status"),
        "orders",
        ["order_payment_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orders_fulfillment_status"),
        "orders",
        ["fulfillment_status"],
        unique=False,
    )
    op.create_index(op.f("ix_orders_created_at"), "orders", ["created_at"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column(
            "item_type",
            order_item_type_enum,
            server_default="product",
            nullable=False,
        ),
        sa.Column("external_price_id", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_amount_cents", sa.Integer(), nullable=False),
        sa.Column("subtotal_amount_cents", sa.Integer(), nullable=False),
        sa.Column("tax_amount_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_item_type"), "order_items", ["item_type"], unique=False)
    op.create_index(
        op.f("ix_order_items_external_price_id"),
        "order_items",
        ["external_price_id"],
        unique=False,
    )
    op.create_index(op.f("ix_order_items_created_at"), "order_items", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_order_items_created_at"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_external_price_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_item_type"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")

    op.drop_index(op.f("ix_orders_created_at"), table_name="orders")
    op.drop_index(op.f("ix_orders_fulfillment_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_order_payment_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_payment_session_id"), table_name="orders")
    op.drop_table("orders")

    op.drop_column("payment_sessions", "basket_snapshot")
