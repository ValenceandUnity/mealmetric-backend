from collections.abc import Generator
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.core.app import create_app
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db
from mealmetric.models.subscription import (
    MealPlanSubscription,
    MealPlanSubscriptionStatus,
    SubscriptionBillingInterval,
)
from mealmetric.models.user import User
from mealmetric.models.vendor import MealPlan, MealPlanStatus, Vendor, VendorStatus


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


def _seed_subscription(
    client: TestClient,
    *,
    client_user_id: UUID,
    stripe_subscription_id: str,
    status: MealPlanSubscriptionStatus,
) -> MealPlanSubscription:
    with _session_local(client)() as db:
        vendor = Vendor(
            slug=f"vendor-{stripe_subscription_id}",
            name=f"Vendor {stripe_subscription_id}",
            status=VendorStatus.ACTIVE,
        )
        db.add(vendor)
        db.flush()
        meal_plan = MealPlan(
            vendor_id=vendor.id,
            slug=f"meal-plan-{stripe_subscription_id}",
            name=f"Meal Plan {stripe_subscription_id}",
            status=MealPlanStatus.PUBLISHED,
        )
        db.add(meal_plan)
        db.flush()

        subscription = MealPlanSubscription(
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=f"cus_{stripe_subscription_id}",
            client_user_id=client_user_id,
            meal_plan_id=meal_plan.id,
            status=status,
            billing_interval=SubscriptionBillingInterval.WEEK,
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        return subscription


def _build_client() -> Generator[TestClient, None, None]:
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


def test_client_subscriptions_require_signed_bff_jwt_and_client_role(
    bff_headers: dict[str, str],
) -> None:
    client_gen = _build_client()
    client = next(client_gen)
    try:
        client_headers, _ = _register_user(client, bff_headers, "client")
        admin_headers, _ = _register_user(client, bff_headers, "admin")

        missing_bff = client.get(
            "/client/subscriptions",
            headers={"Authorization": str(client_headers["Authorization"])},
        )
        assert missing_bff.status_code == 401

        missing_jwt = client.get("/client/subscriptions", headers=bff_headers)
        assert missing_jwt.status_code == 401

        forbidden = client.get("/client/subscriptions", headers=admin_headers)
        assert forbidden.status_code == 403
    finally:
        client_gen.close()


def test_client_subscriptions_only_return_current_clients_records(
    bff_headers: dict[str, str],
) -> None:
    client_gen = _build_client()
    client = next(client_gen)
    try:
        client_headers, client_user_id = _register_user(client, bff_headers, "client")
        _, other_client_user_id = _register_user(client, bff_headers, "client")

        owned = _seed_subscription(
            client,
            client_user_id=client_user_id,
            stripe_subscription_id="sub_owned",
            status=MealPlanSubscriptionStatus.ACTIVE,
        )
        _seed_subscription(
            client,
            client_user_id=other_client_user_id,
            stripe_subscription_id="sub_other",
            status=MealPlanSubscriptionStatus.PAST_DUE,
        )

        response = client.get("/client/subscriptions", headers=client_headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["items"][0]["id"] == str(owned.id)
        assert payload["items"][0]["client_user_id"] == str(client_user_id)
        assert payload["items"][0]["meal_plan"]["slug"] == "meal-plan-sub_owned"
    finally:
        client_gen.close()


def test_admin_subscriptions_list_requires_admin_and_supports_status_filter(
    bff_headers: dict[str, str],
) -> None:
    client_gen = _build_client()
    client = next(client_gen)
    try:
        _, client_user_id = _register_user(client, bff_headers, "client")
        admin_headers, _ = _register_user(client, bff_headers, "admin")

        active = _seed_subscription(
            client,
            client_user_id=client_user_id,
            stripe_subscription_id="sub_active",
            status=MealPlanSubscriptionStatus.ACTIVE,
        )
        _seed_subscription(
            client,
            client_user_id=client_user_id,
            stripe_subscription_id="sub_past_due",
            status=MealPlanSubscriptionStatus.PAST_DUE,
        )

        response = client.get("/admin/subscriptions?status=active", headers=admin_headers)

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["items"][0]["id"] == str(active.id)
        assert payload["items"][0]["status"] == "active"
    finally:
        client_gen.close()
