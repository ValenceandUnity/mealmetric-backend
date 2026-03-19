import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from mealmetric.models.user import Role
from mealmetric.services import jwt_service


@dataclass
class _FakeJWTSettings:
    secret_key: str = "test-secret"
    jwt_algorithm: str = "HS256"


def _patch_settings(monkeypatch: pytest.MonkeyPatch, settings: _FakeJWTSettings) -> None:
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)


def _build_token(payload: dict[str, str | int], secret_key: str) -> str:
    header_part = jwt_service._b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_part = jwt_service._b64url_encode(json.dumps(payload).encode())
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    signature_part = jwt_service._b64url_encode(signature)
    return f"{header_part}.{payload_part}.{signature_part}"


def test_create_and_decode_token_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    user_id = uuid.uuid4()

    token = jwt_service.create_access_token(
        subject_email="jwt@example.com",
        user_id=user_id,
        role=Role.CLIENT,
        token_version=0,
        expires_minutes=5,
    )
    payload = jwt_service.decode_token(token)

    assert payload["sub"] == "jwt@example.com"
    assert payload["user_id"] == str(user_id)
    assert payload["role"] == Role.CLIENT.value
    assert payload["tv"] == 0
    assert isinstance(payload["exp"], int)


def test_encode_payload_rejects_non_hs256(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings(jwt_algorithm="RS256"))
    with pytest.raises(jwt_service.JWTError):
        jwt_service._encode_payload(
            {"sub": "a", "user_id": "b", "role": "client", "tv": 0, "exp": 1}
        )


def test_decode_rejects_unsupported_alg_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings(jwt_algorithm="RS256"))
    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token("a.b.c")


def test_decode_rejects_malformed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token("not-a-jwt")


def test_decode_rejects_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    valid_token = _build_token(
        {
            "sub": "jwt@example.com",
            "user_id": str(uuid.uuid4()),
            "role": Role.CLIENT.value,
            "tv": 0,
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        "test-secret",
    )
    header_part, payload_part, signature_part = valid_token.split(".")
    tampered_signature = ("a" if signature_part[0] != "a" else "b") + signature_part[1:]
    tampered = f"{header_part}.{payload_part}.{tampered_signature}"
    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token(tampered)


def test_decode_rejects_invalid_token_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    header_part = jwt_service._b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_part = jwt_service._b64url_encode(b"\xff")
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(
        b"test-secret",
        signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    token = f"{header_part}.{payload_part}.{jwt_service._b64url_encode(signature)}"

    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token(token)


def test_decode_rejects_invalid_header(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    header_part = jwt_service._b64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload_part = jwt_service._b64url_encode(
        json.dumps(
            {
                "sub": "jwt@example.com",
                "user_id": str(uuid.uuid4()),
                "role": Role.CLIENT.value,
                "tv": 0,
                "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            }
        ).encode()
    )
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(
        b"test-secret",
        signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    token = f"{header_part}.{payload_part}.{jwt_service._b64url_encode(signature)}"

    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token(token)


def test_decode_rejects_non_dict_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    header_part = jwt_service._b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_part = jwt_service._b64url_encode(json.dumps(["not", "dict"]).encode())
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(
        b"test-secret",
        signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    token = f"{header_part}.{payload_part}.{jwt_service._b64url_encode(signature)}"

    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token(token)


def test_decode_rejects_missing_exp_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    token = _build_token(
        {
            "sub": "jwt@example.com",
            "user_id": str(uuid.uuid4()),
            "role": Role.CLIENT.value,
        },
        "test-secret",
    )
    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token(token)


def test_decode_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    token = _build_token(
        {
            "sub": "jwt@example.com",
            "user_id": str(uuid.uuid4()),
            "role": Role.CLIENT.value,
            "tv": 0,
            "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
        },
        "test-secret",
    )
    with pytest.raises(jwt_service.JWTExpiredError):
        jwt_service.decode_token(token)


def test_decode_rejects_missing_required_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, _FakeJWTSettings())
    token = _build_token(
        {
            "sub": "jwt@example.com",
            "user_id": str(uuid.uuid4()),
            "role": Role.CLIENT.value,
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        "test-secret",
    )
    with pytest.raises(jwt_service.JWTDecodeError):
        jwt_service.decode_token(token)
