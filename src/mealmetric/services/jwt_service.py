import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Final

from mealmetric.core.settings import get_settings
from mealmetric.models.user import Role

_HEADER_ALG: Final[str] = "HS256"


class JWTError(Exception):
    pass


class JWTDecodeError(JWTError):
    pass


class JWTExpiredError(JWTError):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _encode_payload(payload: dict[str, str | int]) -> str:
    settings = get_settings()
    if settings.jwt_algorithm != _HEADER_ALG:
        raise JWTError("Only HS256 is supported.")
    if not settings.secret_key:
        raise JWTError("SECRET_KEY is not configured.")

    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    header_part = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(
        settings.secret_key.encode("utf-8"), signing_input, digestmod=hashlib.sha256
    ).digest()
    signature_part = _b64url_encode(signature)
    return f"{header_part}.{payload_part}.{signature_part}"


def _decode_payload(token: str) -> dict[str, str | int]:
    settings = get_settings()
    if settings.jwt_algorithm != _HEADER_ALG:
        raise JWTDecodeError("Unsupported JWT algorithm configuration.")
    if not settings.secret_key:
        raise JWTDecodeError("SECRET_KEY is not configured.")

    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError as exc:
        raise JWTDecodeError("Malformed token.") from exc

    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    expected_sig = hmac.new(
        settings.secret_key.encode("utf-8"), signing_input, digestmod=hashlib.sha256
    ).digest()
    provided_sig = _b64url_decode(signature_part)

    if not hmac.compare_digest(provided_sig, expected_sig):
        raise JWTDecodeError("Invalid token signature.")

    try:
        header = json.loads(_b64url_decode(header_part).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise JWTDecodeError("Invalid token encoding.") from exc

    if not isinstance(header, dict) or header.get("alg") != _HEADER_ALG:
        raise JWTDecodeError("Invalid JWT header.")
    if not isinstance(payload, dict):
        raise JWTDecodeError("Invalid JWT payload.")

    raw_exp = payload.get("exp")
    if not isinstance(raw_exp, int):
        raise JWTDecodeError("Missing expiration claim.")

    now_ts = int(datetime.now(UTC).timestamp())
    if raw_exp < now_ts:
        raise JWTExpiredError("Token has expired.")

    clean_payload: dict[str, str | int] = {}
    for key in ("sub", "user_id", "role"):
        value = payload.get(key)
        if not isinstance(value, str):
            raise JWTDecodeError(f"Missing or invalid claim: {key}")
        clean_payload[key] = value
    clean_payload["exp"] = raw_exp
    raw_token_version = payload.get("tv")
    if not isinstance(raw_token_version, int):
        raise JWTDecodeError("Missing or invalid claim: tv")
    clean_payload["tv"] = raw_token_version
    return clean_payload


def create_access_token(
    subject_email: str,
    user_id: uuid.UUID,
    role: Role,
    token_version: int,
    expires_minutes: int,
) -> str:
    expire_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload: dict[str, str | int] = {
        "sub": subject_email,
        "user_id": str(user_id),
        "role": role.value,
        "tv": token_version,
        "exp": int(expire_at.timestamp()),
    }
    return _encode_payload(payload)


def decode_token(token: str) -> dict[str, str | int]:
    return _decode_payload(token)
