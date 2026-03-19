from collections.abc import Generator
from datetime import UTC, datetime, tzinfo
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.core.app import create_app
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db
from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItem, OrderItemType
from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.models.recommendation import MealPlanRecommendation, MealPlanRecommendationStatus
from mealmetric.models.training import PtClientLink, PtClientLinkStatus
from mealmetric.models.user import User
from mealmetric.models.vendor import (
    MealPlan,
    MealPlanAvailability,
    MealPlanAvailabilityStatus,
    MealPlanItem,
    MealPlanStatus,
    Vendor,
    VendorMenuItem,
    VendorMenuItemStatus,
    VendorPickupWindow,
    VendorPickupWindowStatus,
    VendorStatus,
)


@pytest.fixture
def client_orders_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("RATE_LIMIT_RPS", "1000")
    get_settings.cache_clear()
    app = create_app()

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
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )
    app.state.testing_session_local = testing_session_local

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


def _session_local(client: TestClient) -> sessionmaker[Session]:
    app = cast(FastAPI, client.app)
    return cast(sessionmaker[Session], app.state.testing_session_local)


def _register_user(
    client: TestClient,
    bff_headers: dict[str, str],
    role: str,
) -> tuple[dict[str, str], UUID]:
    email = f"{role}-{uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": role},
        headers=bff_headers,
    )
    assert response.status_code == 201
    token = str(response.json()["access_token"])

    with _session_local(client)() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user_id = user.id

    return {"Authorization": f"Bearer {token}", **bff_headers}, user_id


def _create_link(
    db: Session,
    *,
    pt_user_id: UUID,
    client_user_id: UUID,
    status: PtClientLinkStatus = PtClientLinkStatus.ACTIVE,
) -> PtClientLink:
    link = PtClientLink(pt_user_id=pt_user_id, client_user_id=client_user_id, status=status)
    db.add(link)
    db.flush()
    return link


def _create_catalog(
    db: Session,
) -> tuple[MealPlan, MealPlan, VendorPickupWindow, VendorPickupWindow]:
    vendor = Vendor(slug="alpha", name="Alpha Vendor", status=VendorStatus.ACTIVE)
    db.add(vendor)
    db.flush()

    item_a = VendorMenuItem(
        vendor_id=vendor.id,
        slug="protein-box",
        name="Protein Box",
        price_cents=1200,
        calories=500,
        status=VendorMenuItemStatus.ACTIVE,
    )
    item_b = VendorMenuItem(
        vendor_id=vendor.id,
        slug="greens-box",
        name="Greens Box",
        price_cents=800,
        calories=250,
        status=VendorMenuItemStatus.ACTIVE,
    )
    db.add_all([item_a, item_b])
    db.flush()

    direct_plan = MealPlan(
        vendor_id=vendor.id,
        slug="lean-pack",
        name="Lean Pack",
        status=MealPlanStatus.PUBLISHED,
    )
    recommended_plan = MealPlan(
        vendor_id=vendor.id,
        slug="recovery-pack",
        name="Recovery Pack",
        status=MealPlanStatus.PUBLISHED,
    )
    db.add_all([direct_plan, recommended_plan])
    db.flush()

    db.add_all(
        [
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=direct_plan.id,
                vendor_menu_item_id=item_a.id,
                quantity=1,
                position=0,
            ),
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=direct_plan.id,
                vendor_menu_item_id=item_b.id,
                quantity=1,
                position=1,
            ),
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=recommended_plan.id,
                vendor_menu_item_id=item_a.id,
                quantity=2,
                position=0,
            ),
        ]
    )
    db.flush()

    past_window = VendorPickupWindow(
        vendor_id=vendor.id,
        label="Past Pickup",
        pickup_start_at=datetime(2026, 3, 15, 17, 0, tzinfo=UTC),
        pickup_end_at=datetime(2026, 3, 15, 18, 0, tzinfo=UTC),
        status=VendorPickupWindowStatus.SCHEDULED,
    )
    future_window = VendorPickupWindow(
        vendor_id=vendor.id,
        label="Future Pickup",
        pickup_start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
        pickup_end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
        status=VendorPickupWindowStatus.OPEN,
    )
    db.add_all([past_window, future_window])
    db.flush()

    db.add_all(
        [
            MealPlanAvailability(
                vendor_id=vendor.id,
                meal_plan_id=direct_plan.id,
                pickup_window_id=past_window.id,
                status=MealPlanAvailabilityStatus.AVAILABLE,
                inventory_count=5,
            ),
            MealPlanAvailability(
                vendor_id=vendor.id,
                meal_plan_id=recommended_plan.id,
                pickup_window_id=future_window.id,
                status=MealPlanAvailabilityStatus.AVAILABLE,
                inventory_count=5,
            ),
        ]
    )
    db.flush()
    return direct_plan, recommended_plan, past_window, future_window


