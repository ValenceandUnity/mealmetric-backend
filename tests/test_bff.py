import hashlib
import hmac
import time
from collections.abc import Callable

from fastapi.testclient import TestClient


def _signed_headers(
    method: str, path_with_query: str, body: bytes, key: str, timestamp: int, caller_id: str
) -> dict[str, str]:
    body_hash = hashlib.sha256(body).hexdigest()
    signing_input = f"{method}\n{path_with_query}\n{timestamp}\n{caller_id}\n{body_hash}".encode()
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    return {
        "X-MM-BFF-Caller": caller_id,
        "X-MM-BFF-Timestamp": str(timestamp),
        "X-MM-BFF-Signature": signature,
    }


def test_bff_ping_missing_header_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    response = client.get("/bff/ping")
    assert response.status_code == 401


def test_bff_ping_wrong_header_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = {"X-MM-BFF-Timestamp": str(now)}
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 401


def test_bff_ping_valid_primary_key_returns_200(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = _signed_headers("GET", "/bff/ping", b"", "trusted-key-primary", now, "web-bff")
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_bff_ping_valid_secondary_key_returns_200(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_KEY_SECONDARY="trusted-key-secondary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = _signed_headers("GET", "/bff/ping", b"", "trusted-key-secondary", now, "web-bff")
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_bff_ping_secondary_unset_allows_only_primary(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    primary_headers = _signed_headers(
        "GET", "/bff/ping", b"", "trusted-key-primary", now, "web-bff"
    )
    secondary_headers = _signed_headers(
        "GET", "/bff/ping", b"", "trusted-key-secondary", now, "web-bff"
    )
    primary_response = client.get("/bff/ping", headers=primary_headers)
    secondary_response = client.get("/bff/ping", headers=secondary_headers)

    assert primary_response.status_code == 200
    assert primary_response.json() == {"ok": True}
    assert secondary_response.status_code == 401


def test_bff_ping_invalid_key_with_secondary_set_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_KEY_SECONDARY="trusted-key-secondary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = _signed_headers("GET", "/bff/ping", b"", "nope", now, "web-bff")
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 401


def test_bff_ping_missing_caller_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = _signed_headers("GET", "/bff/ping", b"", "trusted-key-primary", now, "web-bff")
    headers.pop("X-MM-BFF-Caller")
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 401


def test_bff_ping_caller_mismatch_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = _signed_headers("GET", "/bff/ping", b"", "trusted-key-primary", now, "web-bff")
    headers["X-MM-BFF-Caller"] = "mobile-bff"
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 401


def test_bff_ping_bad_signature_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    now = int(time.time())
    headers = {
        "X-MM-BFF-Caller": "web-bff",
        "X-MM-BFF-Timestamp": str(now),
        "X-MM-BFF-Signature": "deadbeef",
    }
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 401


def test_bff_ping_timestamp_too_old_returns_401(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    old_ts = int(time.time()) - 301
    headers = _signed_headers("GET", "/bff/ping", b"", "trusted-key-primary", old_ts, "web-bff")
    response = client.get("/bff/ping", headers=headers)
    assert response.status_code == 401


def test_bff_ping_legacy_key_is_rejected_in_production_even_if_flag_set(
    configured_client: Callable[..., TestClient],
) -> None:
    client: TestClient = configured_client(
        APP_ENV="production",
        MEALMETRIC_BFF_KEY_PRIMARY="trusted-key-primary",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="true",
    )
    response = client.get(
        "/bff/ping",
        headers={"X-MM-BFF-Caller": "web-bff", "X-MM-BFF-Key": "trusted-key-primary"},
    )
    assert response.status_code == 401
