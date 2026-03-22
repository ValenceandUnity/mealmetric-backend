from collections.abc import Generator
from datetime import UTC, datetime
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
from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory, AuditLog
from mealmetric.models.recommendation import (
    MealPlanRecommendation,
    MealPlanRecommendationStatus,
)
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
def meal_plan_recommendations_api_client(
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
    link = PtClientLink(
        pt_user_id=pt_user_id,
        client_user_id=client_user_id,
        status=status,
    )
    db.add(link)
    db.flush()
    return link


def _create_vendor_catalog(db: Session) -> tuple[UUID, UUID, UUID]:
    vendor = Vendor(slug="alpha", name="Alpha Vendor", status=VendorStatus.ACTIVE)
    db.add(vendor)
    db.flush()

    active_item = VendorMenuItem(
        vendor_id=vendor.id,
        slug="protein-box",
        name="Protein Box",
        price_cents=1200,
        calories=500,
        status=VendorMenuItemStatus.ACTIVE,
    )
    second_item = VendorMenuItem(
        vendor_id=vendor.id,
        slug="greens-box",
        name="Greens Box",
        price_cents=800,
        calories=250,
        status=VendorMenuItemStatus.ACTIVE,
    )
    hidden_item = VendorMenuItem(
        vendor_id=vendor.id,
        slug="hidden-box",
        name="Hidden Box",
        price_cents=600,
        calories=200,
        status=VendorMenuItemStatus.ARCHIVED,
    )
    db.add_all([active_item, second_item, hidden_item])
    db.flush()

    visible_plan = MealPlan(
        vendor_id=vendor.id,
        slug="lean-pack",
        name="Lean Pack",
        status=MealPlanStatus.PUBLISHED,
    )
    hidden_plan = MealPlan(
        vendor_id=vendor.id,
        slug="hidden-pack",
        name="Hidden Pack",
        status=MealPlanStatus.PUBLISHED,
    )
    db.add_all([visible_plan, hidden_plan])
    db.flush()

    db.add_all(
        [
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=visible_plan.id,
                vendor_menu_item_id=active_item.id,
                quantity=2,
                position=0,
            ),
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=visible_plan.id,
                vendor_menu_item_id=second_item.id,
                quantity=1,
                position=1,
            ),
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=hidden_plan.id,
                vendor_menu_item_id=active_item.id,
                quantity=1,
                position=0,
            ),
            MealPlanItem(
                vendor_id=vendor.id,
                meal_plan_id=hidden_plan.id,
                vendor_menu_item_id=hidden_item.id,
                quantity=1,
                position=1,
            ),
        ]
    )
    db.flush()

    visible_window = VendorPickupWindow(
        vendor_id=vendor.id,
        label="Friday Pickup",
        pickup_start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
        pickup_end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
        status=VendorPickupWindowStatus.SCHEDULED,
    )
    hidden_window = VendorPickupWindow(
        vendor_id=vendor.id,
        label="Saturday Pickup",
        pickup_start_at=datetime(2026, 3, 21, 17, 0, tzinfo=UTC),
        pickup_end_at=datetime(2026, 3, 21, 18, 0, tzinfo=UTC),
        status=VendorPickupWindowStatus.OPEN,
    )
    db.add_all([visible_window, hidden_window])
    db.flush()

    db.add_all(
        [
            MealPlanAvailability(
                vendor_id=vendor.id,
                meal_plan_id=visible_plan.id,
                pickup_window_id=visible_window.id,
                status=MealPlanAvailabilityStatus.AVAILABLE,
                inventory_count=5,
            ),
            MealPlanAvailability(
                vendor_id=vendor.id,
                meal_plan_id=hidden_plan.id,
                pickup_window_id=hidden_window.id,
                status=MealPlanAvailabilityStatus.SOLD_OUT,
                inventory_count=0,
            ),
        ]
    )
    db.flush()
    db.commit()

    return vendor.id, visible_plan.id, hidden_plan.id


def _create_recommendation(
    db: Session,
    *,
    pt_user_id: UUID,
    client_user_id: UUID,
    meal_plan_id: UUID,
    recommended_at: datetime,
    rationale: str,
    status: MealPlanRecommendationStatus = MealPlanRecommendationStatus.ACTIVE,
) -> MealPlanRecommendation:
    recommendation = MealPlanRecommendation(
        pt_user_id=pt_user_id,
        client_user_id=client_user_id,
        meal_plan_id=meal_plan_id,
        status=status,
        rationale=rationale,
        recommended_at=recommended_at,
    )
    db.add(recommendation)
    db.flush()
    return recommendation


def test_recommendation_routes_require_signed_bff_jwt_and_expected_roles(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    client_headers, client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        db.commit()

    missing_bff = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        headers={"Authorization": str(pt_headers["Authorization"])},
    )
    assert missing_bff.status_code == 401

    missing_jwt = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        headers=bff_headers,
    )
    assert missing_jwt.status_code == 401

    forbidden_pt_scope = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        headers=client_headers,
    )
    assert forbidden_pt_scope.status_code == 403

    forbidden_client_scope = meal_plan_recommendations_api_client.get(
        "/client/meal-plan-recommendations",
        headers=pt_headers,
    )
    assert forbidden_client_scope.status_code == 403