def _create_payment_session(
    db: Session,
    *,
    user_id: UUID,
    checkout_session_id: str,
    payment_intent_id: str,
    basket_snapshot: dict[str, object],
) -> PaymentSession:
    payment_session = PaymentSession(
        user_id=user_id,
        stripe_checkout_session_id=checkout_session_id,
        stripe_payment_intent_id=payment_intent_id,
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        basket_snapshot=basket_snapshot,
    )
    db.add(payment_session)
    db.flush()
    return payment_session


def _create_order(
    db: Session,
    *,
    payment_session_id: UUID,
    client_user_id: UUID,
    created_at: datetime,
    amount_cents: int,
) -> Order:
    order = Order(
        payment_session_id=payment_session_id,
        client_user_id=client_user_id,
        order_payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
        currency="usd",
        subtotal_amount_cents=amount_cents,
        tax_amount_cents=0,
        total_amount_cents=amount_cents,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(order)
    db.flush()
    return order


def _add_order_item(db: Session, *, order_id: UUID, description: str, amount_cents: int) -> None:
    db.add(
        OrderItem(
            order_id=order_id,
            item_type=OrderItemType.PRODUCT,
            description=description,
            quantity=1,
            unit_amount_cents=amount_cents,
            subtotal_amount_cents=amount_cents,
            tax_amount_cents=0,
            total_amount_cents=amount_cents,
        )
    )
    db.flush()


def _seed_orders(
    client: TestClient,
    *,
    client_user_id: UUID,
    other_client_user_id: UUID,
    pt_user_id: UUID,
) -> tuple[UUID, UUID, UUID, UUID]:
    with _session_local(client)() as db:
        direct_plan, recommended_plan, past_window, future_window = _create_catalog(db)
        _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        _create_link(db, pt_user_id=pt_user_id, client_user_id=other_client_user_id)

        grounded_recommendation = MealPlanRecommendation(
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
            meal_plan_id=recommended_plan.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="Recovery-focused recommendation",
            recommended_at=datetime(2026, 3, 16, 9, 0, tzinfo=UTC),
        )
        unrelated_recommendation = MealPlanRecommendation(
            pt_user_id=pt_user_id,
            client_user_id=other_client_user_id,
            meal_plan_id=recommended_plan.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="Other client recommendation",
            recommended_at=datetime(2026, 3, 16, 10, 0, tzinfo=UTC),
        )
        db.add_all([grounded_recommendation, unrelated_recommendation])
        db.flush()

        direct_payment_session = _create_payment_session(
            db,
            user_id=client_user_id,
            checkout_session_id="cs_direct_client",
            payment_intent_id="pi_direct_client",
            basket_snapshot={
                "currency": "usd",
                "meal_plan_id": str(direct_plan.id),
                "pickup_window_id": str(past_window.id),
                "items": [
                    {
                        "item_type": "product",
                        "description": "Lean Pack",
                        "quantity": 1,
                        "unit_amount_cents": 2000,
                        "subtotal_amount_cents": 2000,
                        "tax_amount_cents": 0,
                        "total_amount_cents": 2000,
                    }
                ],
            },
        )
        recommended_payment_session = _create_payment_session(
            db,
            user_id=client_user_id,
            checkout_session_id="cs_recommended_client",
            payment_intent_id="pi_recommended_client",
            basket_snapshot={
                "currency": "usd",
                "meal_plan_id": str(recommended_plan.id),
                "pickup_window_id": str(future_window.id),
                "recommendation_id": str(grounded_recommendation.id),
                "items": [
                    {
                        "item_type": "product",
                        "description": "Recovery Pack",
                        "quantity": 1,
                        "unit_amount_cents": 3200,
                        "subtotal_amount_cents": 3200,
                        "tax_amount_cents": 0,
                        "total_amount_cents": 3200,
                    }
                ],
            },
        )
        ungrounded_payment_session = _create_payment_session(
            db,
            user_id=client_user_id,
            checkout_session_id="cs_ungrounded_client",
            payment_intent_id="pi_ungrounded_client",
            basket_snapshot={
                "currency": "usd",
                "meal_plan_id": str(recommended_plan.id),
                "pickup_window_id": str(future_window.id),
                "recommendation_id": str(unrelated_recommendation.id),
                "items": [
                    {
                        "item_type": "product",
                        "description": "Recovery Pack Alt",
                        "quantity": 1,
                        "unit_amount_cents": 3100,
                        "subtotal_amount_cents": 3100,
                        "tax_amount_cents": 0,
                        "total_amount_cents": 3100,
                    }
                ],
            },
        )
        other_client_payment_session = _create_payment_session(
            db,
            user_id=other_client_user_id,
            checkout_session_id="cs_other_client",
            payment_intent_id="pi_other_client",
            basket_snapshot={
                "currency": "usd",
                "meal_plan_id": str(recommended_plan.id),
                "pickup_window_id": str(future_window.id),
                "items": [
                    {
                        "item_type": "product",
                        "description": "Other Client Order",
                        "quantity": 1,
                        "unit_amount_cents": 3000,
                        "subtotal_amount_cents": 3000,
                        "tax_amount_cents": 0,
                        "total_amount_cents": 3000,
                    }
                ],
            },
        )

        direct_order = _create_order(
            db,
            payment_session_id=direct_payment_session.id,
            client_user_id=client_user_id,
            created_at=datetime(2026, 3, 16, 11, 0, tzinfo=UTC),
            amount_cents=2000,
        )
        recommended_order = _create_order(
            db,
            payment_session_id=recommended_payment_session.id,
            client_user_id=client_user_id,
            created_at=datetime(2026, 3, 17, 9, 0, tzinfo=UTC),
            amount_cents=3200,
        )
        ungrounded_order = _create_order(
            db,
            payment_session_id=ungrounded_payment_session.id,
            client_user_id=client_user_id,
            created_at=datetime(2026, 3, 17, 8, 0, tzinfo=UTC),
            amount_cents=3100,
        )
        other_client_order = _create_order(
            db,
            payment_session_id=other_client_payment_session.id,
            client_user_id=other_client_user_id,
            created_at=datetime(2026, 3, 17, 7, 0, tzinfo=UTC),
            amount_cents=3000,
        )

        _add_order_item(db, order_id=direct_order.id, description="Lean Pack", amount_cents=2000)
        _add_order_item(
            db,
            order_id=recommended_order.id,
            description="Recovery Pack",
            amount_cents=3200,
        )
        _add_order_item(
            db,
            order_id=ungrounded_order.id,
            description="Recovery Pack Alt",
            amount_cents=3100,
        )
        _add_order_item(
            db,
            order_id=other_client_order.id,
            description="Other Client Order",
            amount_cents=3000,
        )
        db.commit()

    return direct_order.id, recommended_order.id, ungrounded_order.id, other_client_order.id


def test_client_orders_require_signed_bff_jwt_and_client_role(
    client_orders_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers, _ = _register_user(client_orders_api_client, bff_headers, "client")
    admin_headers, _ = _register_user(client_orders_api_client, bff_headers, "admin")

    missing_bff = client_orders_api_client.get(
        "/client/orders",
        headers={"Authorization": str(client_headers["Authorization"])},
    )
    assert missing_bff.status_code == 401

    missing_jwt = client_orders_api_client.get("/client/orders", headers=bff_headers)
    assert missing_jwt.status_code == 401

    forbidden = client_orders_api_client.get("/client/orders", headers=admin_headers)
    assert forbidden.status_code == 403


def test_client_reads_own_orders_successfully_and_cannot_read_another_clients_orders(
    client_orders_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers, client_user_id = _register_user(client_orders_api_client, bff_headers, "client")
    _, other_client_user_id = _register_user(client_orders_api_client, bff_headers, "client")
    _, pt_user_id = _register_user(client_orders_api_client, bff_headers, "pt")

    direct_order_id, recommended_order_id, ungrounded_order_id, other_client_order_id = (
        _seed_orders(
            client_orders_api_client,
            client_user_id=client_user_id,
            other_client_user_id=other_client_user_id,
            pt_user_id=pt_user_id,
        )
    )

    response = client_orders_api_client.get("/client/orders", headers=client_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert [UUID(item["id"]) for item in payload["items"]] == [
        recommended_order_id,
        ungrounded_order_id,
        direct_order_id,
    ]
    assert {item["client_user_id"] for item in payload["items"]} == {str(client_user_id)}
    assert str(other_client_order_id) not in {item["id"] for item in payload["items"]}


def test_client_orders_distinguish_direct_vs_pt_recommended_and_ground_recommendation_visibility(
    client_orders_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers, client_user_id = _register_user(client_orders_api_client, bff_headers, "client")
    _, other_client_user_id = _register_user(client_orders_api_client, bff_headers, "client")
    _, pt_user_id = _register_user(client_orders_api_client, bff_headers, "pt")

    _seed_orders(
        client_orders_api_client,
        client_user_id=client_user_id,
        other_client_user_id=other_client_user_id,
        pt_user_id=pt_user_id,
    )

    response = client_orders_api_client.get("/client/orders", headers=client_headers)
    assert response.status_code == 200
    payload = response.json()

    recommended = payload["items"][0]
    ungrounded = payload["items"][1]
    direct = payload["items"][2]

    assert recommended["meal_plan_context_type"] == "pt_recommended"
    assert recommended["meal_plan"]["slug"] == "recovery-pack"
    assert recommended["pickup_window"]["label"] == "Future Pickup"
    assert recommended["pt_recommendation"]["rationale"] == "Recovery-focused recommendation"

    assert ungrounded["meal_plan_context_type"] == "direct_or_assigned"
    assert ungrounded["meal_plan"]["slug"] == "recovery-pack"
    assert ungrounded["pt_recommendation"] is None

    assert direct["meal_plan_context_type"] == "direct_or_assigned"
    assert direct["meal_plan"]["slug"] == "lean-pack"
    assert direct["pickup_window"]["label"] == "Past Pickup"
    assert direct["pt_recommendation"] is None


def test_client_upcoming_pickups_only_return_future_relevant_records(
    client_orders_api_client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_headers, client_user_id = _register_user(client_orders_api_client, bff_headers, "client")
    _, other_client_user_id = _register_user(client_orders_api_client, bff_headers, "client")
    _, pt_user_id = _register_user(client_orders_api_client, bff_headers, "pt")

    _seed_orders(
        client_orders_api_client,
        client_user_id=client_user_id,
        other_client_user_id=other_client_user_id,
        pt_user_id=pt_user_id,
    )

    monkeypatch.setattr("mealmetric.services.order_service.datetime", FrozenDateTime)

    response = client_orders_api_client.get("/client/upcoming-pickups", headers=client_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [item["pickup_window"]["label"] for item in payload["items"]] == [
        "Future Pickup",
        "Future Pickup",
    ]


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> "FrozenDateTime":
        return cls(2026, 3, 17, 12, 0, tzinfo=tz or UTC)
