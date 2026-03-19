import hashlib
import hmac
import sys
import time
from collections.abc import Callable, Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mealmetric.core.app import create_app
from mealmetric.core.security import token_denylist
from mealmetric.core.settings import get_settings
from mealmetric.db.base import Base
from mealmetric.db.session import get_db


def _signed_bff_headers(
    *,
    method: str,
    path_with_query: str,
    body: bytes,
    key: str,
    caller_id: str = "web-bff",
    timestamp: int | None = None,
) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else timestamp
    body_hash = hashlib.sha256(body).hexdigest()
    signing_input = f"{method}\n{path_with_query}\n{ts}\n{caller_id}\n{body_hash}".encode()
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    return {
        "X-MM-BFF-Caller": caller_id,
        "X-MM-BFF-Timestamp": str(ts),
        "X-MM-BFF-Signature": signature,
    }


def _with_test_db() -> tuple[TestClient, FastAPI]:
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
    return TestClient(app), app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    test_client, _app = _with_test_db()
    try:
        yield test_client
    finally:
        _app.dependency_overrides.pop(get_db, None)
        test_client.close()


@pytest.fixture
def bff_headers() -> dict[str, str]:
    # Legacy test compatibility for non-critical suites. Runtime only honors this
    # path when APP_ENV is development/test and the explicit insecure flag is set.
    return {"X-MM-BFF-Key": "test-bff-key", "X-MM-BFF-Caller": "web-bff"}


@pytest.fixture
def signed_bff_headers() -> Callable[..., dict[str, str]]:
    def _build(
        *,
        method: str,
        path_with_query: str,
        body: bytes = b"",
        key: str = "test-bff-key",
        caller_id: str = "web-bff",
        timestamp: int | None = None,
    ) -> dict[str, str]:
        return _signed_bff_headers(
            method=method,
            path_with_query=path_with_query,
            body=body,
            key=key,
            caller_id=caller_id,
            timestamp=timestamp,
        )

    return _build


@pytest.fixture
def auth_headers(client: TestClient, bff_headers: dict[str, str]) -> dict[str, str]:
    email = f"user-{uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": "client"},
        headers=bff_headers,
    )
    assert response.status_code == 201
    token = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}", **bff_headers}


@pytest.fixture
def admin_auth_headers(client: TestClient, bff_headers: dict[str, str]) -> dict[str, str]:
    email = f"admin-{uuid4()}@example.com"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": "admin"},
        headers=bff_headers,
    )
    assert response.status_code == 201
    token = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}", **bff_headers}


@pytest.fixture
def configured_client(monkeypatch: pytest.MonkeyPatch) -> Callable[..., TestClient]:
    def _build(**env_vars: str) -> TestClient:
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        if "DATABASE_URL" in env_vars:
            app = create_app()
            return TestClient(app)
        test_client, _app = _with_test_db()
        return test_client

    return _build


@pytest.fixture(autouse=True)
def clear_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("KILL_SWITCH_ENABLED", "false")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("MEALMETRIC_BFF_KEY_PRIMARY", "test-bff-key")
    monkeypatch.delenv("MEALMETRIC_BFF_KEY_SECONDARY", raising=False)
    monkeypatch.setenv("MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY", "true")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_SUCCESS_URL", "https://example.com/success")
    monkeypatch.setenv("STRIPE_CANCEL_URL", "https://example.com/cancel")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOKS_ENABLED", "false")
    monkeypatch.setenv("STRIPE_WEBHOOK_MODE", "ingest_only")
    monkeypatch.delenv("STRIPE_API_VERSION", raising=False)


@pytest.fixture(autouse=True)
def clear_token_denylist() -> None:
    token_denylist.clear()
