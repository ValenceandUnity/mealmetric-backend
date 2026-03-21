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
from mealmetric.models.training import PtClientLink, PtClientLinkStatus


@pytest.fixture
def pt_metrics_api_client(
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


def _register_headers(
    client: TestClient, bff_headers: dict[str, str], role: str
) -> dict[str, str]:
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


def _seed_pt_client_link(
    client: TestClient,
    *,
    pt_headers: dict[str, str],
    client_headers: dict[str, str],
    status: PtClientLinkStatus,
) -> None:
    pt_id = _current_user_id(client, pt_headers)
    client_id = _current_user_id(client, client_headers)
    app = cast(FastAPI, client.app)
    session_local = cast(sessionmaker[Session], app.state.testing_session_local)

    with session_local() as db:
        db.add(
            PtClientLink(
                pt_user_id=pt_id,
                client_user_id=client_id,
                status=status,
            )
        )
        db.commit()


def _seed_client_week_records(
    client: TestClient,
    *,
    client_headers: dict[str, str],
    calories: int,
    expenditure: int,
) -> None:
    user_id = _current_user_id(client, client_headers)
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


def test_pt_metrics_requires_signed_bff_and_auth(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    client_id = uuid4()

    missing_bff = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics",
        headers={"Authorization": str(pt_headers["Authorization"])},
    )
    assert missing_bff.status_code == 401

    missing_jwt = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics",
        headers=bff_headers,
    )
    assert missing_jwt.status_code == 401


def test_pt_role_required_for_pt_metrics(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")
    client_id = _current_user_id(pt_metrics_api_client, client_headers)

    response = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics",
        headers=client_headers,
    )
    assert response.status_code == 403


