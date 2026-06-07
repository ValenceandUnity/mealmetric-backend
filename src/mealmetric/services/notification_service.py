import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from mealmetric.models.notification import Notification, NotificationType
from mealmetric.repos import notification_repo


class NotificationNotFoundError(Exception):
    """Raised when a notification is outside the current user's scope."""


class NotificationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID) -> list[Notification]:
        return notification_repo.list_notifications_for_user(self._session, user_id)

    def count_unread_for_user(self, user_id: uuid.UUID) -> int:
        return notification_repo.count_unread_notifications_for_user(self._session, user_id)

    def mark_as_read(self, *, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification:
        notification = notification_repo.get_notification_for_user(
            self._session,
            notification_id=notification_id,
            user_id=user_id,
        )
        if notification is None:
            raise NotificationNotFoundError("notification_not_found")
        notification.is_read = True
        return notification_repo.save_notification(self._session, notification)

    def create_client_workout_logged_notification(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        workout_log_id: uuid.UUID,
    ) -> Notification:
        return notification_repo.create_notification(
            self._session,
            recipient_user_id=pt_user_id,
            actor_user_id=client_user_id,
            notification_type=NotificationType.CLIENT_WORKOUT_LOGGED,
            title="Client logged a workout",
            message="A linked client submitted a new workout log.",
            related_entity_type="workout_log",
            related_entity_id=str(workout_log_id),
        )

    def create_pt_workout_note_added_notification(
        self,
        *,
        client_user_id: uuid.UUID,
        pt_user_id: uuid.UUID,
        workout_log_id: uuid.UUID,
    ) -> Notification:
        return notification_repo.create_notification(
            self._session,
            recipient_user_id=client_user_id,
            actor_user_id=pt_user_id,
            notification_type=NotificationType.PT_WORKOUT_NOTE_ADDED,
            title="Coach note added",
            message="Your trainer added a note to one of your workout logs.",
            related_entity_type="workout_log",
            related_entity_id=str(workout_log_id),
        )

    def create_pt_assignment_created_notification(
        self,
        *,
        client_user_id: uuid.UUID,
        pt_user_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> Notification:
        return notification_repo.create_notification(
            self._session,
            recipient_user_id=client_user_id,
            actor_user_id=pt_user_id,
            notification_type=NotificationType.PT_ASSIGNMENT_CREATED,
            title="Training assignment added",
            message="Your trainer assigned you a new training package.",
            related_entity_type="client_training_package_assignment",
            related_entity_id=str(assignment_id),
        )

    def create_pt_client_invitation_received_notification(
        self,
        *,
        client_user_id: uuid.UUID,
        pt_user_id: uuid.UUID,
        pt_email: str,
        invitation_id: uuid.UUID,
    ) -> Notification:
        return notification_repo.create_notification(
            self._session,
            recipient_user_id=client_user_id,
            actor_user_id=pt_user_id,
            notification_type=NotificationType.PT_CLIENT_INVITATION_RECEIVED,
            title="Trainer invite received",
            message=f"{pt_email} invited you to join their PT roster.",
            related_entity_type="pt_client_invitation",
            related_entity_id=str(invitation_id),
        )

    def create_pt_client_invitation_accepted_notification(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        client_email: str,
        invitation_id: uuid.UUID,
    ) -> Notification:
        return notification_repo.create_notification(
            self._session,
            recipient_user_id=pt_user_id,
            actor_user_id=client_user_id,
            notification_type=NotificationType.PT_CLIENT_INVITATION_ACCEPTED,
            title="Client accepted invite",
            message=f"{client_email} accepted your PT roster invite.",
            related_entity_type="pt_client_invitation",
            related_entity_id=str(invitation_id),
        )

    def create_pt_client_invitation_declined_notification(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        client_email: str,
        invitation_id: uuid.UUID,
    ) -> Notification:
        return notification_repo.create_notification(
            self._session,
            recipient_user_id=pt_user_id,
            actor_user_id=client_user_id,
            notification_type=NotificationType.PT_CLIENT_INVITATION_DECLINED,
            title="Client declined invite",
            message=f"{client_email} declined your PT roster invite.",
            related_entity_type="pt_client_invitation",
            related_entity_id=str(invitation_id),
        )

    def mark_related_entity_notifications_as_read(
        self,
        *,
        recipient_user_id: uuid.UUID,
        related_entity_type: str,
        related_entity_id: str,
    ) -> list[Notification]:
        notifications = notification_repo.list_notifications_for_related_entity(
            self._session,
            recipient_user_id=recipient_user_id,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        return self._mark_notifications_as_read(notifications)

    def _mark_notifications_as_read(self, notifications: Iterable[Notification]) -> list[Notification]:
        updated: list[Notification] = []
        for notification in notifications:
            if notification.is_read:
                updated.append(notification)
                continue
            notification.is_read = True
            updated.append(notification_repo.save_notification(self._session, notification))
        return updated
