import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.db.base import Base
from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.models.subscription import (
    MealPlanSubscription,
    MealPlanSubscriptionStatus,
    SubscriptionBillingInterval,
)
from mealmetric.models.user import Role, User
from mealmetric.models.vendor import MealPlan, MealPlanStatus, Vendor, VendorStatus
from mealmetric.services.reconciliation_service import ReconciliationService


def _build_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return session_local()


def test_reconciliation_detects_expected_mismatch_scenarios() -> None:
    session = _build_session()
    user = User(email="reconcile@example.com", password_hash="pw", role=Role.CLIENT)
    vendor = Vendor(slug="reconcile-vendor", name="Reconcile Vendor", status=VendorStatus.ACTIVE)
    session.add_all([user, vendor])
    session.flush()
    meal_plan = MealPlan(
        vendor_id=vendor.id,
        slug="reconcile-plan",
        name="Reconcile Plan",
        status=MealPlanStatus.PUBLISHED,
    )
    session.add(meal_plan)
    session.flush()

    successful_without_order = PaymentSession(
        user_id=user.id,
        stripe_checkout_session_id="cs_reconcile_missing_order",
        stripe_payment_intent_id="pi_reconcile_missing_order",
        payment_status=PaymentStatus.PAYMENT_INTENT_SUCCEEDED,
        basket_snapshot={
            "currency": "usd",
            "items": [
                {
                    "quantity": 1,
                    "unit_amount_cents": 100,
                    "subtotal_amount_cents": 100,
                    "tax_amount_cents": 0,
                    "total_amount_cents": 100,
                }
            ],
        },
    )
    successful_without_order.id = uuid.uuid4()
    session.add(successful_without_order)

    successful_with_order = PaymentSession(
        user_id=user.id,
        stripe_checkout_session_id="cs_reconcile_has_order",
        stripe_payment_intent_id="pi_reconcile_has_order",
        payment_status=PaymentStatus.PAYMENT_INTENT_SUCCEEDED,
    )
    successful_with_order.id = uuid.uuid4()
    session.add(successful_with_order)
    session.flush()
    session.add(
        Order(
            payment_session_id=successful_with_order.id,
            client_user_id=user.id,
            order_payment_status=OrderPaymentStatus.PAID,
            fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
            currency="usd",
            subtotal_amount_cents=100,
            tax_amount_cents=0,
            total_amount_cents=100,
        )
    )

    old_failed_webhook = StripeWebhookEvent(
        stripe_event_id="evt_reconcile_failed",
        event_type="checkout.session.completed",
        processing_status=WebhookProcessingStatus.FAILED,
        payload={"id": "evt_reconcile_failed"},
        payload_sha256="a" * 64,
        request_id="req_reconcile_failed",
        processing_error="event_processing_failed",
        received_at=datetime.now(UTC) - timedelta(hours=1),
    )
    old_processing_webhook = StripeWebhookEvent(
        stripe_event_id="evt_reconcile_processing",
        event_type="invoice.paid",
        processing_status=WebhookProcessingStatus.PROCESSING,
        payload={"id": "evt_reconcile_processing"},
        payload_sha256="b" * 64,
        request_id="req_reconcile_processing",
        received_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add_all([old_failed_webhook, old_processing_webhook])

    session.add(
        MealPlanSubscription(
            stripe_subscription_id="sub_reconcile_missing_link",
            stripe_customer_id="cus_reconcile_1",
            client_user_id=user.id,
            meal_plan_id=meal_plan.id,
            status=MealPlanSubscriptionStatus.ACTIVE,
            billing_interval=SubscriptionBillingInterval.MONTH,
            latest_stripe_event_id=None,
        )
    )
    session.commit()

    report = ReconciliationService(session).run(stale_window_seconds=300)

    assert [item.checkout_session_id for item in report.payment_sessions_missing_orders] == [
        "cs_reconcile_missing_order"
    ]
    assert [item.stripe_event_id for item in report.webhook_processing_gaps] == [
        "evt_reconcile_failed",
        "evt_reconcile_processing",
    ]
    assert [
        item.stripe_subscription_id for item in report.subscriptions_missing_lifecycle_linkage
    ] == ["sub_reconcile_missing_link"]
