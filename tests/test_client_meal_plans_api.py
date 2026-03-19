from collections.abc import Generator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.core.app import create_app
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db
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
def client_meal_plans_api_client(
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


def _register_headers(client: TestClient, bff_headers: dict[str, str], role: str) -> dict[str, str]:
    email = f"{role}-{uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": role},
        headers=bff_headers,
    )
    assert response.status_code == 201
    token = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}", **bff_headers}


def _create_vendor(
    db: Session,
    *,
    slug: str,
    name: str,
    status: VendorStatus = VendorStatus.ACTIVE,
) -> Vendor:
    vendor = Vendor(slug=slug, name=name, status=status)
    db.add(vendor)
    db.flush()
    return vendor


def _create_menu_item(
    db: Session,
    *,
    vendor_id: UUID,
    slug: str,
    price_cents: int,
    calories: int,
    status: VendorMenuItemStatus = VendorMenuItemStatus.ACTIVE,
) -> VendorMenuItem:
    menu_item = VendorMenuItem(
        vendor_id=vendor_id,
        slug=slug,
        name=slug.replace("-", " ").title(),
        price_cents=price_cents,
        calories=calories,
        status=status,
    )
    db.add(menu_item)
    db.flush()
    return menu_item


def _create_meal_plan(
    db: Session,
    *,
    vendor_id: UUID,
    slug: str,
    name: str,
    status: MealPlanStatus = MealPlanStatus.PUBLISHED,
) -> MealPlan:
    meal_plan = MealPlan(vendor_id=vendor_id, slug=slug, name=name, status=status)
    db.add(meal_plan)
    db.flush()
    return meal_plan


def _create_meal_plan_item(
    db: Session,
    *,
    vendor_id: UUID,
    meal_plan_id: UUID,
    vendor_menu_item_id: UUID,
    position: int,
    quantity: int = 1,
) -> MealPlanItem:
    item = MealPlanItem(
        vendor_id=vendor_id,
        meal_plan_id=meal_plan_id,
        vendor_menu_item_id=vendor_menu_item_id,
        quantity=quantity,
        position=position,
    )
    db.add(item)
    db.flush()
    return item


def _create_pickup_window(
    db: Session,
    *,
    vendor_id: UUID,
    start_at: datetime,
    end_at: datetime,
    status: VendorPickupWindowStatus = VendorPickupWindowStatus.SCHEDULED,
    label: str = "Window",
) -> VendorPickupWindow:
    pickup_window = VendorPickupWindow(
        vendor_id=vendor_id,
        label=label,
        pickup_start_at=start_at,
        pickup_end_at=end_at,
        status=status,
    )
    db.add(pickup_window)
    db.flush()
    return pickup_window


def _create_availability(
    db: Session,
    *,
    vendor_id: UUID,
    meal_plan_id: UUID,
    pickup_window_id: UUID,
    status: MealPlanAvailabilityStatus = MealPlanAvailabilityStatus.AVAILABLE,
    inventory_count: int | None = None,
) -> MealPlanAvailability:
    availability = MealPlanAvailability(
        vendor_id=vendor_id,
        meal_plan_id=meal_plan_id,
        pickup_window_id=pickup_window_id,
        status=status,
        inventory_count=inventory_count,
    )
    db.add(availability)
    db.flush()
    return availability


