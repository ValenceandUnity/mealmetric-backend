from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.core.app import create_app
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db


@pytest.fixture
def admin_vendor_api_client(
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


def test_admin_vendor_routes_require_signed_bff_and_admin_role(
    admin_vendor_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(admin_vendor_api_client, bff_headers, "admin")
    client_headers = _register_headers(admin_vendor_api_client, bff_headers, "client")

    missing_auth = admin_vendor_api_client.post(
        "/admin/vendors",
        json={"slug": "alpha", "name": "Alpha"},
        headers=bff_headers,
    )
    assert missing_auth.status_code == 401

    missing_bff = admin_vendor_api_client.post(
        "/admin/vendors",
        json={"slug": "alpha", "name": "Alpha"},
        headers={"Authorization": str(admin_headers["Authorization"])},
    )
    assert missing_bff.status_code == 401

    forbidden = admin_vendor_api_client.post(
        "/admin/vendors",
        json={"slug": "alpha", "name": "Alpha"},
        headers=client_headers,
    )
    assert forbidden.status_code == 403


def test_admin_vendor_catalog_full_mutation_flow(
    admin_vendor_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(admin_vendor_api_client, bff_headers, "admin")

    vendor_create = admin_vendor_api_client.post(
        "/admin/vendors",
        json={
            "slug": "alpha-vendor",
            "name": "Alpha Vendor",
            "description": "initial",
            "status": "draft",
        },
        headers=admin_headers,
    )
    assert vendor_create.status_code == 201
    vendor_id = UUID(str(vendor_create.json()["id"]))
    assert vendor_create.json()["meal_plan_count"] == 0

    vendor_update = admin_vendor_api_client.patch(
        f"/admin/vendors/{vendor_id}",
        json={
            "slug": "alpha-vendor",
            "name": "Alpha Vendor Updated",
            "description": "updated",
            "status": "active",
        },
        headers=admin_headers,
    )
    assert vendor_update.status_code == 200
    assert vendor_update.json()["status"] == "active"

    menu_item_create = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/menu-items",
        json={
            "slug": "protein-box",
            "name": "Protein Box",
            "description": "high protein",
            "status": "active",
            "price_cents": 1299,
            "currency_code": "USD",
            "calories": 550,
            "protein_grams": 45,
            "carbs_grams": 20,
            "fat_grams": 18,
        },
        headers=admin_headers,
    )
    assert menu_item_create.status_code == 201
    menu_item_id = UUID(str(menu_item_create.json()["id"]))

    menu_item_update = admin_vendor_api_client.patch(
        f"/admin/vendors/{vendor_id}/menu-items/{menu_item_id}",
        json={
            "slug": "protein-box",
            "name": "Protein Box Deluxe",
            "description": "high protein deluxe",
            "status": "active",
            "price_cents": 1499,
            "currency_code": "USD",
            "calories": 650,
            "protein_grams": 50,
            "carbs_grams": 22,
            "fat_grams": 20,
        },
        headers=admin_headers,
    )
    assert menu_item_update.status_code == 200
    assert menu_item_update.json()["name"] == "Protein Box Deluxe"

    meal_plan_create = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/meal-plans",
        json={
            "slug": "lean-week",
            "name": "Lean Week",
            "description": "lean plan",
            "status": "draft",
        },
        headers=admin_headers,
    )
    assert meal_plan_create.status_code == 201
    meal_plan_id = UUID(str(meal_plan_create.json()["id"]))

    meal_plan_update = admin_vendor_api_client.patch(
        f"/admin/vendors/{vendor_id}/meal-plans/{meal_plan_id}",
        json={
            "slug": "lean-week",
            "name": "Lean Week Published",
            "description": "lean plan published",
            "status": "published",
        },
        headers=admin_headers,
    )
    assert meal_plan_update.status_code == 200
    assert meal_plan_update.json()["status"] == "published"

    meal_plan_item_create = admin_vendor_api_client.post(
        f"/admin/meal-plans/{meal_plan_id}/items",
        json={
            "vendor_menu_item_id": str(menu_item_id),
            "quantity": 2,
            "position": 0,
            "notes": "main item",
        },
        headers=admin_headers,
    )
    assert meal_plan_item_create.status_code == 201
    meal_plan_item_id = UUID(str(meal_plan_item_create.json()["id"]))
    assert meal_plan_item_create.json()["quantity"] == 2

    meal_plan_item_update = admin_vendor_api_client.patch(
        f"/admin/meal-plans/{meal_plan_id}/items/{meal_plan_item_id}",
        json={
            "vendor_menu_item_id": str(menu_item_id),
            "quantity": 3,
            "position": 1,
            "notes": "updated item",
        },
        headers=admin_headers,
    )
    assert meal_plan_item_update.status_code == 200
    assert meal_plan_item_update.json()["quantity"] == 3
    assert meal_plan_item_update.json()["position"] == 1

    pickup_window_create = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/pickup-windows",
        json={
            "label": "Friday Pickup",
            "status": "scheduled",
            "pickup_start_at": "2026-03-20T17:00:00Z",
            "pickup_end_at": "2026-03-20T18:00:00Z",
            "order_cutoff_at": "2026-03-20T16:00:00Z",
            "notes": "window notes",
        },
        headers=admin_headers,
    )
    assert pickup_window_create.status_code == 201
    pickup_window_id = UUID(str(pickup_window_create.json()["id"]))

    pickup_window_update = admin_vendor_api_client.patch(
        f"/admin/vendors/{vendor_id}/pickup-windows/{pickup_window_id}",
        json={
            "label": "Friday Pickup Updated",
            "status": "open",
            "pickup_start_at": "2026-03-20T17:30:00Z",
            "pickup_end_at": "2026-03-20T18:30:00Z",
            "order_cutoff_at": "2026-03-20T16:30:00Z",
            "notes": "updated notes",
        },
        headers=admin_headers,
    )
    assert pickup_window_update.status_code == 200
    assert pickup_window_update.json()["status"] == "open"

    availability_create = admin_vendor_api_client.post(
        f"/admin/meal-plans/{meal_plan_id}/availability",
        json={
            "pickup_window_id": str(pickup_window_id),
            "status": "available",
            "inventory_count": 10,
        },
        headers=admin_headers,
    )
    assert availability_create.status_code == 201
    availability_id = UUID(str(availability_create.json()["id"]))

    availability_update = admin_vendor_api_client.patch(
        f"/admin/meal-plans/{meal_plan_id}/availability/{availability_id}",
        json={
            "pickup_window_id": str(pickup_window_id),
            "status": "scheduled",
            "inventory_count": 8,
        },
        headers=admin_headers,
    )
    assert availability_update.status_code == 200
    assert availability_update.json()["availability_status"] == "scheduled"

    availability_cancel = admin_vendor_api_client.post(
        f"/admin/meal-plans/{meal_plan_id}/availability/{availability_id}/cancel",
        headers=admin_headers,
    )
    assert availability_cancel.status_code == 200
    assert availability_cancel.json()["availability_status"] == "cancelled"

    pickup_window_cancel = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/pickup-windows/{pickup_window_id}/cancel",
        headers=admin_headers,
    )
    assert pickup_window_cancel.status_code == 200
    assert pickup_window_cancel.json()["status"] == "cancelled"

    menu_item_archive = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/menu-items/{menu_item_id}/archive",
        headers=admin_headers,
    )
    assert menu_item_archive.status_code == 200
    assert menu_item_archive.json()["status"] == "archived"

    meal_plan_archive = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/meal-plans/{meal_plan_id}/archive",
        headers=admin_headers,
    )
    assert meal_plan_archive.status_code == 200
    assert meal_plan_archive.json()["status"] == "archived"

    item_delete = admin_vendor_api_client.delete(
        f"/admin/meal-plans/{meal_plan_id}/items/{meal_plan_item_id}",
        headers=admin_headers,
    )
    assert item_delete.status_code == 204

    vendor_archive = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_id}/archive",
        headers=admin_headers,
    )
    assert vendor_archive.status_code == 200
    assert vendor_archive.json()["status"] == "archived"


