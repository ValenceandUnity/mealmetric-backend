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
from mealmetric.models.training import (
    AssignmentStatus,
    PtClientInvitationStatus,
    PtClientLinkStatus,
    TrainingPackageStatus,
)
from mealmetric.services.training_service import PtProfileService


@pytest.fixture
def training_api_client() -> Generator[TestClient, None, None]:
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

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.state.testing_session_local = testing_session_local
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


def _register_token(client: TestClient, bff_headers: dict[str, str], role: str) -> str:
    email = f"{role}-{uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": role},
        headers=bff_headers,
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _register_token_for_email(
    client: TestClient,
    bff_headers: dict[str, str],
    *,
    email: str,
    role: str,
) -> str:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": role},
        headers=bff_headers,
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _headers_for_role(client: TestClient, bff_headers: dict[str, str], role: str) -> dict[str, str]:
    token = _register_token(client, bff_headers, role)
    return {"Authorization": f"Bearer {token}", **bff_headers}


def _current_user_id(client: TestClient, headers: dict[str, str]) -> UUID:
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    return UUID(str(response.json()["id"]))


def _seed_pt_profile(client: TestClient, user_id: UUID, display_name: str = "Coach") -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    session_factory = cast(sessionmaker[Session], app.state.testing_session_local)
    with session_factory() as db:
        service = PtProfileService(db)
        service.create_profile(user_id=user_id, display_name=display_name)
        db.commit()


def test_pt_profile_read_update(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt_user_id = _current_user_id(training_api_client, pt_headers)
    _seed_pt_profile(training_api_client, pt_user_id)

    get_response = training_api_client.get("/pt/profile/me", headers=pt_headers)
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == "Coach"

    update_response = training_api_client.put(
        "/pt/profile/me",
        json={
            "display_name": "Coach Updated",
            "bio": "Strength",
            "certifications_text": "NASM",
            "specialties_text": "hypertrophy",
            "is_active": True,
        },
        headers=pt_headers,
    )
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["display_name"] == "Coach Updated"
    assert body["bio"] == "Strength"


def test_pt_client_links_create_list_update(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client_user_id = _current_user_id(training_api_client, client_headers)

    create_response = training_api_client.post(
        "/pt/clients/links",
        json={
            "client_user_id": str(client_user_id),
            "status": "pending",
            "notes": "new",
        },
        headers=pt_headers,
    )
    assert create_response.status_code == 201
    link_id = create_response.json()["id"]

    list_response = training_api_client.get("/pt/clients/links", headers=pt_headers)
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    alias_list_response = training_api_client.get("/pt/clients", headers=pt_headers)
    assert alias_list_response.status_code == 200
    assert alias_list_response.json()["count"] == 1

    patch_response = training_api_client.patch(
        f"/pt/clients/links/{link_id}",
        json={"status": "active"},
        headers=pt_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "active"


def test_pt_roster_categories_list_create_assign_and_filter_clients(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client1_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client2_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client1_id = _current_user_id(training_api_client, client1_headers)
    client2_id = _current_user_id(training_api_client, client2_headers)

    link1_response = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client1_id), "status": "active"},
        headers=pt1_headers,
    )
    assert link1_response.status_code == 201

    link2_response = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client2_id), "status": "active"},
        headers=pt1_headers,
    )
    assert link2_response.status_code == 201

    create_category_response = training_api_client.post(
        "/pt/roster-categories",
        json={"name": "Strength Focus"},
        headers=pt1_headers,
    )
    assert create_category_response.status_code == 201
    category_id = create_category_response.json()["id"]

    list_categories_response = training_api_client.get(
        "/pt/roster-categories",
        headers=pt1_headers,
    )
    assert list_categories_response.status_code == 200
    assert list_categories_response.json()["count"] == 1
    assert list_categories_response.json()["items"][0]["name"] == "Strength Focus"

    assign_category_response = training_api_client.patch(
        f"/pt/clients/{client1_id}/roster-category",
        json={"roster_category_id": category_id},
        headers=pt1_headers,
    )
    assert assign_category_response.status_code == 200
    assert assign_category_response.json()["client_user_id"] == str(client1_id)
    assert assign_category_response.json()["client_name"] == assign_category_response.json()["client_email"]
    assert assign_category_response.json()["roster_name"] == "Strength Focus"

    all_clients_response = training_api_client.get("/pt/clients", headers=pt1_headers)
    assert all_clients_response.status_code == 200
    assert all_clients_response.json()["count"] == 2
    assert all(
        "client_name" in item and "client_email" in item and "roster_name" in item
        for item in all_clients_response.json()["items"]
    )
    assert any(
        item["client_user_id"] == str(client1_id) and item["roster_name"] == "Strength Focus"
        for item in all_clients_response.json()["items"]
    )
    assert any(
        item["client_user_id"] == str(client2_id) and item["roster_name"] is None
        for item in all_clients_response.json()["items"]
    )

    filtered_clients_response = training_api_client.get(
        "/pt/clients",
        params={"category_id": category_id},
        headers=pt1_headers,
    )
    assert filtered_clients_response.status_code == 200
    assert filtered_clients_response.json()["count"] == 1
    assert filtered_clients_response.json()["items"][0]["client_user_id"] == str(client1_id)
    assert filtered_clients_response.json()["items"][0]["roster_name"] == "Strength Focus"

    cross_pt_category_list = training_api_client.get(
        "/pt/clients",
        params={"category_id": category_id},
        headers=pt2_headers,
    )
    assert cross_pt_category_list.status_code == 404
    assert cross_pt_category_list.json() == {"detail": "pt_roster_category_not_found"}


