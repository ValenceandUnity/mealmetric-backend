import json
import uuid
from dataclasses import dataclass

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.db.base import Base
from mealmetric.models.subscription import MealPlanSubscription, MealPlanSubscriptionStatus
from mealmetric.models.user import Role, User
from mealmetric.models.vendor import MealPlan, MealPlanStatus, Vendor, VendorStatus
from mealmetric.services.stripe_webhook_service import StripeWebhookIngressService


@dataclass
class _FakeSettings:
    stripe_webhook_secret: str = "whsec_test_123"
    stripe_api_version: str | None = None
    stripe_webhook_mode: str = "process"


@dataclass
class _FakeStripeEvent:
    id: str
    type: str


def _build_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return session_local()


def _seed_client_and_meal_plan(session: Session) -> tuple[User, MealPlan]:
    user = User(email="client@example.com", password_hash="pw", role=Role.CLIENT)
    vendor = Vendor(slug="alpha", name="Alpha Vendor", status=VendorStatus.ACTIVE)
    session.add_all([user, vendor])
    session.flush()
    meal_plan = MealPlan(
        vendor_id=vendor.id,
        slug="weekly-plan",
        name="Weekly Plan",
        status=MealPlanStatus.PUBLISHED,
    )
    session.add(meal_plan)
    session.commit()
    return user, meal_plan


def _subscription_payload(
    *,
    subscription_id: str,
    customer_id: str,
    client_user_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    status: str = "active",
    event_type: str = "customer.subscription.created",
    current_period_start: int = 1760000000,
    current_period_end: int = 1762592000,
) -> bytes:
    return json.dumps(
        {
            "id": f"evt_{subscription_id}_{event_type.replace('.', '_')}",
            "type": event_type,
            "data": {
                "object": {
                    "id": subscription_id,
                    "customer": customer_id,
                    "status": status,
                    "metadata": {
                        "client_user_id": str(client_user_id),
                        "meal_plan_id": str(meal_plan_id),
                    },
                    "items": {
                        "data": [
                            {"price": {"recurring": {"interval": "week"}}},
                        ]
                    },
                    "current_period_start": current_period_start,
                    "current_period_end": current_period_end,
                    "cancel_at_period_end": False,
                    "canceled_at": None,
                }
            },
        }
    ).encode("utf-8")


def _invoice_payload(
    *,
    invoice_id: str,
    subscription_id: str,
    customer_id: str,
    event_type: str,
    created: int = 1762592000,
    period_start: int = 1762592000,
    period_end: int = 1765184000,
) -> bytes:
    return json.dumps(
        {
            "id": f"evt_{invoice_id}_{event_type.replace('.', '_')}",
            "type": event_type,
            "data": {
                "object": {
                    "id": invoice_id,
                    "subscription": subscription_id,
                    "customer": customer_id,
                    "created": created,
                    "status_transitions": {
                        "paid_at": created if event_type == "invoice.paid" else None
                    },
                    "lines": {
                        "data": [
                            {"period": {"start": period_start, "end": period_end}},
                        ]
                    },
                }
            },
        }
    ).encode("utf-8")


def test_subscription_created_event_is_persisted_and_duplicate_delivery_is_idempotent() -> None:
    session = _build_session()
    user, meal_plan = _seed_client_and_meal_plan(session)
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]
    payload = _subscription_payload(
        subscription_id="sub_created_1",
        customer_id="cus_123",
        client_user_id=user.id,
        meal_plan_id=meal_plan.id,
    )

    first = service.ingest_event(
        session=session,
        event=_FakeStripeEvent(
            id="evt_sub_created_1",
            type="customer.subscription.created",
        ),
        payload=payload,
        request_id="req_sub_created_1",
    )
    second = service.ingest_event(
        session=session,
        event=_FakeStripeEvent(
            id="evt_sub_created_1",
            type="customer.subscription.created",
        ),
        payload=payload,
        request_id="req_sub_created_2",
    )

    rows = session.scalars(select(MealPlanSubscription)).all()
    assert first.duplicate is False
    assert second.duplicate is True
    assert len(rows) == 1
    assert rows[0].stripe_subscription_id == "sub_created_1"
    assert rows[0].status == MealPlanSubscriptionStatus.ACTIVE


def test_invoice_paid_updates_subscription_renewal_state() -> None:
    session = _build_session()
    user, meal_plan = _seed_client_and_meal_plan(session)
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    service.ingest_event(
        session=session,
        event=_FakeStripeEvent(
            id="evt_sub_seed_paid",
            type="customer.subscription.created",
        ),
        payload=_subscription_payload(
            subscription_id="sub_paid_1",
            customer_id="cus_paid_1",
            client_user_id=user.id,
            meal_plan_id=meal_plan.id,
            status="trialing",
        ),
        request_id="req_sub_seed_paid",
    )

    service.ingest_event(
        session=session,
        event=_FakeStripeEvent(id="evt_invoice_paid_1", type="invoice.paid"),
        payload=_invoice_payload(
            invoice_id="in_paid_1",
            subscription_id="sub_paid_1",
            customer_id="cus_paid_1",
            event_type="invoice.paid",
        ),
        request_id="req_invoice_paid_1",
    )

    subscription = session.scalar(
        select(MealPlanSubscription).where(
            MealPlanSubscription.stripe_subscription_id == "sub_paid_1"
        )
    )
    assert subscription is not None
    assert subscription.status == MealPlanSubscriptionStatus.ACTIVE
    assert subscription.latest_invoice_id == "in_paid_1"
    assert subscription.current_period_end is not None
    assert subscription.last_invoice_paid_at is not None


def test_invoice_payment_failed_marks_subscription_past_due() -> None:
    session = _build_session()
    user, meal_plan = _seed_client_and_meal_plan(session)
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    service.ingest_event(
        session=session,
        event=_FakeStripeEvent(
            id="evt_sub_seed_failed",
            type="customer.subscription.created",
        ),
        payload=_subscription_payload(
            subscription_id="sub_failed_1",
            customer_id="cus_failed_1",
            client_user_id=user.id,
            meal_plan_id=meal_plan.id,
        ),
        request_id="req_sub_seed_failed",
    )

    service.ingest_event(
        session=session,
        event=_FakeStripeEvent(id="evt_invoice_failed_1", type="invoice.payment_failed"),
        payload=_invoice_payload(
            invoice_id="in_failed_1",
            subscription_id="sub_failed_1",
            customer_id="cus_failed_1",
            event_type="invoice.payment_failed",
        ),
        request_id="req_invoice_failed_1",
    )

    subscription = session.scalar(
        select(MealPlanSubscription).where(
            MealPlanSubscription.stripe_subscription_id == "sub_failed_1"
        )
    )
    assert subscription is not None
    assert subscription.status == MealPlanSubscriptionStatus.PAST_DUE
    assert subscription.latest_invoice_id == "in_failed_1"
    assert subscription.last_invoice_failed_at is not None