def test_pt_metrics_requires_active_link(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    linked_client_headers = _register_headers(
        pt_metrics_api_client, bff_headers, "client"
    )
    unlinked_client_headers = _register_headers(
        pt_metrics_api_client, bff_headers, "client"
    )

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=linked_client_headers,
        status=PtClientLinkStatus.PENDING,
    )
    pending_client_id = _current_user_id(pt_metrics_api_client, linked_client_headers)

    pending = pt_metrics_api_client.get(
        f"/pt/clients/{pending_client_id}/metrics",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert pending.status_code == 403

    app = cast(FastAPI, pt_metrics_api_client.app)
    session_local = cast(sessionmaker[Session], app.state.testing_session_local)
    with session_local() as db:
        db.query(PtClientLink).delete()
        db.commit()

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=linked_client_headers,
        status=PtClientLinkStatus.ENDED,
    )
    ended = pt_metrics_api_client.get(
        f"/pt/clients/{pending_client_id}/metrics",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert ended.status_code == 403

    unlinked_client_id = _current_user_id(
        pt_metrics_api_client, unlinked_client_headers
    )
    unlinked = pt_metrics_api_client.get(
        f"/pt/clients/{unlinked_client_id}/metrics",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert unlinked.status_code == 403


def test_pt_single_client_metrics_success_overview_weekly_history(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    client_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=client_headers,
        status=PtClientLinkStatus.ACTIVE,
    )
    _seed_client_week_records(
        pt_metrics_api_client,
        client_headers=client_headers,
        calories=2100,
        expenditure=1700,
    )
    client_id = _current_user_id(pt_metrics_api_client, client_headers)

    overview = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["client_user_id"] == str(client_id)
    assert overview_payload["total_intake_calories"] == 2100
    assert overview_payload["weekly_target_deficit_calories"] == 3500

    weekly = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics/weekly",
        params={"week_start_date": "2026-03-16"},
        headers=pt_headers,
    )
    assert weekly.status_code == 200
    weekly_payload = weekly.json()
    assert weekly_payload["client_user_id"] == str(client_id)
    assert weekly_payload["as_of_date"] == "2026-03-22"
    assert weekly_payload["total_expenditure_calories"] == 1700
    assert weekly_payload["freshness"]["source"] == "raw"

    history = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics/history",
        params={"weeks": 3, "as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["client_user_id"] == str(client_id)
    assert history_payload["count"] == 3
    assert history_payload["week_start_date"] == "2026-03-16"


def test_pt_metrics_empty_state_and_history_bounds(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    client_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=client_headers,
        status=PtClientLinkStatus.ACTIVE,
    )
    client_id = _current_user_id(pt_metrics_api_client, client_headers)

    overview = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["has_data"] is False
    assert overview_payload["freshness"]["source"] == "empty"

    history = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics/history",
        params={"weeks": 1, "as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert history.status_code == 200
    assert history.json()["freshness"]["source"] == "empty"

    too_low = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics/history",
        params={"weeks": 0},
        headers=pt_headers,
    )
    assert too_low.status_code == 422

    too_high = pt_metrics_api_client.get(
        f"/pt/clients/{client_id}/metrics/history",
        params={"weeks": 53},
        headers=pt_headers,
    )
    assert too_high.status_code == 422


def test_pt_comparison_returns_only_linked_clients_stable_ordering(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    client_a_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")
    client_b_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=client_b_headers,
        status=PtClientLinkStatus.ACTIVE,
    )
    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=client_a_headers,
        status=PtClientLinkStatus.ACTIVE,
    )

    _seed_client_week_records(
        pt_metrics_api_client,
        client_headers=client_a_headers,
        calories=1000,
        expenditure=700,
    )
    _seed_client_week_records(
        pt_metrics_api_client,
        client_headers=client_b_headers,
        calories=2000,
        expenditure=1200,
    )

    response = pt_metrics_api_client.get(
        "/pt/metrics/comparison",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    ids = [UUID(item["client_user_id"]) for item in payload["items"]]
    assert ids == sorted(ids)
    assert payload["count"] == 2
    assert all(item["has_data"] is True for item in payload["items"])
    assert all("freshness" in item for item in payload["items"])


def test_pt_comparison_explicit_unlinked_client_ids_forbidden(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    linked_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")
    unlinked_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=linked_headers,
        status=PtClientLinkStatus.ACTIVE,
    )

    linked_id = _current_user_id(pt_metrics_api_client, linked_headers)
    unlinked_id = _current_user_id(pt_metrics_api_client, unlinked_headers)

    response = pt_metrics_api_client.get(
        "/pt/metrics/comparison",
        params=[("client_ids", str(linked_id)), ("client_ids", str(unlinked_id))],
        headers=pt_headers,
    )
    assert response.status_code == 403


def test_pt_comparison_empty_linked_set_is_deterministic(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")

    response = pt_metrics_api_client.get(
        "/pt/metrics/comparison",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["items"] == []


def test_pt_comparison_malformed_week_start_date_returns_422(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")

    response = pt_metrics_api_client.get(
        "/pt/metrics/comparison",
        params={"week_start_date": "2026/03/16"},
        headers=pt_headers,
    )
    assert response.status_code == 422


def test_pt_comparison_conflicting_date_filters_returns_422(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")

    response = pt_metrics_api_client.get(
        "/pt/metrics/comparison",
        params={"week_start_date": "2026-03-16", "as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert response.status_code == 422


def test_pt_comparison_duplicate_client_ids_are_deduplicated_deterministically(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(pt_metrics_api_client, bff_headers, "pt")
    client_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")

    _seed_pt_client_link(
        pt_metrics_api_client,
        pt_headers=pt_headers,
        client_headers=client_headers,
        status=PtClientLinkStatus.ACTIVE,
    )
    _seed_client_week_records(
        pt_metrics_api_client,
        client_headers=client_headers,
        calories=1500,
        expenditure=900,
    )

    client_id = _current_user_id(pt_metrics_api_client, client_headers)
    response = pt_metrics_api_client.get(
        "/pt/metrics/comparison",
        params=[("client_ids", str(client_id)), ("client_ids", str(client_id))],
        headers=pt_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert [item["client_user_id"] for item in payload["items"]] == [str(client_id)]


def test_client_metrics_route_regression_still_works(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(pt_metrics_api_client, bff_headers, "client")
    _seed_client_week_records(
        pt_metrics_api_client,
        client_headers=client_headers,
        calories=1800,
        expenditure=1300,
    )

    response = pt_metrics_api_client.get(
        "/metrics/overview",
        params={"as_of_date": "2026-03-18"},
        headers=client_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_intake_calories"] == 1800


def test_prometheus_metrics_route_unchanged(
    pt_metrics_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    admin_headers = _register_headers(pt_metrics_api_client, bff_headers, "admin")

    response = pt_metrics_api_client.get("/metrics", headers=admin_headers)
    assert response.status_code == 200
    assert "mealmetric_http_requests_total" in response.text
