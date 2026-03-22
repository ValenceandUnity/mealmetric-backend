import uuid
from datetime import datetime

from pydantic import BaseModel

from mealmetric.models.notification import NotificationType


class NotificationRead(BaseModel):
    id: uuid.UUID
    recipient_user_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    type: NotificationType
    title: str
    message: str
    related_entity_type: str | None
    related_entity_id: str | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    count: int


class NotificationUnreadCountResponse(BaseModel):
    count: int
