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
def client_training_api_client(
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


def _seed_assignment_bundle(
    client: TestClient,
    pt_headers: dict[str, str],
    client_user_id: UUID,
) -> dict[str, str]:
    link = client.post(
        "/pt/clients/links",
        json={"client_user_id": str(client_user_id), "status": "active"},
        headers=pt_headers,
    )
    assert link.status_code == 201

    routine = client.post(
        "/pt/routines",
        json={"title": "Client Routine", "estimated_minutes": 40},
        headers=pt_headers,
    )
    assert routine.status_code == 201
    routine_id = str(routine.json()["id"])

    package = client.post(
        "/pt/packages",
        json={"title": "Client Package", "status": "active", "is_template": False},
        headers=pt_headers,
    )
    assert package.status_code == 201
    package_id = str(package.json()["id"])

    composition = client.put(
        f"/pt/packages/{package_id}/routines",
        json={"items": [{"routine_id": routine_id, "position": 1, "day_label": "Day 1"}]},
        headers=pt_headers,
    )
    assert composition.status_code == 200

    checklist = client.put(
        f"/pt/packages/{package_id}/checklist",
        json={"items": [{"label": "Hydrate", "position": 0, "is_required": True}]},
        headers=pt_headers,
    )
    assert checklist.status_code == 200

    assignment = client.post(
        f"/pt/clients/{client_user_id}/assignments",
        json={"training_package_id": package_id, "status": "active"},
        headers=pt_headers,
    )
    assert assignment.status_code == 201

    return {
        "routine_id": routine_id,
        "package_id": package_id,
        "assignment_id": str(assignment.json()["id"]),
    }


def test_client_can_list_own_assignments(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    _seed_assignment_bundle(client_training_api_client, pt_headers, client_user_id)

    response = client_training_api_client.get(
        "/client/training/assignments", headers=client_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["client_user_id"] == str(client_user_id)


def test_client_can_get_own_assignment_detail(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client_user_id)

    response = client_training_api_client.get(
        f"/client/training/assignments/{bundle['assignment_id']}",
        headers=client_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == bundle["assignment_id"]
    assert payload["package"]["id"] == bundle["package_id"]
    assert len(payload["routines"]) == 1
    assert len(payload["checklist_items"]) == 1


def test_client_cannot_read_another_clients_assignment(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client1_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client2_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client1_id = _current_user_id(client_training_api_client, client1_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client1_id)

    response = client_training_api_client.get(
        f"/client/training/assignments/{bundle['assignment_id']}",
        headers=client2_headers,
    )
    assert response.status_code == 404


def test_client_can_list_own_workout_logs(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client_user_id)

    created = client_training_api_client.post(
        "/client/training/workout-logs",
        json={
            "assignment_id": bundle["assignment_id"],
            "routine_id": bundle["routine_id"],
            "duration_minutes": 38,
            "completion_status": "completed",
            "client_notes": "felt good",
        },
        headers=client_headers,
    )
    assert created.status_code == 201

    response = client_training_api_client.get(
        "/client/training/workout-logs", headers=client_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["assignment_id"] == bundle["assignment_id"]


def test_client_can_create_own_workout_log(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client_user_id)

    response = client_training_api_client.post(
        "/client/training/workout-logs",
        json={
            "assignment_id": bundle["assignment_id"],
            "routine_id": bundle["routine_id"],
            "duration_minutes": 42,
            "completion_status": "partial",
            "client_notes": "low energy",
        },
        headers=client_headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["client_user_id"] == str(client_user_id)
    assert payload["completion_status"] == "partial"


def test_client_cannot_create_workout_log_for_another_client(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client1_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client2_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client1_id = _current_user_id(client_training_api_client, client1_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client1_id)

    response = client_training_api_client.post(
        "/client/training/workout-logs",
        json={
            "assignment_id": bundle["assignment_id"],
            "routine_id": bundle["routine_id"],
            "completion_status": "completed",
        },
        headers=client2_headers,
    )
    assert response.status_code == 404


def test_client_cannot_attach_log_to_unowned_assignment(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client1_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client2_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client1_id = _current_user_id(client_training_api_client, client1_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client1_id)

    response = client_training_api_client.post(
        "/client/training/workout-logs",
        json={"assignment_id": bundle["assignment_id"], "completion_status": "completed"},
        headers=client2_headers,
    )
    assert response.status_code == 404


def test_client_cannot_read_another_clients_workout_logs(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client1_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client2_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client1_id = _current_user_id(client_training_api_client, client1_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client1_id)

    created = client_training_api_client.post(
        "/client/training/workout-logs",
        json={"assignment_id": bundle["assignment_id"], "completion_status": "completed"},
        headers=client1_headers,
    )
    assert created.status_code == 201

    response = client_training_api_client.get(
        "/client/training/workout-logs", headers=client2_headers
    )
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_client_training_auth_and_trusted_caller_are_enforced(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    no_auth = client_training_api_client.get("/client/training/assignments", headers=bff_headers)
    assert no_auth.status_code == 401

    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    no_bff = client_training_api_client.get(
        "/client/training/assignments",
        headers={"Authorization": client_headers["Authorization"]},
    )
    assert no_bff.status_code == 401


def test_pt_routes_remain_unaffected_for_client_role(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    response = client_training_api_client.get("/pt/folders", headers=client_headers)
    assert response.status_code == 403


def test_client_can_read_assignment_checklist_endpoint(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client_user_id)

    response = client_training_api_client.get(
        f"/client/training/assignments/{bundle['assignment_id']}/checklist",
        headers=client_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["label"] == "Hydrate"


def test_client_workout_log_rejects_assignment_routine_mismatch(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt1_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    pt2_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    bundle_pt1 = _seed_assignment_bundle(client_training_api_client, pt1_headers, client_user_id)
    bundle_pt2 = _seed_assignment_bundle(client_training_api_client, pt2_headers, client_user_id)

    response = client_training_api_client.post(
        "/client/training/workout-logs",
        json={
            "assignment_id": bundle_pt1["assignment_id"],
            "routine_id": bundle_pt2["routine_id"],
            "completion_status": "completed",
        },
        headers=client_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "assignment_routine_pt_mismatch"


def test_client_workout_log_rejects_unrelated_pt_routine(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt1_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    pt2_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    _seed_assignment_bundle(client_training_api_client, pt1_headers, client_user_id)

    foreign_routine = client_training_api_client.post(
        "/pt/routines",
        json={"title": "Foreign"},
        headers=pt2_headers,
    )
    assert foreign_routine.status_code == 201

    response = client_training_api_client.post(
        "/client/training/workout-logs",
        json={
            "routine_id": foreign_routine.json()["id"],
            "completion_status": "completed",
        },
        headers=client_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "routine_not_assigned_to_client"


def test_client_workout_log_rejects_archived_routine(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)
    bundle = _seed_assignment_bundle(client_training_api_client, pt_headers, client_user_id)

    archived = client_training_api_client.delete(
        f"/pt/routines/{bundle['routine_id']}",
        headers=pt_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    response = client_training_api_client.post(
        "/client/training/workout-logs",
        json={
            "assignment_id": bundle["assignment_id"],
            "routine_id": bundle["routine_id"],
            "completion_status": "completed",
        },
        headers=client_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "routine_archived"


def test_client_assignment_list_order_is_deterministic(
    client_training_api_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    pt1_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    pt2_headers = _register_headers(client_training_api_client, bff_headers, "pt")
    client_headers = _register_headers(client_training_api_client, bff_headers, "client")
    client_user_id = _current_user_id(client_training_api_client, client_headers)

    first = _seed_assignment_bundle(client_training_api_client, pt1_headers, client_user_id)
    second = _seed_assignment_bundle(client_training_api_client, pt2_headers, client_user_id)

    response = client_training_api_client.get(
        "/client/training/assignments", headers=client_headers
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["id"] == second["assignment_id"]
    assert items[1]["id"] == first["assignment_id"]
