import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from mealmetric.models.order import OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItemType
from mealmetric.models.recommendation import MealPlanRecommendationStatus
from mealmetric.models.vendor import MealPlanStatus, VendorPickupWindowStatus


class ClientOrderItemRead(BaseModel):
    id: uuid.UUID
    item_type: OrderItemType
    external_price_id: str | None
    description: str | None
    quantity: int
    unit_amount_cents: int
    subtotal_amount_cents: int
    tax_amount_cents: int
    total_amount_cents: int
    created_at: datetime


class ClientOrderMealPlanRead(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: MealPlanStatus
    total_price_cents: int
    total_calories: int
    item_count: int
    availability_count: int


class ClientOrderPickupWindowRead(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    label: str | None
    status: VendorPickupWindowStatus
    pickup_start_at: datetime
    pickup_end_at: datetime
    order_cutoff_at: datetime | None
    notes: str | None


class ClientOrderRecommendationRead(BaseModel):
    id: uuid.UUID
    pt_user_id: uuid.UUID
    client_user_id: uuid.UUID
    meal_plan_id: uuid.UUID
    status: MealPlanRecommendationStatus
    rationale: str | None
    recommended_at: datetime
    expires_at: datetime | None
    is_expired: bool


class ClientOrderRead(BaseModel):
    id: uuid.UUID
    payment_session_id: uuid.UUID
    client_user_id: uuid.UUID
    order_payment_status: OrderPaymentStatus
    fulfillment_status: OrderFulfillmentStatus
    currency: str
    subtotal_amount_cents: int
    tax_amount_cents: int
    total_amount_cents: int
    created_at: datetime
    updated_at: datetime
    meal_plan_context_type: Literal["direct_or_assigned", "pt_recommended"]
    meal_plan: ClientOrderMealPlanRead | None
    pickup_window: ClientOrderPickupWindowRead | None
    pt_recommendation: ClientOrderRecommendationRead | None
    items: list[ClientOrderItemRead]


class ClientOrderListResponse(BaseModel):
    items: list[ClientOrderRead]
    count: int
