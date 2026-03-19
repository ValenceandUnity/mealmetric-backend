"""add phase l subscription foundation

Revision ID: c7e9a21b4d5f
Revises: 4a7c9e1d2b3f
Create Date: 2026-03-17 07:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e9a21b4d5f"
down_revision: str | Sequence[str] | None = "4a7c9e1d2b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

meal_plan_subscription_status_enum = sa.Enum(
    "incomplete",
    "incomplete_expired",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "paused",
    name="meal_plan_subscription_status",
    native_enum=False,
    create_constraint=True,
)

subscription_billing_interval_enum = sa.Enum(
    "day",
    "week",
    "month",
    "year",
    "unknown",
    name="subscription_billing_interval",
    native_enum=False,
    create_constraint=True,
)

subscription_invoice_status_enum = sa.Enum(
    "paid",
    "payment_failed",
    "draft",
    "open",
    "uncollectible",
    "void",
    "unknown",
    name="subscription_invoice_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "meal_plan_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("meal_plan_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            meal_plan_subscription_status_enum,
            server_default="incomplete",
            nullable=False,
        ),
        sa.Column(
            "billing_interval",
            subscription_billing_interval_enum,
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("latest_invoice_status", subscription_invoice_status_enum, nullable=True),
        sa.Column("latest_stripe_event_id", sa.String(length=255), nullable=True),
        sa.Column("last_invoice_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_invoice_failed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["meal_plan_id"], ["meal_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stripe_subscription_id",
            name="uq_meal_plan_subscriptions_stripe_subscription_id",
        ),
    )
    op.create_index(
        op.f("ix_meal_plan_subscriptions_client_user_id"),
        "meal_plan_subscriptions",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_subscriptions_meal_plan_id"),
        "meal_plan_subscriptions",
        ["meal_plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_subscriptions_status"),
        "meal_plan_subscriptions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_subscriptions_stripe_customer_id"),
        "meal_plan_subscriptions",
        ["stripe_customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_plan_subscriptions_stripe_subscription_id"),
        "meal_plan_subscriptions",
        ["stripe_subscription_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_meal_plan_subscriptions_stripe_subscription_id"),
        table_name="meal_plan_subscriptions",
    )
    op.drop_index(
        op.f("ix_meal_plan_subscriptions_stripe_customer_id"),
        table_name="meal_plan_subscriptions",
    )
    op.drop_index(op.f("ix_meal_plan_subscriptions_status"), table_name="meal_plan_subscriptions")
    op.drop_index(
        op.f("ix_meal_plan_subscriptions_meal_plan_id"),
        table_name="meal_plan_subscriptions",
    )
    op.drop_index(
        op.f("ix_meal_plan_subscriptions_client_user_id"),
        table_name="meal_plan_subscriptions",
    )
    op.drop_table("meal_plan_subscriptions")
