import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from mealmetric.models.order import OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItemType
from mealmetric.models.stripe_webhook_event import WebhookProcessingStatus


class AdminWebhookEventSummary(BaseModel):
    stripe_event_id: str
    event_type: str
    processing_status: WebhookProcessingStatus
    payment_session_id: uuid.UUID | None
    payload_sha256: str
    request_id: str | None
    processing_error: str | None
    received_at: datetime
    processed_at: datetime | None


class AdminWebhookEventDetail(AdminWebhookEventSummary):
    payload: dict[str, object]


class AdminWebhookEventListResponse(BaseModel):
    items: list[AdminWebhookEventSummary]
    count: int


class AdminWebhookReplayResponse(BaseModel):
    stripe_event_id: str
    outcome: Literal["replayed", "noop", "failed"]
    processing_status: WebhookProcessingStatus | None
    detail: str


class AdminReconciliationPaymentMismatch(BaseModel):
    payment_session_id: uuid.UUID
    checkout_session_id: str
    payment_status: str


class AdminReconciliationWebhookMismatch(BaseModel):
    stripe_event_id: str
    event_type: str
    processing_status: WebhookProcessingStatus
    received_at: datetime
    processing_error: str | None


class AdminReconciliationSubscriptionMismatch(BaseModel):
    subscription_id: uuid.UUID
    stripe_subscription_id: str
    status: str


class AdminReconciliationReportResponse(BaseModel):
    generated_at: datetime
    stale_window_seconds: int
    payment_sessions_missing_orders: list[AdminReconciliationPaymentMismatch]
    webhook_processing_gaps: list[AdminReconciliationWebhookMismatch]
    subscriptions_missing_lifecycle_linkage: list[AdminReconciliationSubscriptionMismatch]


class AdminOrderItemRead(BaseModel):
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


class AdminOrderRead(BaseModel):
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
    items: list[AdminOrderItemRead]


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderRead]
    count: int