def test_pt_client_invitation_send_list_and_accept_flow(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_email = "roshi@example.com"
    client_email = "goku@example.com"
    pt_token = _register_token_for_email(
        training_api_client,
        bff_headers,
        email=pt_email,
        role="pt",
    )
    client_token = _register_token_for_email(
        training_api_client,
        bff_headers,
        email=client_email,
        role="client",
    )
    pt_headers = {"Authorization": f"Bearer {pt_token}", **bff_headers}
    client_headers = {"Authorization": f"Bearer {client_token}", **bff_headers}
    client_user_id = _current_user_id(training_api_client, client_headers)

    invite_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": client_email},
        headers=pt_headers,
    )
    assert invite_response.status_code == 201
    invite_payload = invite_response.json()
    invitation_id = invite_payload["id"]
    assert invite_payload["status"] == PtClientInvitationStatus.PENDING.value
    assert invite_payload["client_email"] == client_email
    assert invite_payload["pt_email"] == pt_email

    duplicate_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": client_email},
        headers=pt_headers,
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"detail": "pt_client_invitation_pending"}

    pt_list_response = training_api_client.get("/pt/client-invitations", headers=pt_headers)
    assert pt_list_response.status_code == 200
    assert pt_list_response.json()["count"] == 1

    client_list_response = training_api_client.get("/client/invitations", headers=client_headers)
    assert client_list_response.status_code == 200
    assert client_list_response.json()["count"] == 1
    assert client_list_response.json()["items"][0]["id"] == invitation_id

    roster_before_acceptance = training_api_client.get("/pt/clients", headers=pt_headers)
    assert roster_before_acceptance.status_code == 200
    assert roster_before_acceptance.json()["count"] == 0

    accept_response = training_api_client.post(
        f"/client/invitations/{invitation_id}/accept",
        headers=client_headers,
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["status"] == PtClientInvitationStatus.ACCEPTED.value

    roster_after_acceptance = training_api_client.get("/pt/clients", headers=pt_headers)
    assert roster_after_acceptance.status_code == 200
    assert roster_after_acceptance.json()["count"] == 1
    assert roster_after_acceptance.json()["items"][0]["client_user_id"] == str(client_user_id)


def test_pt_client_invitation_rejects_missing_email_non_client_and_self(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_email = "masterroshi@example.com"
    pt_token = _register_token_for_email(
        training_api_client,
        bff_headers,
        email=pt_email,
        role="pt",
    )
    other_pt_token = _register_token_for_email(
        training_api_client,
        bff_headers,
        email="krillin-coach@example.com",
        role="pt",
    )
    _ = other_pt_token
    _register_token_for_email(
        training_api_client,
        bff_headers,
        email="bulma@example.com",
        role="client",
    )
    pt_headers = {"Authorization": f"Bearer {pt_token}", **bff_headers}

    missing_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": "missing@example.com"},
        headers=pt_headers,
    )
    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "client_user_not_found"}

    non_client_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": "krillin-coach@example.com"},
        headers=pt_headers,
    )
    assert non_client_response.status_code == 422
    assert non_client_response.json() == {"detail": "client_role_required"}

    self_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": pt_email},
        headers=pt_headers,
    )
    assert self_response.status_code == 422
    assert self_response.json() == {"detail": "pt_client_invitation_self_forbidden"}


