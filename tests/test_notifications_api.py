from collections.abc import Generator
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.core.app import create_app
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db


def _register_token(client: TestClient, bff_headers: dict[str, str], role: str) -> str:
    email = f"{role}-{uuid4()}@example.com"
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


def _create_memory_client() -> TestClient:
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
    return TestClient(app)


def test_notifications_list_unread_and_mark_read(bff_headers: dict[str, str]) -> None:
    client = _create_memory_client()
    try:
        pt_headers = _headers_for_role(client, bff_headers, "pt")
        client_headers = _headers_for_role(client, bff_headers, "client")
        client_user_id = _current_user_id(client, client_headers)

        link_response = client.post(
            "/pt/clients/links",
            json={"client_user_id": str(client_user_id), "status": "active"},
            headers=pt_headers,
        )
        assert link_response.status_code == 201

        package_response = client.post(
            "/pt/packages",
            json={"title": "Notify Package", "status": "active", "is_template": False},
            headers=pt_headers,
        )
        assert package_response.status_code == 201

        assign_response = client.post(
            f"/pt/clients/{client_user_id}/assignments",
            json={"training_package_id": package_response.json()["id"], "status": "assigned"},
            headers=pt_headers,
        )
        assert assign_response.status_code == 201

        unread_response = client.get("/notifications/unread-count", headers=client_headers)
        assert unread_response.status_code == 200
        assert unread_response.json()["count"] == 1

        list_response = client.get("/notifications", headers=client_headers)
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["count"] == 1
        notification_id = payload["items"][0]["id"]
        assert payload["items"][0]["type"] == "pt_assignment_created"
        assert payload["items"][0]["is_read"] is False

        mark_read = client.patch(
            f"/notifications/{notification_id}/read",
            headers=client_headers,
        )
        assert mark_read.status_code == 200
        assert mark_read.json()["is_read"] is True

        unread_after = client.get("/notifications/unread-count", headers=client_headers)
        assert unread_after.status_code == 200
        assert unread_after.json()["count"] == 0
    finally:
        client.close()


def test_notification_triggers_respect_recipient_scope(bff_headers: dict[str, str]) -> None:
    client = _create_memory_client()
    try:
        pt_headers = _headers_for_role(client, bff_headers, "pt")
        other_pt_headers = _headers_for_role(client, bff_headers, "pt")
        client_headers = _headers_for_role(client, bff_headers, "client")
        client_user_id = _current_user_id(client, client_headers)

        link_response = client.post(
            "/pt/clients/links",
            json={"client_user_id": str(client_user_id), "status": "active"},
            headers=pt_headers,
        )
        assert link_response.status_code == 201

        routine_response = client.post(
            "/pt/routines",
            json={"title": "Notification Routine"},
            headers=pt_headers,
        )
        assert routine_response.status_code == 201

        create_log_response = client.post(
            "/client/training/workout-logs",
            json={"routine_id": routine_response.json()["id"], "completion_status": "completed"},
            headers=client_headers,
        )
        assert create_log_response.status_code == 201
        workout_log_id = create_log_response.json()["id"]

        pt_notifications = client.get("/notifications", headers=pt_headers)
        assert pt_notifications.status_code == 200
        assert pt_notifications.json()["count"] == 1
        assert pt_notifications.json()["items"][0]["type"] == "client_workout_logged"

        other_pt_notifications = client.get("/notifications", headers=other_pt_headers)
        assert other_pt_notifications.status_code == 200
        assert other_pt_notifications.json()["count"] == 0

        note_response = client.patch(
            f"/pt/workout-logs/{workout_log_id}/pt-notes",
            json={"pt_notes": "Keep your chest up on each rep."},
            headers=pt_headers,
        )
        assert note_response.status_code == 200

        client_notifications = client.get("/notifications", headers=client_headers)
        assert client_notifications.status_code == 200
        notification_types = [item["type"] for item in client_notifications.json()["items"]]
        assert notification_types == ["pt_workout_note_added"]
    finally:
        client.close()


def test_notifications_mark_read_hides_cross_user_resource(bff_headers: dict[str, str]) -> None:
    client = _create_memory_client()
    try:
        pt_headers = _headers_for_role(client, bff_headers, "pt")
        client_headers = _headers_for_role(client, bff_headers, "client")
        other_client_headers = _headers_for_role(client, bff_headers, "client")
        client_user_id = _current_user_id(client, client_headers)

        link_response = client.post(
            "/pt/clients/links",
            json={"client_user_id": str(client_user_id), "status": "active"},
            headers=pt_headers,
        )
        assert link_response.status_code == 201

        package_response = client.post(
            "/pt/packages",
            json={"title": "Scoped Notification", "status": "active", "is_template": False},
            headers=pt_headers,
        )
        assert package_response.status_code == 201

        assign_response = client.post(
            f"/pt/clients/{client_user_id}/assignments",
            json={"training_package_id": package_response.json()["id"], "status": "assigned"},
            headers=pt_headers,
        )
        assert assign_response.status_code == 201

        notifications_response = client.get("/notifications", headers=client_headers)
        assert notifications_response.status_code == 200
        notification_id = notifications_response.json()["items"][0]["id"]

        forbidden_response = client.patch(
            f"/notifications/{notification_id}/read",
            headers=other_client_headers,
        )
        assert forbidden_response.status_code == 404
        assert forbidden_response.json() == {"detail": "notification_not_found"}
    finally:
        client.close()
