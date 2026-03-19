from collections.abc import Generator
from datetime import UTC, date, datetime
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
from mealmetric.models.metrics import (
    ActivityExpenditureRecord,
    CalorieIntakeRecord,
    DeficitTarget,
    DeficitTargetStatus,
)


@pytest.fixture
def client_metrics_api_client(
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


def _current_user_id(client: TestClient, headers: dict[str, str]) -> UUID:
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    return UUID(str(response.json()["id"]))


def _seed_client_week_records(
    client: TestClient,
    user_headers: dict[str, str],
    calories: int,
    expenditure: int,
) -> None:
    user_id = _current_user_id(client, user_headers)
    app = cast(FastAPI, client.app)
    session_local = cast(sessionmaker[Session], app.state.testing_session_local)

    with session_local() as db:
        db.add(
            CalorieIntakeRecord(
                client_user_id=user_id,
                recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                business_date=date(2026, 3, 17),
                calories=calories,
            )
        )
        db.add(
            ActivityExpenditureRecord(
                client_user_id=user_id,
                recorded_at=datetime(2026, 3, 17, 18, 0, tzinfo=UTC),
                business_date=date(2026, 3, 17),
                expenditure_calories=expenditure,
            )
        )
        db.add(
            DeficitTarget(
                client_user_id=user_id,
                target_daily_deficit_calories=500,
                status=DeficitTargetStatus.ACTIVE,
                effective_from_date=date(2026, 3, 1),
            )
        )
        db.commit()


def test_client_metrics_requires_signed_bff_and_auth(
    client_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_metrics_api_client, bff_headers, "client")

    missing_bff = client_metrics_api_client.get(
        "/metrics/overview",
        headers={"Authorization": str(client_headers["Authorization"])},
    )
    assert missing_bff.status_code == 401

    missing_jwt = client_metrics_api_client.get("/metrics/overview", headers=bff_headers)
    assert missing_jwt.status_code == 401


def test_client_role_required_for_client_metrics(
    client_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(client_metrics_api_client, bff_headers, "admin")
    response = client_metrics_api_client.get("/metrics/overview", headers=admin_headers)
    assert response.status_code == 403


def test_client_metrics_self_only_visibility(
    client_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client1_headers = _register_headers(client_metrics_api_client, bff_headers, "client")
    client2_headers = _register_headers(client_metrics_api_client, bff_headers, "client")

    _seed_client_week_records(
        client_metrics_api_client, client1_headers, calories=2200, expenditure=1800
    )

    client1_overview = client_metrics_api_client.get(
        "/metrics/overview",
        params={"as_of_date": "2026-03-18"},
        headers=client1_headers,
    )
    assert client1_overview.status_code == 200
    assert client1_overview.json()["total_intake_calories"] == 2200

    client2_overview = client_metrics_api_client.get(
        "/metrics/overview",
        params={"as_of_date": "2026-03-18"},
        headers=client2_headers,
    )
    assert client2_overview.status_code == 200
    assert client2_overview.json()["total_intake_calories"] == 0


def test_client_metrics_response_contract_and_freshness(
    client_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_metrics_api_client, bff_headers, "client")
    _seed_client_week_records(
        client_metrics_api_client, client_headers, calories=2000, expenditure=1500
    )

    overview = client_metrics_api_client.get(
        "/metrics/overview",
        params={"as_of_date": "2026-03-18"},
        headers=client_headers,
    )
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert "freshness" in overview_payload
    assert "source" in overview_payload["freshness"]
    assert overview_payload["weekly_target_deficit_calories"] == 3500

    weekly = client_metrics_api_client.get(
        "/metrics/weekly",
        params={"week_start_date": "2026-03-16"},
        headers=client_headers,
    )
    assert weekly.status_code == 200
    weekly_payload = weekly.json()
    assert weekly_payload["week_start_day"] == 1
    assert weekly_payload["business_timezone"] == "America/New_York"
    assert weekly_payload["weekly_target_deficit_calories"] == 3500
    assert weekly_payload["freshness"]["source"] == "raw"
    assert weekly_payload["freshness"]["version"] is None


def test_client_metrics_empty_state_and_history_validation(
    client_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_metrics_api_client, bff_headers, "client")

    overview = client_metrics_api_client.get(
        "/metrics/overview",
        params={"as_of_date": "2026-03-18"},
        headers=client_headers,
    )
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["has_data"] is False
    assert payload["freshness"]["source"] == "empty"

    history = client_metrics_api_client.get(
        "/metrics/history",
        params={"weeks": 3, "as_of_date": "2026-03-18"},
        headers=client_headers,
    )
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["count"] == 3

    too_low = client_metrics_api_client.get(
        "/metrics/history",
        params={"weeks": 0},
        headers=client_headers,
    )
    assert too_low.status_code == 422

    too_high = client_metrics_api_client.get(
        "/metrics/history",
        params={"weeks": 53},
        headers=client_headers,
    )
    assert too_high.status_code == 422


def test_prometheus_metrics_route_unchanged(
    client_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(client_metrics_api_client, bff_headers, "admin")

    response = client_metrics_api_client.get("/metrics", headers=admin_headers)
    assert response.status_code == 200
    assert "mealmetric_http_requests_total" in response.text
