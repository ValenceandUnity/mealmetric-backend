from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.notification import (
    NotificationListResponse,
    NotificationRead,
    NotificationUnreadCountResponse,
)
from mealmetric.db.session import get_db
from mealmetric.models.notification import Notification
from mealmetric.models.user import Role, User
from mealmetric.services.notification_service import NotificationNotFoundError, NotificationService

router = APIRouter(
    prefix="/notifications",
    dependencies=[
        Depends(require_trusted_caller),
        Depends(require_roles(Role.CLIENT, Role.PT)),
    ],
    tags=["notifications"],
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


def _to_read(notification: Notification) -> NotificationRead:
    return NotificationRead(
        id=notification.id,
        recipient_user_id=notification.recipient_user_id,
        actor_user_id=notification.actor_user_id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        related_entity_type=notification.related_entity_type,
        related_entity_id=notification.related_entity_id,
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


def _run_mutation[T](db: Session, operation: Callable[[], T]) -> T:
    try:
        result = operation()
        db.commit()
        return result
    except NotificationNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("", response_model=NotificationListResponse)
def list_notifications(db: DBSessionDep, current_user: CurrentUserDep) -> NotificationListResponse:
    session = _require_db(db)
    service = NotificationService(session)
    items = [_to_read(item) for item in service.list_for_user(current_user.id)]
    return NotificationListResponse(items=items, count=len(items))


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def get_unread_count(
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> NotificationUnreadCountResponse:
    session = _require_db(db)
    service = NotificationService(session)
    return NotificationUnreadCountResponse(count=service.count_unread_for_user(current_user.id))


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_as_read(
    notification_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> NotificationRead:
    session = _require_db(db)
    service = NotificationService(session)

    def _operation() -> Notification:
        return service.mark_as_read(notification_id=notification_id, user_id=current_user.id)

    notification = _run_mutation(session, _operation)
    return _to_read(notification)