def test_client_invitation_decline_and_scope_protection(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    other_client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_email = training_api_client.get("/auth/me", headers=client_headers).json()["email"]

    invite_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": client_email},
        headers=pt_headers,
    )
    assert invite_response.status_code == 201
    invitation_id = invite_response.json()["id"]

    other_client_response = training_api_client.post(
        f"/client/invitations/{invitation_id}/accept",
        headers=other_client_headers,
    )
    assert other_client_response.status_code == 404
    assert other_client_response.json() == {"detail": "pt_client_invitation_not_found"}

    decline_response = training_api_client.post(
        f"/client/invitations/{invitation_id}/decline",
        headers=client_headers,
    )
    assert decline_response.status_code == 200
    assert decline_response.json()["status"] == PtClientInvitationStatus.DECLINED.value

    roster_response = training_api_client.get("/pt/clients", headers=pt_headers)
    assert roster_response.status_code == 200
    assert roster_response.json()["count"] == 0

def test_pt_client_detail_returns_profile_assignments_and_metrics(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client_user_id = _current_user_id(training_api_client, client_headers)

    create_link_response = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    assert create_link_response.status_code == 201

    package_response = training_api_client.post(
        "/pt/packages",
        json={
            "title": "Client Detail Package",
            "status": "active",
            "is_template": False,
        },
        headers=pt_headers,
    )
    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    assignment_response = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package_id, "status": "assigned"},
        headers=pt_headers,
    )
    assert assignment_response.status_code == 201

    detail_response = training_api_client.get(
        f"/pt/clients/{client_user_id}",
        params={"as_of_date": "2026-03-18"},
        headers=pt_headers,
    )
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["client"]["id"] == str(client_user_id)
    assert payload["client"]["role"] == "client"
    assert payload["assignments_count"] == 1
    assert payload["current_assignments"][0]["training_package_id"] == package_id
    assert payload["metrics_snapshot"]["client_user_id"] == str(client_user_id)


