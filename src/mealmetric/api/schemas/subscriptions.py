import uuid
from datetime import datetime

from pydantic import BaseModel

from mealmetric.models.subscription import (
    MealPlanSubscriptionStatus,
    SubscriptionBillingInterval,
    SubscriptionInvoiceStatus,
)


class SubscriptionMealPlanRead(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str


class SubscriptionRead(BaseModel):
    id: uuid.UUID
    stripe_subscription_id: str
    stripe_customer_id: str | None
    client_user_id: uuid.UUID
    meal_plan_id: uuid.UUID
    status: MealPlanSubscriptionStatus
    billing_interval: SubscriptionBillingInterval
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    latest_invoice_id: str | None
    latest_invoice_status: SubscriptionInvoiceStatus | None
    latest_stripe_event_id: str | None
    last_invoice_paid_at: datetime | None
    last_invoice_failed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    meal_plan: SubscriptionMealPlanRead | None


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionRead]
    count: int
