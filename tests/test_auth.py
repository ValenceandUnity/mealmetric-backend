import json
from collections.abc import Callable, Generator
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mealmetric.api.deps.auth import require_roles
from mealmetric.api.routes import auth as auth_routes
from mealmetric.core.app import create_app
from mealmetric.core.security import token_denylist
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db
from mealmetric.models.auth_failure_tracker import AuthFailureTracker
from mealmetric.models.role import Role as NormalizedRole
from mealmetric.models.user import Role, User
from mealmetric.models.user_role import UserRole
from mealmetric.services.jwt_service import JWTError


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    app = create_app()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _register(
    client: TestClient, email: str, password: str, bff_headers: dict[str, str], role: str = "client"
) -> str:
    payload = {"email": email, "password": password, "role": role}
    content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = client.post(
        "/auth/register",
        content=content,
        headers={**bff_headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 201
    payload = response.json()
    return str(payload["access_token"])


def test_register_then_me(auth_client: TestClient, signed_bff_headers) -> None:  # type: ignore[no-untyped-def]
    register_payload = {"email": "client@example.com", "password": "securepass1", "role": "client"}
    register_headers = signed_bff_headers(
        method="POST",
        path_with_query="/auth/register",
        body=json.dumps(register_payload, separators=(",", ":")).encode("utf-8"),
    )
    token = _register(auth_client, "client@example.com", "securepass1", register_headers)
    response = auth_client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            **signed_bff_headers(method="GET", path_with_query="/auth/me"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "client@example.com"
    assert body["role"] == "client"


def test_register_creates_normalized_role_membership(
    auth_client: TestClient, bff_headers: dict[str, str]
) -> None:
    email = "normalized-role@example.com"
    _register(auth_client, email, "securepass1", bff_headers, role="pt")

    app = auth_client.app
    assert isinstance(app, FastAPI)
    with app.state.testing_session_local() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        role = session.scalar(select(NormalizedRole).where(NormalizedRole.name == "pt"))
        assert role is not None
        membership = session.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        )
        assert membership is not None


def test_invalid_login_returns_401(auth_client: TestClient, bff_headers: dict[str, str]) -> None:
    _register(auth_client, "login@example.com", "securepass1", bff_headers)
    response = auth_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "wrongpass1"},
        headers=bff_headers,
    )
    assert response.status_code == 401


def test_duplicate_email_returns_409(auth_client: TestClient, bff_headers: dict[str, str]) -> None:
    _register(auth_client, "duplicate@example.com", "securepass1", bff_headers)
    response = auth_client.post(
        "/auth/register",
        json={"email": "duplicate@example.com", "password": "securepass1"},
        headers=bff_headers,
    )
    assert response.status_code == 409


def test_register_returns_503_and_rolls_back_when_token_creation_fails(
    auth_client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = auth_client.app
    assert isinstance(app, FastAPI)

    def _raise_jwt_error(**_kwargs):  # type: ignore[no-untyped-def]
        raise JWTError("token signing unavailable")

    monkeypatch.setattr(auth_routes, "create_access_token", _raise_jwt_error)

    response = auth_client.post(
        "/auth/register",
        json={"email": "jwt-fail@example.com", "password": "securepass1", "role": "client"},
        headers=bff_headers,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "token_service_unavailable"}

    with app.state.testing_session_local() as session:
        user = session.scalar(select(User).where(User.email == "jwt-fail@example.com"))
        assert user is None


def test_register_returns_503_when_users_schema_is_stale(
    bff_headers: dict[str, str],
) -> None:
    get_settings.cache_clear()
    app = create_app()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY NOT NULL,
                    email TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'client',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))

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
        response = client.post(
            "/auth/register",
            json={"email": "stale-schema@example.com", "password": "securepass1", "role": "client"},
            headers=bff_headers,
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "db_schema_mismatch"}