def test_recommendation_routes_return_stable_empty_lists(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    client_headers, client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        db.commit()

    pt_response = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        headers=pt_headers,
    )
    assert pt_response.status_code == 200
    assert pt_response.json() == {"items": [], "count": 0}

    client_response = meal_plan_recommendations_api_client.get(
        "/client/meal-plan-recommendations",
        headers=client_headers,
    )
    assert client_response.status_code == 200
    assert client_response.json() == {"items": [], "count": 0}


def test_pt_can_create_and_read_only_scoped_recommendations(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    _, second_pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    _, second_client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )
    _, client_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "client")

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _, visible_plan_id, _ = _create_vendor_catalog(db)
        _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        _create_link(db, pt_user_id=second_pt_user_id, client_user_id=client_user_id)
        _create_link(db, pt_user_id=pt_user_id, client_user_id=second_client_user_id)
        _create_recommendation(
            db,
            pt_user_id=second_pt_user_id,
            client_user_id=client_user_id,
            meal_plan_id=visible_plan_id,
            recommended_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            rationale="Other PT recommendation",
        )
        _create_recommendation(
            db,
            pt_user_id=pt_user_id,
            client_user_id=second_client_user_id,
            meal_plan_id=visible_plan_id,
            recommended_at=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
            rationale="Different client recommendation",
        )
        db.commit()

    create_response = meal_plan_recommendations_api_client.post(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        json={
            "meal_plan_id": str(visible_plan_id),
            "rationale": "High protein fit",
            "recommended_at": "2026-03-16T10:00:00Z",
        },
        headers=pt_headers,
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["rationale"] == "High protein fit"
    assert created_payload["pt"]["id"] == str(pt_user_id)
    assert created_payload["meal_plan"]["slug"] == "lean-pack"
    assert created_payload["meal_plan_is_currently_discoverable"] is True
    assert created_payload["meal_plan_is_currently_available"] is True
    assert created_payload["is_expired"] is False

    list_response = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        headers=pt_headers,
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["pt_user_id"] == str(pt_user_id)
    assert payload["items"][0]["pt"]["id"] == str(pt_user_id)
    assert payload["items"][0]["client_user_id"] == str(client_user_id)
    assert payload["items"][0]["rationale"] == "High protein fit"

    with _session_local(meal_plan_recommendations_api_client)() as db:
        audit_rows = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.action == AuditEventAction.MEAL_PLAN_RECOMMENDATION_CREATED)
                .order_by(AuditLog.created_at.asc())
            )
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].category == AuditEventCategory.RECOMMENDATION
        assert audit_rows[0].actor_user_id == pt_user_id
        assert audit_rows[0].request_id is not None
        assert audit_rows[0].metadata_json["client_user_id"] == str(client_user_id)
        assert audit_rows[0].metadata_json["meal_plan_id"] == str(visible_plan_id)
        assert audit_rows[0].metadata_json["rationale"] == "High protein fit"


def test_pt_create_contract_forbids_status_override_and_allows_historical_duplicates(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    _, client_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "client")

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _, visible_plan_id, _ = _create_vendor_catalog(db)
        _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        db.commit()

    rejected_status = meal_plan_recommendations_api_client.post(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        json={
            "meal_plan_id": str(visible_plan_id),
            "rationale": "Attempted override",
            "status": "withdrawn",
        },
        headers=pt_headers,
    )
    assert rejected_status.status_code == 422

    first_create = meal_plan_recommendations_api_client.post(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        json={
            "meal_plan_id": str(visible_plan_id),
            "rationale": "First active recommendation",
            "recommended_at": "2026-03-16T09:00:00Z",
        },
        headers=pt_headers,
    )
    assert first_create.status_code == 201
    assert first_create.json()["status"] == "active"

    second_create = meal_plan_recommendations_api_client.post(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        json={
            "meal_plan_id": str(visible_plan_id),
            "rationale": "Second active recommendation",
            "recommended_at": "2026-03-17T09:00:00Z",
        },
        headers=pt_headers,
    )
    assert second_create.status_code == 201
    assert second_create.json()["status"] == "active"

    list_response = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        headers=pt_headers,
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] == 2
    assert [item["rationale"] for item in payload["items"]] == [
        "Second active recommendation",
        "First active recommendation",
    ]


def test_pt_create_and_read_are_blocked_after_link_end(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    _, client_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "client")
    _, ended_client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _, visible_plan_id, _ = _create_vendor_catalog(db)
        _create_link(
            db,
            pt_user_id=pt_user_id,
            client_user_id=ended_client_user_id,
            status=PtClientLinkStatus.ENDED,
        )
        db.commit()

    unlinked_response = meal_plan_recommendations_api_client.post(
        f"/pt/clients/{client_user_id}/meal-plan-recommendations",
        json={"meal_plan_id": str(visible_plan_id), "rationale": "No link"},
        headers=pt_headers,
    )
    assert unlinked_response.status_code == 403
    assert unlinked_response.json() == {"detail": "pt_client_link_not_active"}

    ended_response = meal_plan_recommendations_api_client.post(
        f"/pt/clients/{ended_client_user_id}/meal-plan-recommendations",
        json={"meal_plan_id": str(visible_plan_id), "rationale": "Ended link"},
        headers=pt_headers,
    )
    assert ended_response.status_code == 403
    assert ended_response.json() == {"detail": "pt_client_link_not_active"}

    ended_list = meal_plan_recommendations_api_client.get(
        f"/pt/clients/{ended_client_user_id}/meal-plan-recommendations",
        headers=pt_headers,
    )
    assert ended_list.status_code == 403
    assert ended_list.json() == {"detail": "pt_client_link_not_active"}


