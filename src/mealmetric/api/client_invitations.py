from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.training import PTClientInvitationListResponse, PTClientInvitationRead
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.training_service import (
    PtClientInvitationService,
    PTClientInvitationView,
    TrainingConflictError,
    TrainingNotFoundError,
    TrainingPermissionError,
    TrainingValidationError,
)

router = APIRouter(
    prefix="/client/invitations",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-invitations"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    return db


def _translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TrainingNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, TrainingConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, TrainingPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, TrainingValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


def _run_mutation[T](db: Session, operation: Callable[[], T]) -> T:
    try:
        result = operation()
        db.commit()
        return result
    except (
        TrainingNotFoundError,
        TrainingConflictError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        db.rollback()
        raise _translate_service_error(exc) from exc


def _to_read(view: PTClientInvitationView) -> PTClientInvitationRead:
    invitation = view.invitation
    return PTClientInvitationRead(
        id=invitation.id,
        pt_user_id=invitation.pt_user_id,
        client_user_id=invitation.client_user_id,
        pt_email=view.pt_email,
        client_email=view.client_email,
        client_email_snapshot=invitation.client_email_snapshot,
        status=invitation.status,
        created_at=invitation.created_at,
        responded_at=invitation.responded_at,
    )


@router.get("", response_model=PTClientInvitationListResponse)
def list_client_invitations(
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTClientInvitationListResponse:
    session = _require_db(db)
    service = PtClientInvitationService(session)
    items = [_to_read(item) for item in service.list_for_client(current_user.id)]
    return PTClientInvitationListResponse(items=items, count=len(items))


@router.post("/{invitation_id}/accept", response_model=PTClientInvitationRead)
def accept_client_invitation(
    invitation_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTClientInvitationRead:
    session = _require_db(db)
    service = PtClientInvitationService(session)

    def _operation() -> PTClientInvitationView:
        return service.accept_invitation(
            client_user_id=current_user.id,
            invitation_id=invitation_id,
        )

    updated = _run_mutation(session, _operation)
    return _to_read(updated)


@router.post("/{invitation_id}/decline", response_model=PTClientInvitationRead)
def decline_client_invitation(
    invitation_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTClientInvitationRead:
    session = _require_db(db)
    service = PtClientInvitationService(session)

    def _operation() -> PTClientInvitationView:
        return service.decline_invitation(
            client_user_id=current_user.id,
            invitation_id=invitation_id,
        )

    updated = _run_mutation(session, _operation)
    return _to_read(updated)