def test_register_returns_503_and_logs_stage_for_unexpected_errors(
    auth_client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _raise_runtime_error(_plain: str) -> str:
        raise RuntimeError("hash backend unavailable")

    monkeypatch.setattr(auth_routes, "hash_password", _raise_runtime_error)
    caplog.set_level("ERROR", logger="mealmetric.auth")

    response = auth_client.post(
        "/auth/register",
        json={"email": "unexpected-error@example.com", "password": "securepass1", "role": "client"},
        headers=bff_headers,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "register_unavailable"}
    assert any(
        record.message == "register failed unexpectedly"
        and getattr(record, "stage", None) == "hash_password"
        for record in caplog.records
    )


def test_me_requires_jwt(auth_client: TestClient, bff_headers: dict[str, str]) -> None:
    response = auth_client.get("/auth/me", headers=bff_headers)
    assert response.status_code == 401


def test_logout_revokes_token(auth_client: TestClient, signed_bff_headers) -> None:  # type: ignore[no-untyped-def]
    register_payload = {"email": "logout@example.com", "password": "securepass1", "role": "client"}
    register_headers = signed_bff_headers(
        method="POST",
        path_with_query="/auth/register",
        body=json.dumps(register_payload, separators=(",", ":")).encode("utf-8"),
    )
    token = _register(auth_client, "logout@example.com", "securepass1", register_headers)
    me_headers = {
        "Authorization": f"Bearer {token}",
        **signed_bff_headers(method="GET", path_with_query="/auth/me"),
    }

    pre_logout = auth_client.get("/auth/me", headers=me_headers)
    assert pre_logout.status_code == 200

    logout_response = auth_client.post(
        "/auth/logout",
        headers={
            "Authorization": f"Bearer {token}",
            **signed_bff_headers(method="POST", path_with_query="/auth/logout"),
        },
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"ok": True}

    token_denylist.clear()
    post_logout = auth_client.get("/auth/me", headers=me_headers)
    assert post_logout.status_code == 401

    app = auth_client.app
    assert isinstance(app, FastAPI)
    with app.state.testing_session_local() as session:
        user = session.scalar(select(User).where(User.email == "logout@example.com"))
        assert user is not None
        assert user.token_version == 1


def test_old_token_rejected_after_relogin_with_versioned_tokens(
    auth_client: TestClient,
    signed_bff_headers: Callable[..., dict[str, str]],
) -> None:
    register_payload = {
        "email": "versioned@example.com",
        "password": "securepass1",
        "role": "client",
    }
    register_headers = signed_bff_headers(
        method="POST",
        path_with_query="/auth/register",
        body=json.dumps(register_payload, separators=(",", ":")).encode("utf-8"),
    )
    original_token = _register(
        auth_client, "versioned@example.com", "securepass1", register_headers
    )
    original_headers = {
        "Authorization": f"Bearer {original_token}",
        **signed_bff_headers(method="GET", path_with_query="/auth/me"),
    }

    logout_response = auth_client.post(
        "/auth/logout",
        headers={
            "Authorization": f"Bearer {original_token}",
            **signed_bff_headers(method="POST", path_with_query="/auth/logout"),
        },
    )
    assert logout_response.status_code == 200

    login_payload = {"email": "versioned@example.com", "password": "securepass1"}
    login_content = json.dumps(login_payload, separators=(",", ":")).encode("utf-8")
    login_response = auth_client.post(
        "/auth/login",
        content=login_content,
        headers={
            **signed_bff_headers(
                method="POST",
                path_with_query="/auth/login",
                body=login_content,
            ),
            "Content-Type": "application/json",
        },
    )
    assert login_response.status_code == 200
    new_token = str(login_response.json()["access_token"])

    assert auth_client.get("/auth/me", headers=original_headers).status_code == 401
    assert (
        auth_client.get(
            "/auth/me",
            headers={
                "Authorization": f"Bearer {new_token}",
                **signed_bff_headers(method="GET", path_with_query="/auth/me"),
            },
        ).status_code
        == 200
    )


def test_auth_failure_alert_triggers_after_threshold(
    auth_client: TestClient,
    bff_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _register(auth_client, "alerts@example.com", "securepass1", bff_headers)
    caplog.set_level("WARNING", logger="mealmetric.auth")

    for _ in range(5):
        response = auth_client.post(
            "/auth/login",
            json={"email": "alerts@example.com", "password": "wrongpass1"},
            headers=bff_headers,
        )
        assert response.status_code == 401

    assert any("auth failure alert triggered" in record.message for record in caplog.records)

    app = auth_client.app
    assert isinstance(app, FastAPI)
    with app.state.testing_session_local() as session:
        tracker = session.get(AuthFailureTracker, "alerts@example.com")
        assert tracker is not None
        assert tracker.failure_count == 5
        assert tracker.alert_emitted_at is not None


def test_successful_login_resets_persisted_failure_tracker(
    auth_client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    _register(auth_client, "reset@example.com", "securepass1", bff_headers)
    for _ in range(2):
        response = auth_client.post(
            "/auth/login",
            json={"email": "reset@example.com", "password": "wrongpass1"},
            headers=bff_headers,
        )
        assert response.status_code == 401

    success_response = auth_client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": "securepass1"},
        headers=bff_headers,
    )
    assert success_response.status_code == 200

    app = auth_client.app
    assert isinstance(app, FastAPI)
    with app.state.testing_session_local() as session:
        tracker = session.get(AuthFailureTracker, "reset@example.com")
        assert tracker is not None
        assert tracker.failure_count == 0
        assert tracker.window_started_at is None


def test_require_roles_allows_admin_and_denies_client(
    auth_client: TestClient, bff_headers: dict[str, str]
) -> None:
    protected = APIRouter(prefix="/authz")

    @protected.get("/admin")
    def _admin_only(
        _user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    app = auth_client.app
    assert isinstance(app, FastAPI)
    app.include_router(protected)

    admin_token = _register(
        auth_client, "admin@example.com", "securepass1", bff_headers, role="admin"
    )
    client_token = _register(
        auth_client, "basic@example.com", "securepass1", bff_headers, role="client"
    )

    admin_response = auth_client.get(
        "/authz/admin", headers={"Authorization": f"Bearer {admin_token}", **bff_headers}
    )
    assert admin_response.status_code == 200

    client_response = auth_client.get(
        "/authz/admin", headers={"Authorization": f"Bearer {client_token}", **bff_headers}
    )
    assert client_response.status_code == 403


def test_require_roles_uses_normalized_membership_as_canonical(
    auth_client: TestClient, bff_headers: dict[str, str]
) -> None:
    protected = APIRouter(prefix="/authz")

    @protected.get("/admin-canonical")
    def _admin_only(
        _user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    app = auth_client.app
    assert isinstance(app, FastAPI)
    app.include_router(protected)

    token = _register(
        auth_client, "canonical-client@example.com", "securepass1", bff_headers, role="client"
    )

    with app.state.testing_session_local() as session:
        user = session.scalar(select(User).where(User.email == "canonical-client@example.com"))
        assert user is not None
        user.role = Role.ADMIN
        session.commit()

    response = auth_client.get(
        "/authz/admin-canonical",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 403


def test_require_roles_allows_multiple_roles(
    auth_client: TestClient, bff_headers: dict[str, str]
) -> None:
    protected = APIRouter(prefix="/authz")

    @protected.get("/admin-or-client")
    def _admin_or_client(
        _user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.CLIENT))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    app = auth_client.app
    assert isinstance(app, FastAPI)
    app.include_router(protected)

    admin_token = _register(
        auth_client, "multi-admin@example.com", "securepass1", bff_headers, role="admin"
    )
    client_token = _register(
        auth_client, "multi-client@example.com", "securepass1", bff_headers, role="client"
    )
    vendor_token = _register(
        auth_client, "multi-vendor@example.com", "securepass1", bff_headers, role="vendor"
    )

    admin_response = auth_client.get(
        "/authz/admin-or-client", headers={"Authorization": f"Bearer {admin_token}", **bff_headers}
    )
    assert admin_response.status_code == 200

    client_response = auth_client.get(
        "/authz/admin-or-client", headers={"Authorization": f"Bearer {client_token}", **bff_headers}
    )
    assert client_response.status_code == 200

    vendor_response = auth_client.get(
        "/authz/admin-or-client", headers={"Authorization": f"Bearer {vendor_token}", **bff_headers}
    )
    assert vendor_response.status_code == 403


def test_require_roles_falls_back_to_compatibility_role_if_membership_absent(
    auth_client: TestClient,
    bff_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    protected = APIRouter(prefix="/authz")

    @protected.get("/admin-fallback")
    def _admin_only(
        _user: Annotated[User, Depends(require_roles(Role.ADMIN))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    app = auth_client.app
    assert isinstance(app, FastAPI)
    app.include_router(protected)

    token = _register(
        auth_client, "fallback-admin@example.com", "securepass1", bff_headers, role="admin"
    )

    with app.state.testing_session_local() as session:
        user = session.scalar(select(User).where(User.email == "fallback-admin@example.com"))
        assert user is not None
        session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        session.commit()

    caplog.set_level("WARNING", logger="mealmetric.authz")
    response = auth_client.get(
        "/authz/admin-fallback",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert any(
        "normalized role membership missing, using compatibility fallback" in record.message
        for record in caplog.records
    )