def test_client_reads_only_own_historical_recommendations_and_expiry_is_explicit(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    _, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    _, second_pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    client_headers, client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )
    _, second_client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _, visible_plan_id, hidden_plan_id = _create_vendor_catalog(db)
        active_link = _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        historical_link = _create_link(
            db,
            pt_user_id=second_pt_user_id,
            client_user_id=client_user_id,
            status=PtClientLinkStatus.ENDED,
        )
        _create_link(db, pt_user_id=pt_user_id, client_user_id=second_client_user_id)

        active_link.status = PtClientLinkStatus.ACTIVE
        historical_link.status = PtClientLinkStatus.ENDED

        _create_recommendation(
            db,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
            meal_plan_id=visible_plan_id,
            recommended_at=datetime(2026, 3, 16, 9, 0, tzinfo=UTC),
            rationale="Visible recommendation",
        )
        expired_hidden_recommendation = _create_recommendation(
            db,
            pt_user_id=second_pt_user_id,
            client_user_id=client_user_id,
            meal_plan_id=hidden_plan_id,
            recommended_at=datetime(2026, 3, 17, 9, 0, tzinfo=UTC),
            rationale="Historical hidden recommendation",
        )
        expired_hidden_recommendation.expires_at = datetime(2026, 3, 16, 10, 0, tzinfo=UTC)
        _create_recommendation(
            db,
            pt_user_id=pt_user_id,
            client_user_id=second_client_user_id,
            meal_plan_id=visible_plan_id,
            recommended_at=datetime(2026, 3, 18, 9, 0, tzinfo=UTC),
            rationale="Other client recommendation",
        )
        db.commit()

    response = meal_plan_recommendations_api_client.get(
        "/client/meal-plan-recommendations",
        headers=client_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [item["rationale"] for item in payload["items"]] == [
        "Historical hidden recommendation",
        "Visible recommendation",
    ]
    assert payload["items"][0]["meal_plan"]["slug"] == "hidden-pack"
    assert payload["items"][0]["pt"]["id"] == str(second_pt_user_id)
    assert payload["items"][0]["meal_plan_is_currently_discoverable"] is False
    assert payload["items"][0]["meal_plan_is_currently_available"] is False
    assert payload["items"][0]["is_expired"] is True
    assert payload["items"][1]["meal_plan"]["slug"] == "lean-pack"
    assert payload["items"][1]["pt"]["id"] == str(pt_user_id)
    assert payload["items"][1]["meal_plan_is_currently_discoverable"] is True
    assert payload["items"][1]["meal_plan_is_currently_available"] is True
    assert payload["items"][1]["is_expired"] is False


def test_metrics_and_existing_training_vendor_and_admin_flows_remain_stable(
    meal_plan_recommendations_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers, pt_user_id = _register_user(meal_plan_recommendations_api_client, bff_headers, "pt")
    client_headers, client_user_id = _register_user(
        meal_plan_recommendations_api_client, bff_headers, "client"
    )
    admin_headers, _ = _register_user(meal_plan_recommendations_api_client, bff_headers, "admin")

    with _session_local(meal_plan_recommendations_api_client)() as db:
        _create_vendor_catalog(db)
        _create_link(db, pt_user_id=pt_user_id, client_user_id=client_user_id)
        db.commit()

    metrics_response = meal_plan_recommendations_api_client.get("/metrics", headers=admin_headers)
    assert metrics_response.status_code == 200
    assert "mealmetric_http_requests_total" in metrics_response.text

    vendor_discovery_response = meal_plan_recommendations_api_client.get(
        "/vendors",
        headers=client_headers,
    )
    assert vendor_discovery_response.status_code == 200
    assert vendor_discovery_response.json()["count"] == 1

    pt_search_response = meal_plan_recommendations_api_client.get(
        "/pt/meal-plans/search",
        headers=pt_headers,
    )
    assert pt_search_response.status_code == 200
    assert pt_search_response.json()["count"] == 1

    pt_training_response = meal_plan_recommendations_api_client.get(
        "/pt/profile/me",
        headers=pt_headers,
    )
    assert pt_training_response.status_code == 404

    admin_vendor_response = meal_plan_recommendations_api_client.post(
        "/admin/vendors",
        json={
            "slug": "new-admin-vendor",
            "name": "New Admin Vendor",
            "status": "draft",
        },
        headers=admin_headers,
    )
    assert admin_vendor_response.status_code == 201
