import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from mealmetric.models.notification import Notification, NotificationType


def create_notification(
    session: Session,
    *,
    recipient_user_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    notification_type: NotificationType,
    title: str,
    message: str,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> Notification:
    notification = Notification(
        recipient_user_id=recipient_user_id,
        actor_user_id=actor_user_id,
        type=notification_type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    session.add(notification)
    session.flush()
    return notification


def list_notifications_for_user(session: Session, user_id: uuid.UUID) -> list[Notification]:
    stmt: Select[tuple[Notification]] = (
        select(Notification)
        .where(Notification.recipient_user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    return list(session.scalars(stmt))


def count_unread_notifications_for_user(session: Session, user_id: uuid.UUID) -> int:
    stmt = select(func.count(Notification.id)).where(
        Notification.recipient_user_id == user_id,
        Notification.is_read.is_(False),
    )
    return int(session.scalar(stmt) or 0)


def get_notification_for_user(
    session: Session,
    *,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Notification | None:
    stmt: Select[tuple[Notification]] = select(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_user_id == user_id,
    )
    return session.scalar(stmt)


def save_notification(session: Session, notification: Notification) -> Notification:
    session.add(notification)
    session.flush()
    return notification
