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
def pt_meal_plans_api_client(
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


def _seed_catalog(client: TestClient) -> UUID:
    app = cast(FastAPI, client.app)
    session_local = cast(sessionmaker[Session], app.state.testing_session_local)

    with session_local() as db:
        vendor = _create_vendor(db, slug="alpha", name="Alpha Vendor")
        item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="protein-box",
            price_cents=1200,
            calories=500,
        )
        second_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="greens-box",
            price_cents=700,
            calories=250,
        )
        hidden_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="hidden-box",
            price_cents=400,
            calories=100,
            status=VendorMenuItemStatus.ARCHIVED,
        )

        visible_plan = _create_meal_plan(
            db, vendor_id=vendor.id, slug="lean-pack", name="Lean Pack"
        )
        filtered_plan = _create_meal_plan(
            db, vendor_id=vendor.id, slug="hidden-pack", name="Hidden Pack"
        )

        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=visible_plan.id,
            vendor_menu_item_id=item.id,
            position=0,
            quantity=2,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=visible_plan.id,
            vendor_menu_item_id=second_item.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=filtered_plan.id,
            vendor_menu_item_id=item.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=filtered_plan.id,
            vendor_menu_item_id=hidden_item.id,
            position=1,
        )

        visible_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 28, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 28, 18, 0, tzinfo=UTC),
            label="Saturday Pickup",
        )
        sold_out_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 29, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 29, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.OPEN,
            label="Sunday Pickup",
        )

        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=visible_plan.id,
            pickup_window_id=visible_window.id,
            inventory_count=4,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=filtered_plan.id,
            pickup_window_id=sold_out_window.id,
            status=MealPlanAvailabilityStatus.SOLD_OUT,
            inventory_count=0,
        )
        db.commit()

    return vendor.id


def test_pt_meal_plan_search_requires_signed_bff_jwt_and_pt_role(
    pt_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_meal_plans_api_client, bff_headers, "pt")
    client_headers = _register_headers(pt_meal_plans_api_client, bff_headers, "client")

    missing_bff = pt_meal_plans_api_client.get(
        "/pt/meal-plans/search", headers={"Authorization": str(pt_headers["Authorization"])}
    )
    assert missing_bff.status_code == 401

    missing_jwt = pt_meal_plans_api_client.get("/pt/meal-plans/search", headers=bff_headers)
    assert missing_jwt.status_code == 401

    forbidden = pt_meal_plans_api_client.get("/pt/meal-plans/search", headers=client_headers)
    assert forbidden.status_code == 403


def test_pt_meal_plan_search_empty_state_and_discoverable_filtering(
    pt_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_meal_plans_api_client, bff_headers, "pt")

    empty = pt_meal_plans_api_client.get("/pt/meal-plans/search", headers=pt_headers)
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "count": 0}

    vendor_id = _seed_catalog(pt_meal_plans_api_client)

    search = pt_meal_plans_api_client.get(
        "/pt/meal-plans/search",
        headers=pt_headers,
    )
    assert search.status_code == 200
    payload = search.json()
    assert payload["count"] == 1
    assert [item["slug"] for item in payload["items"]] == ["lean-pack"]
    assert payload["items"][0]["total_price_cents"] == 3100
    assert payload["items"][0]["total_calories"] == 1250

    filtered = pt_meal_plans_api_client.get(
        "/pt/meal-plans/search",
        params={
            "vendor_id": str(vendor_id),
            "available_on": "2026-03-28",
            "price_min_cents": 3000,
            "calorie_min": 1200,
        },
        headers=pt_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 1
    assert filtered.json()["items"][0]["slug"] == "lean-pack"


def test_pt_meal_plan_search_invalid_date_and_regression_routes_remain_stable(
    pt_meal_plans_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_meal_plans_api_client, bff_headers, "pt")
    admin_headers = _register_headers(pt_meal_plans_api_client, bff_headers, "admin")

    invalid_date = pt_meal_plans_api_client.get(
        "/pt/meal-plans/search",
        params={"available_on": "2026-99-99"},
        headers=pt_headers,
    )
    assert invalid_date.status_code == 422
    assert invalid_date.json() == {"detail": "invalid_available_on"}

    metrics_response = pt_meal_plans_api_client.get("/metrics", headers=admin_headers)
    assert metrics_response.status_code == 200
    assert "mealmetric_http_requests_total" in metrics_response.text

    pt_metrics_response = pt_meal_plans_api_client.get(
        "/pt/metrics/comparison",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert pt_metrics_response.status_code == 200
    assert pt_metrics_response.json()["count"] == 0

    pt_training_response = pt_meal_plans_api_client.get(
        "/pt/profile/me",
        headers=pt_headers,
    )
    assert pt_training_response.status_code == 404
