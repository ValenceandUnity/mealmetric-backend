from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_trusted_caller
from mealmetric.api.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RegisterRequest,
    TokenResponse,
)
from mealmetric.core.settings import get_settings
from mealmetric.db.session import get_db
from mealmetric.models.user import User
from mealmetric.services.auth_service import AuthService, EmailAlreadyRegisteredError
from mealmetric.services.jwt_service import create_access_token
from mealmetric.services.security import hash_password

public_router = APIRouter(dependencies=[Depends(require_trusted_caller)])
protected_router = APIRouter(
    dependencies=[Depends(require_trusted_caller), Depends(get_current_user)]
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


@public_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DBSessionDep) -> TokenResponse:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    auth_service = AuthService(db)
    try:
        user = auth_service.register_user(
            email=str(payload.email),
            password_hash=hash_password(payload.password),
            role=payload.role,
        )
        db.commit()
    except EmailAlreadyRegisteredError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from exc

    token = create_access_token(
        subject_email=user.email,
        user_id=user.id,
        role=user.role,
        token_version=user.token_version,
        expires_minutes=get_settings().access_token_expire_minutes,
    )
    return TokenResponse(access_token=token)


@public_router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: DBSessionDep) -> TokenResponse:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    auth_service = AuthService(db)
    user = auth_service.authenticate_user(
        email=str(payload.email),
        password=payload.password,
        request_id=getattr(request.state, "request_id", "-"),
    )
    if user is None:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db.commit()
    token = create_access_token(
        subject_email=user.email,
        user_id=user.id,
        role=user.role,
        token_version=user.token_version,
        expires_minutes=get_settings().access_token_expire_minutes,
    )
    return TokenResponse(access_token=token)


@protected_router.get("/me", response_model=MeResponse)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        created_at=current_user.created_at,
    )


@protected_router.post("/logout", response_model=LogoutResponse)
def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    db: DBSessionDep,
) -> LogoutResponse:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    AuthService(db).revoke_tokens_for_user(user=current_user)
    db.commit()
    return LogoutResponse(ok=True)