def test_pt_client_detail_requires_active_link(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    response = training_api_client.get(f"/pt/clients/{client_user_id}", headers=pt_headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "pt_client_link_not_active"}


def test_pt_dashboard_returns_real_client_summaries(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )

    package_response = training_api_client.post(
        "/pt/packages",
        json={
            "title": "Dashboard Package",
            "status": "active",
            "is_template": False,
        },
        headers=pt_headers,
    )
    assert package_response.status_code == 201

    training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={
            "training_package_id": package_response.json()["id"],
            "status": "assigned",
        },
        headers=pt_headers,
    )

    routine_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Dashboard Routine"},
        headers=pt_headers,
    )
    assert routine_response.status_code == 201

    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={
            "routine_id": routine_response.json()["id"],
            "performed_at": "2026-03-19T13:30:00Z",
            "completion_status": "completed",
        },
        headers=client_headers,
    )
    assert create_log_response.status_code == 201

    response = training_api_client.get("/pt/dashboard", headers=pt_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["client"]["id"] == str(client_user_id)
    assert item["client"]["email"].endswith("@example.com")
    assert item["status"] == "active"
    assert item["assignment_count"] == 1
    assert item["workout_log_count"] == 1
    assert item["latest_workout_log_at"].startswith("2026-03-19T13:30:00")
    assert item["metrics_snapshot"]["client_user_id"] == str(client_user_id)


def test_pt_can_list_client_workout_logs_with_structured_entries(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client_user_id = _current_user_id(training_api_client, client_headers)

    link_response = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    assert link_response.status_code == 201

    routine_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Lower Body A", "estimated_minutes": 55},
        headers=pt_headers,
    )
    assert routine_response.status_code == 201
    routine_id = routine_response.json()["id"]

    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={
            "routine_id": routine_id,
            "performed_at": "2026-03-18T13:30:00Z",
            "duration_minutes": 54,
            "completion_status": "completed",
            "client_notes": "Felt strong.",
            "exercise_entries": [
                {
                    "position": 0,
                    "exercise_name": "Back Squat",
                    "sets": 4,
                    "reps": 6,
                    "weight": "225.00",
                },
                {
                    "position": 1,
                    "exercise_name": "Walking Lunge",
                    "duration_seconds": 120,
                    "notes": "Per leg finisher",
                },
            ],
        },
        headers=client_headers,
    )
    assert create_log_response.status_code == 201

    response = training_api_client.get(
        f"/pt/clients/{client_user_id}/workout-logs",
        headers=pt_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["routine_id"] == routine_id
    assert payload["items"][0]["routine_title"] == "Lower Body A"
    assert payload["items"][0]["duration_minutes"] == 54
    assert payload["items"][0]["exercise_entries"][0]["position"] == 0
    assert payload["items"][0]["exercise_entries"][0]["exercise_name"] == "Back Squat"
    assert payload["items"][0]["exercise_entries"][1]["position"] == 1
    assert payload["items"][0]["exercise_entries"][1]["notes"] == "Per leg finisher"


def test_pt_can_view_client_standalone_logs_after_invitation_acceptance(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client_user_id = _current_user_id(training_api_client, client_headers)
    client_email = training_api_client.get("/auth/me", headers=client_headers).json()["email"]

    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={
            "mode": "general_workout",
            "performed_at": "2026-03-18T13:30:00Z",
            "completion_status": "completed",
            "exercise_entries": [
                {
                    "position": 0,
                    "exercise_name": "Invite Flow Standalone Workout",
                    "sets": 3,
                    "reps": 10,
                    "weight": "135.00",
                }
            ],
        },
        headers=client_headers,
    )
    assert create_log_response.status_code == 201

    invite_response = training_api_client.post(
        "/pt/client-invitations",
        json={"client_email": client_email},
        headers=pt_headers,
    )
    assert invite_response.status_code == 201
    invitation_id = invite_response.json()["id"]

    accept_response = training_api_client.post(
        f"/client/invitations/{invitation_id}/accept",
        headers=client_headers,
    )
    assert accept_response.status_code == 200

    response = training_api_client.get(
        f"/pt/clients/{client_user_id}/workout-logs",
        headers=pt_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["pt_user_id"] is None
    assert payload["items"][0]["mode"] == "general_workout"
    assert payload["items"][0]["exercise_entries"][0]["exercise_name"] == (
        "Invite Flow Standalone Workout"
    )


def test_pt_client_workout_logs_require_legitimate_scope(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    link_response = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt1_headers,
    )
    assert link_response.status_code == 201

    response = training_api_client.get(
        f"/pt/clients/{client_user_id}/workout-logs",
        headers=pt2_headers,
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "workout_logs_not_in_scope"}

    pending_client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    pending_client_user_id = _current_user_id(training_api_client, pending_client_headers)
    pending_link_response = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(pending_client_user_id), "status": "pending"},
        headers=pt1_headers,
    )
    assert pending_link_response.status_code == 201

    pending_scope_response = training_api_client.get(
        f"/pt/clients/{pending_client_user_id}/workout-logs",
        headers=pt1_headers,
    )
    assert pending_scope_response.status_code == 403
    assert pending_scope_response.json() == {"detail": "workout_logs_not_in_scope"}