def test_admin_vendor_catalog_conflict_validation_and_not_found_paths(
    admin_vendor_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(admin_vendor_api_client, bff_headers, "admin")

    vendor_a = admin_vendor_api_client.post(
        "/admin/vendors",
        json={"slug": "vendor-a", "name": "Vendor A", "status": "active"},
        headers=admin_headers,
    )
    assert vendor_a.status_code == 201
    vendor_a_id = UUID(str(vendor_a.json()["id"]))

    duplicate_vendor = admin_vendor_api_client.post(
        "/admin/vendors",
        json={"slug": "vendor-a", "name": "Vendor A Duplicate", "status": "draft"},
        headers=admin_headers,
    )
    assert duplicate_vendor.status_code == 409
    assert duplicate_vendor.json() == {"detail": "vendor_already_exists"}

    vendor_b = admin_vendor_api_client.post(
        "/admin/vendors",
        json={"slug": "vendor-b", "name": "Vendor B", "status": "active"},
        headers=admin_headers,
    )
    assert vendor_b.status_code == 201
    vendor_b_id = UUID(str(vendor_b.json()["id"]))

    menu_item_b = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_b_id}/menu-items",
        json={
            "slug": "vendor-b-item",
            "name": "Vendor B Item",
            "status": "active",
            "price_cents": 999,
            "currency_code": "USD",
            "calories": 300,
            "protein_grams": 20,
            "carbs_grams": 15,
            "fat_grams": 10,
        },
        headers=admin_headers,
    )
    assert menu_item_b.status_code == 201
    menu_item_b_id = UUID(str(menu_item_b.json()["id"]))

    meal_plan_a = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_a_id}/meal-plans",
        json={"slug": "plan-a", "name": "Plan A", "status": "draft"},
        headers=admin_headers,
    )
    assert meal_plan_a.status_code == 201
    meal_plan_a_id = UUID(str(meal_plan_a.json()["id"]))

    cross_vendor_item = admin_vendor_api_client.post(
        f"/admin/meal-plans/{meal_plan_a_id}/items",
        json={
            "vendor_menu_item_id": str(menu_item_b_id),
            "quantity": 1,
            "position": 0,
        },
        headers=admin_headers,
    )
    assert cross_vendor_item.status_code == 422
    assert cross_vendor_item.json() == {"detail": "meal_plan_item_vendor_mismatch"}

    missing_vendor = admin_vendor_api_client.patch(
        f"/admin/vendors/{uuid4()}",
        json={"slug": "missing", "name": "Missing", "status": "draft", "description": None},
        headers=admin_headers,
    )
    assert missing_vendor.status_code == 404
    assert missing_vendor.json() == {"detail": "vendor_not_found"}

    invalid_window = admin_vendor_api_client.post(
        f"/admin/vendors/{vendor_a_id}/pickup-windows",
        json={
            "label": "Invalid Window",
            "status": "scheduled",
            "pickup_start_at": "2026-03-20T18:00:00Z",
            "pickup_end_at": "2026-03-20T17:00:00Z",
            "order_cutoff_at": None,
            "notes": None,
        },
        headers=admin_headers,
    )
    assert invalid_window.status_code == 422
    assert invalid_window.json() == {"detail": "vendor_pickup_window_time_order_invalid"}


def test_existing_metrics_and_training_routes_remain_unchanged(
    admin_vendor_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(admin_vendor_api_client, bff_headers, "admin")
    pt_headers = _register_headers(admin_vendor_api_client, bff_headers, "pt")

    metrics_response = admin_vendor_api_client.get("/metrics", headers=admin_headers)
    assert metrics_response.status_code == 200
    assert "mealmetric_http_requests_total" in metrics_response.text

    pt_profile_response = admin_vendor_api_client.get("/pt/profile/me", headers=pt_headers)
    assert pt_profile_response.status_code == 404

    admin_forbidden_on_pt = admin_vendor_api_client.get("/pt/profile/me", headers=admin_headers)
    assert admin_forbidden_on_pt.status_code == 403
