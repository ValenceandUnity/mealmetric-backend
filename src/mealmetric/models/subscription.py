import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base

if TYPE_CHECKING:
    from mealmetric.models.user import User
    from mealmetric.models.vendor import MealPlan


class MealPlanSubscriptionStatus(StrEnum):
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"


class SubscriptionBillingInterval(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class SubscriptionInvoiceStatus(StrEnum):
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    DRAFT = "draft"
    OPEN = "open"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"
    UNKNOWN = "unknown"


class MealPlanSubscription(Base):
    __tablename__ = "meal_plan_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "stripe_subscription_id",
            name="uq_meal_plan_subscriptions_stripe_subscription_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    meal_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[MealPlanSubscriptionStatus] = mapped_column(
        Enum(
            MealPlanSubscriptionStatus,
            name="meal_plan_subscription_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=MealPlanSubscriptionStatus.INCOMPLETE,
        server_default=MealPlanSubscriptionStatus.INCOMPLETE.value,
        index=True,
    )
    billing_interval: Mapped[SubscriptionBillingInterval] = mapped_column(
        Enum(
            SubscriptionBillingInterval,
            name="subscription_billing_interval",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=SubscriptionBillingInterval.UNKNOWN,
        server_default=SubscriptionBillingInterval.UNKNOWN.value,
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latest_invoice_status: Mapped[SubscriptionInvoiceStatus | None] = mapped_column(
        Enum(
            SubscriptionInvoiceStatus,
            name="subscription_invoice_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=True,
    )
    latest_stripe_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_invoice_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_invoice_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")
    meal_plan: Mapped["MealPlan"] = relationship("MealPlan")