def test_pt_can_update_workout_log_notes_for_valid_client(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    routine_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Upper A"},
        headers=pt_headers,
    )
    routine_id = routine_response.json()["id"]
    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={"routine_id": routine_id, "completion_status": "completed"},
        headers=client_headers,
    )
    assert create_log_response.status_code == 201
    workout_log_id = create_log_response.json()["id"]

    response = training_api_client.patch(
        f"/pt/workout-logs/{workout_log_id}/pt-notes",
        json={"pt_notes": "  Keep knees out on the main sets.  "},
        headers=pt_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == workout_log_id
    assert payload["pt_notes"] == "Keep knees out on the main sets."
    assert payload["exercise_entries"] == []


def test_pt_cannot_update_workout_log_notes_outside_scope(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt1_headers,
    )
    routine_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Lower B"},
        headers=pt1_headers,
    )
    routine_id = routine_response.json()["id"]
    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={"routine_id": routine_id, "completion_status": "completed"},
        headers=client_headers,
    )
    workout_log_id = create_log_response.json()["id"]

    response = training_api_client.patch(
        f"/pt/workout-logs/{workout_log_id}/pt-notes",
        json={"pt_notes": "Not allowed"},
        headers=pt2_headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "workout_log_not_found"}


def test_pt_can_clear_workout_log_notes(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    routine_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Conditioning"},
        headers=pt_headers,
    )
    routine_id = routine_response.json()["id"]
    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={"routine_id": routine_id, "completion_status": "completed"},
        headers=client_headers,
    )
    workout_log_id = create_log_response.json()["id"]

    set_response = training_api_client.patch(
        f"/pt/workout-logs/{workout_log_id}/pt-notes",
        json={"pt_notes": "Push the pace next week."},
        headers=pt_headers,
    )
    assert set_response.status_code == 200
    assert set_response.json()["pt_notes"] == "Push the pace next week."

    clear_response = training_api_client.patch(
        f"/pt/workout-logs/{workout_log_id}/pt-notes",
        json={"pt_notes": "   "},
        headers=pt_headers,
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["pt_notes"] is None


def test_non_pt_access_to_workout_log_note_update_is_rejected(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    routine_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Tempo Run"},
        headers=pt_headers,
    )
    routine_id = routine_response.json()["id"]
    create_log_response = training_api_client.post(
        "/client/training/workout-logs",
        json={"routine_id": routine_id, "completion_status": "completed"},
        headers=client_headers,
    )
    workout_log_id = create_log_response.json()["id"]

    response = training_api_client.patch(
        f"/pt/workout-logs/{workout_log_id}/pt-notes",
        json={"pt_notes": "Client should not reach this route."},
        headers=client_headers,
    )
    assert response.status_code == 403


def test_pt_client_link_status_update_hides_cross_pt_resource(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    link = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "pending"},
        headers=pt1_headers,
    )
    assert link.status_code == 201

    response = training_api_client.patch(
        f"/pt/clients/links/{link.json()['id']}",
        json={"status": "active"},
        headers=pt2_headers,
    )
    assert response.status_code == 404


