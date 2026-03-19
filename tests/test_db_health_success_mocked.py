from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mealmetric.api.deps.auth import get_current_user
from mealmetric.db import session as db_session
from mealmetric.models.user import Role, User


def test_db_health_success_with_mocked_session(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    class _FakeSession:
        def execute(self, _query) -> None:  # type: ignore[no-untyped-def]
            return None

        def close(self) -> None:
            return None

    def _fake_get_db() -> Generator[_FakeSession, None, None]:
        yield _FakeSession()

    def _fake_current_user() -> User:
        return User(email="mocked@example.com", password_hash="hash", role=Role.ADMIN)

    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[db_session.get_db] = _fake_get_db
    app.dependency_overrides[get_current_user] = _fake_current_user
    try:
        response = client.get("/db/health", headers=admin_auth_headers)
        metrics = client.get("/metrics", headers=admin_auth_headers)
    finally:
        app.dependency_overrides.pop(db_session.get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert metrics.status_code == 200
    assert 'route="/db/health"' in metrics.text


def test_db_health_non_admin_forbidden(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/db/health", headers=auth_headers)
    assert response.status_code == 403