def _seed_catalog(client: TestClient) -> tuple[UUID, UUID, UUID, UUID]:
    app = cast(FastAPI, client.app)
    session_local = cast(sessionmaker[Session], app.state.testing_session_local)

    with session_local() as db:
        alpha_vendor = _create_vendor(db, slug="alpha", name="Alpha Vendor")
        beta_vendor = _create_vendor(db, slug="beta", name="Beta Vendor")
        hidden_vendor = _create_vendor(
            db,
            slug="hidden",
            name="Hidden Vendor",
            status=VendorStatus.INACTIVE,
        )

        alpha_item_a = _create_menu_item(
            db,
            vendor_id=alpha_vendor.id,
            slug="protein-box",
            price_cents=1200,
            calories=500,
        )
        alpha_item_b = _create_menu_item(
            db,
            vendor_id=alpha_vendor.id,
            slug="greens-box",
            price_cents=800,
            calories=250,
        )
        hidden_item = _create_menu_item(
            db,
            vendor_id=alpha_vendor.id,
            slug="hidden-box",
            price_cents=600,
            calories=200,
            status=VendorMenuItemStatus.ARCHIVED,
        )
        beta_item = _create_menu_item(
            db,
            vendor_id=beta_vendor.id,
            slug="recovery-box",
            price_cents=1500,
            calories=700,
        )
        hidden_vendor_item = _create_menu_item(
            db,
            vendor_id=hidden_vendor.id,
            slug="hidden-vendor-item",
            price_cents=1000,
            calories=400,
        )

        alpha_plan = _create_meal_plan(
            db, vendor_id=alpha_vendor.id, slug="lean-pack", name="Lean Pack"
        )
        beta_plan = _create_meal_plan(
            db, vendor_id=beta_vendor.id, slug="bulk-pack", name="Bulk Pack"
        )
        hidden_plan = _create_meal_plan(
            db, vendor_id=alpha_vendor.id, slug="hidden-pack", name="Hidden Pack"
        )
        _create_meal_plan(
            db,
            vendor_id=alpha_vendor.id,
            slug="draft-pack",
            name="Draft Pack",
            status=MealPlanStatus.DRAFT,
        )
        hidden_vendor_plan = _create_meal_plan(
            db,
            vendor_id=hidden_vendor.id,
            slug="hidden-vendor-plan",
            name="Hidden Vendor Plan",
        )

        _create_meal_plan_item(
            db,
            vendor_id=alpha_vendor.id,
            meal_plan_id=alpha_plan.id,
            vendor_menu_item_id=alpha_item_b.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=alpha_vendor.id,
            meal_plan_id=alpha_plan.id,
            vendor_menu_item_id=alpha_item_a.id,
            position=0,
            quantity=2,
        )
        _create_meal_plan_item(
            db,
            vendor_id=beta_vendor.id,
            meal_plan_id=beta_plan.id,
            vendor_menu_item_id=beta_item.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=alpha_vendor.id,
            meal_plan_id=hidden_plan.id,
            vendor_menu_item_id=alpha_item_a.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=alpha_vendor.id,
            meal_plan_id=hidden_plan.id,
            vendor_menu_item_id=hidden_item.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=hidden_vendor.id,
            meal_plan_id=hidden_vendor_plan.id,
            vendor_menu_item_id=hidden_vendor_item.id,
            position=0,
        )

        alpha_window = _create_pickup_window(
            db,
            vendor_id=alpha_vendor.id,
            start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
            label="Friday Pickup",
        )
        beta_window = _create_pickup_window(
            db,
            vendor_id=beta_vendor.id,
            start_at=datetime(2026, 3, 21, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 21, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.OPEN,
            label="Saturday Pickup",
        )
        hidden_window = _create_pickup_window(
            db,
            vendor_id=hidden_vendor.id,
            start_at=datetime(2026, 3, 22, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 22, 18, 0, tzinfo=UTC),
            label="Hidden Pickup",
        )

        _create_availability(
            db,
            vendor_id=alpha_vendor.id,
            meal_plan_id=alpha_plan.id,
            pickup_window_id=alpha_window.id,
            inventory_count=5,
        )
        _create_availability(
            db,
            vendor_id=beta_vendor.id,
            meal_plan_id=beta_plan.id,
            pickup_window_id=beta_window.id,
            status=MealPlanAvailabilityStatus.SCHEDULED,
            inventory_count=None,
        )
        _create_availability(
            db,
            vendor_id=alpha_vendor.id,
            meal_plan_id=hidden_plan.id,
            pickup_window_id=alpha_window.id,
            inventory_count=5,
        )
        _create_availability(
            db,
            vendor_id=hidden_vendor.id,
            meal_plan_id=hidden_vendor_plan.id,
            pickup_window_id=hidden_window.id,
            inventory_count=5,
        )
        db.commit()

    return alpha_vendor.id, beta_vendor.id, alpha_plan.id, hidden_plan.id


def test_client_discovery_requires_signed_bff_jwt_and_client_role(
    client_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_meal_plans_api_client, bff_headers, "client")
    admin_headers = _register_headers(client_meal_plans_api_client, bff_headers, "admin")

    missing_bff = client_meal_plans_api_client.get(
        "/vendors", headers={"Authorization": str(client_headers["Authorization"])}
    )
    assert missing_bff.status_code == 401

    missing_jwt = client_meal_plans_api_client.get("/vendors", headers=bff_headers)
    assert missing_jwt.status_code == 401

    forbidden = client_meal_plans_api_client.get("/vendors", headers=admin_headers)
    assert forbidden.status_code == 403


def test_client_discovery_empty_states_are_stable(
    client_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_meal_plans_api_client, bff_headers, "client")

    vendors = client_meal_plans_api_client.get("/vendors", headers=client_headers)
    assert vendors.status_code == 200
    assert vendors.json() == {"items": [], "count": 0}

    meal_plans = client_meal_plans_api_client.get("/meal-plans", headers=client_headers)
    assert meal_plans.status_code == 200
    assert meal_plans.json() == {"items": [], "count": 0}


def test_client_discovery_lists_and_details_only_expose_discoverable_catalog(
    client_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_meal_plans_api_client, bff_headers, "client")
    alpha_vendor_id, beta_vendor_id, alpha_plan_id, hidden_plan_id = _seed_catalog(
        client_meal_plans_api_client
    )

    vendors = client_meal_plans_api_client.get("/vendors", headers=client_headers)
    assert vendors.status_code == 200
    vendor_payload = vendors.json()
    assert vendor_payload["count"] == 2
    assert [item["slug"] for item in vendor_payload["items"]] == ["alpha", "beta"]
    assert [item["meal_plan_count"] for item in vendor_payload["items"]] == [1, 1]

    vendor_detail = client_meal_plans_api_client.get(
        f"/vendors/{alpha_vendor_id}",
        headers=client_headers,
    )
    assert vendor_detail.status_code == 200
    vendor_detail_payload = vendor_detail.json()
    assert vendor_detail_payload["meal_plan_count"] == 1
    assert [item["slug"] for item in vendor_detail_payload["meal_plans"]] == ["lean-pack"]

    missing_vendor_detail = client_meal_plans_api_client.get(
        f"/vendors/{uuid4()}",
        headers=client_headers,
    )
    assert missing_vendor_detail.status_code == 404

    meal_plans = client_meal_plans_api_client.get("/meal-plans", headers=client_headers)
    assert meal_plans.status_code == 200
    meal_plan_payload = meal_plans.json()
    assert meal_plan_payload["count"] == 2
    assert [item["slug"] for item in meal_plan_payload["items"]] == ["bulk-pack", "lean-pack"]

    filtered = client_meal_plans_api_client.get(
        "/meal-plans",
        params={"vendor_id": str(alpha_vendor_id), "available_on": "2026-03-20"},
        headers=client_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 1
    assert filtered.json()["items"][0]["slug"] == "lean-pack"

    detail = client_meal_plans_api_client.get(
        f"/meal-plans/{alpha_plan_id}",
        headers=client_headers,
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["slug"] == "lean-pack"
    assert [item["slug"] for item in detail_payload["items"]] == ["protein-box", "greens-box"]
    assert detail_payload["total_price_cents"] == 3200
    assert detail_payload["total_calories"] == 1250
    assert detail_payload["availability"][0]["pickup_window_label"] == "Friday Pickup"

    availability = client_meal_plans_api_client.get(
        f"/meal-plans/{alpha_plan_id}/availability",
        headers=client_headers,
    )
    assert availability.status_code == 200
    availability_payload = availability.json()
    assert availability_payload["count"] == 1
    assert availability_payload["items"][0]["pickup_window_status"] == "scheduled"

    hidden_plan_detail = client_meal_plans_api_client.get(
        f"/meal-plans/{hidden_plan_id}",
        headers=client_headers,
    )
    assert hidden_plan_detail.status_code == 404

    hidden_plan_availability = client_meal_plans_api_client.get(
        f"/meal-plans/{hidden_plan_id}/availability",
        headers=client_headers,
    )
    assert hidden_plan_availability.status_code == 404

    beta_filter = client_meal_plans_api_client.get(
        "/meal-plans",
        params={"vendor_id": str(beta_vendor_id), "price_min_cents": 1400},
        headers=client_headers,
    )
    assert beta_filter.status_code == 200
    assert beta_filter.json()["count"] == 1
    assert beta_filter.json()["items"][0]["slug"] == "bulk-pack"


def test_client_discovery_invalid_date_and_regression_routes_remain_stable(
    client_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_meal_plans_api_client, bff_headers, "client")
    admin_headers = _register_headers(client_meal_plans_api_client, bff_headers, "admin")

    invalid_date = client_meal_plans_api_client.get(
        "/meal-plans",
        params={"available_on": "2026-99-99"},
        headers=client_headers,
    )
    assert invalid_date.status_code == 422
    assert invalid_date.json() == {"detail": "invalid_available_on"}

    metrics_response = client_meal_plans_api_client.get("/metrics", headers=admin_headers)
    assert metrics_response.status_code == 200
    assert "mealmetric_http_requests_total" in metrics_response.text

    client_metrics_response = client_meal_plans_api_client.get(
        "/metrics/overview",
        params={"as_of_date": "2026-03-18"},
        headers=client_headers,
    )
    assert client_metrics_response.status_code == 200
    assert client_metrics_response.json()["has_data"] is False

    client_training_response = client_meal_plans_api_client.get(
        "/client/training/assignments",
        headers=client_headers,
    )
    assert client_training_response.status_code == 200
    assert client_training_response.json() == {"items": [], "count": 0}