def test_pt_folder_crud_and_scope(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    create_response = training_api_client.post(
        "/pt/folders",
        json={"name": "Folder A", "description": "desc", "sort_order": 1},
        headers=pt1_headers,
    )
    assert create_response.status_code == 201
    folder_id = create_response.json()["id"]

    list_response = training_api_client.get("/pt/folders", headers=pt1_headers)
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    update_response = training_api_client.patch(
        f"/pt/folders/{folder_id}",
        json={"name": "Folder B", "description": None, "sort_order": 2},
        headers=pt1_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Folder B"

    forbidden_response = training_api_client.patch(
        f"/pt/folders/{folder_id}",
        json={"name": "Nope", "description": None, "sort_order": 0},
        headers=pt2_headers,
    )
    assert forbidden_response.status_code == 404

    delete_response = training_api_client.delete(f"/pt/folders/{folder_id}", headers=pt1_headers)
    assert delete_response.status_code == 204


def test_pt_routine_crud_archive_and_scope(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    create_response = training_api_client.post(
        "/pt/routines",
        json={"title": "Push Day", "description": "upper", "estimated_minutes": 45},
        headers=pt1_headers,
    )
    assert create_response.status_code == 201
    routine_id = create_response.json()["id"]

    list_response = training_api_client.get("/pt/routines", headers=pt1_headers)
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    detail_response = training_api_client.get(f"/pt/routines/{routine_id}", headers=pt1_headers)
    assert detail_response.status_code == 200

    update_response = training_api_client.patch(
        f"/pt/routines/{routine_id}",
        json={
            "title": "Push Day V2",
            "folder_id": None,
            "description": "upper body",
            "difficulty": "medium",
            "estimated_minutes": 50,
        },
        headers=pt1_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Push Day V2"

    other_pt_response = training_api_client.get(f"/pt/routines/{routine_id}", headers=pt2_headers)
    assert other_pt_response.status_code == 404

    archive_response = training_api_client.delete(f"/pt/routines/{routine_id}", headers=pt1_headers)
    assert archive_response.status_code == 200
    assert archive_response.json()["is_archived"] is True


def test_pt_package_crud_archive_and_scope(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    create_response = training_api_client.post(
        "/pt/packages",
        json={"title": "Beginner Pack", "status": "draft", "is_template": True},
        headers=pt1_headers,
    )
    assert create_response.status_code == 201
    package_id = create_response.json()["id"]

    list_response = training_api_client.get("/pt/packages", headers=pt1_headers)
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    detail_response = training_api_client.get(f"/pt/packages/{package_id}", headers=pt1_headers)
    assert detail_response.status_code == 200

    update_response = training_api_client.patch(
        f"/pt/packages/{package_id}",
        json={
            "title": "Beginner Pack V2",
            "folder_id": None,
            "description": "updated",
            "status": "active",
            "duration_days": 30,
            "is_template": False,
        },
        headers=pt1_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "active"

    other_pt_response = training_api_client.get(f"/pt/packages/{package_id}", headers=pt2_headers)
    assert other_pt_response.status_code == 404

    archive_response = training_api_client.delete(f"/pt/packages/{package_id}", headers=pt1_headers)
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"


def test_package_composition_replace_and_cross_pt_reject(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    r1 = training_api_client.post(
        "/pt/routines",
        json={"title": "R1"},
        headers=pt1_headers,
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    r2 = training_api_client.post(
        "/pt/routines",
        json={"title": "R2"},
        headers=pt1_headers,
    )
    assert r2.status_code == 201
    r2_id = r2.json()["id"]

    r3 = training_api_client.post(
        "/pt/routines",
        json={"title": "R3"},
        headers=pt2_headers,
    )
    assert r3.status_code == 201
    r3_id = r3.json()["id"]

    package = training_api_client.post(
        "/pt/packages",
        json={"title": "Pack", "status": "draft", "is_template": True},
        headers=pt1_headers,
    )
    assert package.status_code == 201
    package_id = package.json()["id"]

    replace_ok = training_api_client.put(
        f"/pt/packages/{package_id}/routines",
        json={
            "items": [
                {"routine_id": r2_id, "position": 2, "day_label": "Day 2"},
                {"routine_id": r1_id, "position": 1, "day_label": "Day 1"},
            ]
        },
        headers=pt1_headers,
    )
    assert replace_ok.status_code == 200
    assert [item["position"] for item in replace_ok.json()["items"]] == [1, 2]

    list_response = training_api_client.get(
        f"/pt/packages/{package_id}/routines", headers=pt1_headers
    )
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 2

    replace_bad = training_api_client.put(
        f"/pt/packages/{package_id}/routines",
        json={
            "items": [
                {"routine_id": r1_id, "position": 1},
                {"routine_id": r3_id, "position": 2},
            ]
        },
        headers=pt1_headers,
    )
    assert replace_bad.status_code == 403


def test_checklist_package_and_routine_replace(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    routine = training_api_client.post(
        "/pt/routines", json={"title": "Routine"}, headers=pt_headers
    )
    assert routine.status_code == 201
    routine_id = routine.json()["id"]

    package = training_api_client.post(
        "/pt/packages",
        json={"title": "Pack", "status": "draft", "is_template": True},
        headers=pt_headers,
    )
    assert package.status_code == 201
    package_id = package.json()["id"]

    package_put = training_api_client.put(
        f"/pt/packages/{package_id}/checklist",
        json={
            "items": [
                {"label": "B", "position": 2, "is_required": False},
                {"label": "A", "position": 1, "is_required": True},
            ]
        },
        headers=pt_headers,
    )
    assert package_put.status_code == 200
    assert [item["position"] for item in package_put.json()["items"]] == [1, 2]

    package_get = training_api_client.get(
        f"/pt/packages/{package_id}/checklist", headers=pt_headers
    )
    assert package_get.status_code == 200
    assert package_get.json()["count"] == 2

    routine_put = training_api_client.put(
        f"/pt/routines/{routine_id}/checklist",
        json={"items": [{"label": "Warmup", "position": 0, "is_required": True}]},
        headers=pt_headers,
    )
    assert routine_put.status_code == 200
    assert routine_put.json()["count"] == 1

    routine_get = training_api_client.get(
        f"/pt/routines/{routine_id}/checklist", headers=pt_headers
    )
    assert routine_get.status_code == 200
    assert routine_get.json()["items"][0]["label"] == "Warmup"


def test_assignments_linked_client_success_and_status_update(
    training_api_client: TestClient, bff_headers: dict[str, str]
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client_user_id = _current_user_id(training_api_client, client_headers)

    package = training_api_client.post(
        "/pt/packages",
        json={
            "title": "Pack",
            "status": TrainingPackageStatus.DRAFT.value,
            "is_template": True,
        },
        headers=pt_headers,
    )
    assert package.status_code == 201
    package_id = package.json()["id"]

    link = training_api_client.post(
        "/pt/clients/links",
        json={
            "client_user_id": str(client_user_id),
            "status": PtClientLinkStatus.ACTIVE.value,
        },
        headers=pt_headers,
    )
    assert link.status_code == 201

    assign = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={
            "training_package_id": package_id,
            "status": AssignmentStatus.ASSIGNED.value,
            "start_date": "2026-03-17",
            "end_date": "2026-04-16",
        },
        headers=pt_headers,
    )
    assert assign.status_code == 201
    assignment_id = assign.json()["id"]

    list_response = training_api_client.get(
        f"/pt/clients/{client_user_id}/assignments",
        headers=pt_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    patch_response = training_api_client.patch(
        f"/pt/assignments/{assignment_id}",
        json={"status": AssignmentStatus.COMPLETED.value},
        headers=pt_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "completed"


def test_assignments_reject_unlinked_and_other_pt_package(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")

    client_user_id = _current_user_id(training_api_client, client_headers)

    package_pt1 = training_api_client.post(
        "/pt/packages",
        json={"title": "P1", "status": "draft", "is_template": True},
        headers=pt1_headers,
    )
    assert package_pt1.status_code == 201

    package_pt2 = training_api_client.post(
        "/pt/packages",
        json={"title": "P2", "status": "draft", "is_template": True},
        headers=pt2_headers,
    )
    assert package_pt2.status_code == 201

    unlinked_attempt = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package_pt1.json()["id"], "status": "assigned"},
        headers=pt1_headers,
    )
    assert unlinked_attempt.status_code == 422

    link = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt1_headers,
    )
    assert link.status_code == 201

    foreign_package_attempt = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package_pt2.json()["id"], "status": "assigned"},
        headers=pt1_headers,
    )
    assert foreign_package_attempt.status_code == 404


def test_pt_routes_preserve_auth_behavior(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    no_auth = training_api_client.get("/pt/folders", headers=bff_headers)
    assert no_auth.status_code == 401

    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_forbidden = training_api_client.get("/pt/folders", headers=client_headers)
    assert client_forbidden.status_code == 403

    no_bff = training_api_client.get("/pt/folders")
    assert no_bff.status_code == 401


def test_pt_roster_category_routes_preserve_auth_behavior(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    no_auth = training_api_client.get("/pt/roster-categories", headers=bff_headers)
    assert no_auth.status_code == 401

    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_forbidden = training_api_client.get("/pt/roster-categories", headers=client_headers)
    assert client_forbidden.status_code == 403


def test_pt_profile_not_found_until_created(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    get_response = training_api_client.get("/pt/profile/me", headers=pt_headers)
    assert get_response.status_code == 404

    put_response = training_api_client.put(
        "/pt/profile/me",
        json={
            "display_name": "x",
            "bio": None,
            "certifications_text": None,
            "specialties_text": None,
            "is_active": True,
        },
        headers=pt_headers,
    )
    assert put_response.status_code == 404


def test_assignment_update_not_owned_returns_not_found(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt1_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt2_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    package = training_api_client.post(
        "/pt/packages",
        json={"title": "Pack", "status": "draft", "is_template": True},
        headers=pt1_headers,
    )
    assert package.status_code == 201

    link = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt1_headers,
    )
    assert link.status_code == 201

    assignment = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package.json()["id"], "status": "assigned"},
        headers=pt1_headers,
    )
    assert assignment.status_code == 201

    patch = training_api_client.patch(
        f"/pt/assignments/{assignment.json()['id']}",
        json={"status": "cancelled"},
        headers=pt2_headers,
    )
    assert patch.status_code == 404


def test_assignment_payload_supports_optional_dates(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    package = training_api_client.post(
        "/pt/packages",
        json={"title": "No Dates", "status": "draft", "is_template": True},
        headers=pt_headers,
    )
    assert package.status_code == 201

    link = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    assert link.status_code == 201

    assign = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package.json()["id"], "status": "active"},
        headers=pt_headers,
    )
    assert assign.status_code == 201
    assert assign.json()["start_date"] is None
    assert assign.json()["end_date"] is None


def test_assignment_list_is_scoped_to_client(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client1_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client2_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client1_id = _current_user_id(training_api_client, client1_headers)
    client2_id = _current_user_id(training_api_client, client2_headers)

    package = training_api_client.post(
        "/pt/packages",
        json={"title": "Scoped", "status": "draft", "is_template": True},
        headers=pt_headers,
    )
    assert package.status_code == 201

    for client_id in (client1_id, client2_id):
        link = training_api_client.post(
            "/pt/clients/links",
            json={"client_user_id": str(client_id), "status": "active"},
            headers=pt_headers,
        )
        assert link.status_code == 201
        assign = training_api_client.post(
            f"/pt/clients/{client_id}/assignments",
            json={"training_package_id": package.json()["id"], "status": "assigned"},
            headers=pt_headers,
        )
        assert assign.status_code == 201

    list_client1 = training_api_client.get(
        f"/pt/clients/{client1_id}/assignments", headers=pt_headers
    )
    assert list_client1.status_code == 200
    assert list_client1.json()["count"] == 1


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"display_name": "Coach", "is_active": None},
        {"title": "", "status": "draft", "is_template": True},
    ],
)
def test_validation_errors_are_returned(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
    invalid_payload: dict[str, object],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    pt_user_id = _current_user_id(training_api_client, pt_headers)

    if "display_name" in invalid_payload:
        _seed_pt_profile(training_api_client, pt_user_id)
        response = training_api_client.put(
            "/pt/profile/me", json=invalid_payload, headers=pt_headers
        )
    else:
        response = training_api_client.post(
            "/pt/packages", json=invalid_payload, headers=pt_headers
        )

    assert response.status_code == 422


def test_package_composition_duplicate_positions_rejected(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")

    r1 = training_api_client.post("/pt/routines", json={"title": "R1"}, headers=pt_headers)
    assert r1.status_code == 201
    r2 = training_api_client.post("/pt/routines", json={"title": "R2"}, headers=pt_headers)
    assert r2.status_code == 201
    package = training_api_client.post(
        "/pt/packages",
        json={"title": "Pack", "status": "draft", "is_template": True},
        headers=pt_headers,
    )
    assert package.status_code == 201

    replace = training_api_client.put(
        f"/pt/packages/{package.json()['id']}/routines",
        json={
            "items": [
                {"routine_id": r1.json()["id"], "position": 1},
                {"routine_id": r2.json()["id"], "position": 1},
            ]
        },
        headers=pt_headers,
    )
    assert replace.status_code == 422


def test_assignment_created_at_is_server_generated(
    training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _headers_for_role(training_api_client, bff_headers, "pt")
    client_headers = _headers_for_role(training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(training_api_client, client_headers)

    package = training_api_client.post(
        "/pt/packages",
        json={"title": "Pack", "status": "draft", "is_template": True},
        headers=pt_headers,
    )
    assert package.status_code == 201

    link = training_api_client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    assert link.status_code == 201

    before = datetime.now(UTC)
    assign = training_api_client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package.json()["id"], "status": "assigned"},
        headers=pt_headers,
    )
    assert assign.status_code == 201
    assigned_at = datetime.fromisoformat(assign.json()["assigned_at"].replace("Z", "+00:00"))
    assert assigned_at >= before
