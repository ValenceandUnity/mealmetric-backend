import hashlib
import hmac
import logging
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from mealmetric.core.settings import get_settings
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.repos.user_repo import get_by_id, get_roles_for_user
from mealmetric.services.jwt_service import JWTDecodeError, JWTExpiredError, decode_token

# We keep OAuth2PasswordBearer for FastAPI docs/client compatibility
# while accepting JSON payloads in /auth/login for the minimal baseline.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DBSessionDep = Annotated[Session | None, Depends(get_db)]
TokenDep = Annotated[str, Depends(oauth2_scheme)]
_CALLER_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
_AUTHZ_LOGGER = logging.getLogger("mealmetric.authz")


@dataclass(frozen=True)
class TrustedCaller:
    caller_id: str


def get_current_user(
    session: DBSessionDep,
    token: TokenDep,
) -> User:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    try:
        payload = decode_token(token)
        user_id = uuid.UUID(str(payload["user_id"]))
        token_version = int(payload["tv"])
    except (JWTDecodeError, JWTExpiredError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = get_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*allowed_roles: Role) -> Callable[..., User]:
    allowed_roles_set = frozenset(allowed_roles)

    def _checker(
        request: Request,
        session: DBSessionDep,
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db_unavailable",
            )

        normalized_roles = get_roles_for_user(session, user.id)
        if normalized_roles:
            if normalized_roles.isdisjoint(allowed_roles_set):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient role permissions.",
                )
            return user

        compatibility_role = user.role
        if not isinstance(compatibility_role, Role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions.",
            )

        request_id = getattr(request.state, "request_id", "-")
        _AUTHZ_LOGGER.warning(
            "normalized role membership missing, using compatibility fallback",
            extra={
                "request_id": request_id,
                "user_id": str(user.id),
                "role": compatibility_role.value,
            },
        )

        if compatibility_role not in allowed_roles_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions.",
            )
        return user

    return _checker


def _trusted_caller_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid trusted caller credentials.",
    )


def _path_with_query(request: Request) -> str:
    query = request.url.query
    return request.url.path if not query else f"{request.url.path}?{query}"


def _sign_bff_request(
    method: str, path_with_query: str, timestamp: str, caller_id: str, body_hash: str, key: str
) -> str:
    signing_input = f"{method}\n{path_with_query}\n{timestamp}\n{caller_id}\n{body_hash}".encode()
    return hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()


async def require_trusted_caller(
    request: Request,
    timestamp: Annotated[str | None, Header(alias="X-MM-BFF-Timestamp")] = None,
    signature: Annotated[str | None, Header(alias="X-MM-BFF-Signature")] = None,
    caller_id: Annotated[str | None, Header(alias="X-MM-BFF-Caller")] = None,
    bff_key: Annotated[str | None, Header(alias="X-MM-BFF-Key")] = None,
) -> TrustedCaller:
    settings = get_settings()
    primary_key = settings.mealmetric_bff_key_primary
    secondary_key = settings.mealmetric_bff_key_secondary
    allow_insecure_legacy_key = (
        settings.mealmetric_bff_allow_insecure_legacy_key
        and settings.app_env.lower() in {"development", "test"}
    )

    if caller_id is None or not _CALLER_PATTERN.fullmatch(caller_id):
        raise _trusted_caller_error()

    if allow_insecure_legacy_key and bff_key is not None:
        if hmac.compare_digest(bff_key, primary_key):
            return TrustedCaller(caller_id=caller_id)
        if secondary_key is not None and hmac.compare_digest(bff_key, secondary_key):
            return TrustedCaller(caller_id=caller_id)

    if timestamp is None or signature is None:
        raise _trusted_caller_error()

    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise _trusted_caller_error() from exc

    now_ts = int(time.time())
    if abs(now_ts - ts) > settings.mealmetric_bff_signature_ttl_seconds:
        raise _trusted_caller_error()

    request_body = await request.body()
    body_hash = hashlib.sha256(request_body).hexdigest()
    method = request.method.upper()
    path_with_query = _path_with_query(request)

    provided_signature = signature.lower()
    expected_primary = _sign_bff_request(
        method, path_with_query, timestamp, caller_id, body_hash, primary_key
    )
    if hmac.compare_digest(provided_signature, expected_primary):
        return TrustedCaller(caller_id=caller_id)

    if secondary_key is not None:
        expected_secondary = _sign_bff_request(
            method, path_with_query, timestamp, caller_id, body_hash, secondary_key
        )
        if hmac.compare_digest(provided_signature, expected_secondary):
            return TrustedCaller(caller_id=caller_id)

    raise _trusted_caller_error()
