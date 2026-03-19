import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.core.observability import AUTH_FAILURE_ALERTS_TOTAL, AUTH_FAILURES_TOTAL
from mealmetric.core.settings import get_settings
from mealmetric.models.user import Role, User
from mealmetric.repos import auth_failure_tracker_repo, user_repo
from mealmetric.services.security import verify_password

logger = logging.getLogger("mealmetric.auth")


class EmailAlreadyRegisteredError(Exception):
    pass


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register_user(self, *, email: str, password_hash: str, role: Role) -> User:
        if user_repo.get_by_email(self.session, email) is not None:
            raise EmailAlreadyRegisteredError("email_already_registered")

        try:
            user = user_repo.create_user(
                self.session,
                email=email,
                password_hash=password_hash,
                role=role,
            )
            user_repo.assign_role_to_user(self.session, user.id, role)
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError("email_already_registered") from exc

        return user

    def authenticate_user(
        self,
        *,
        email: str,
        password: str,
        request_id: str | None = None,
    ) -> User | None:
        normalized_email = email.strip().lower()
        user = user_repo.get_by_email(self.session, normalized_email)
        if user is None:
            self._record_auth_failure(
                subject=normalized_email,
                reason="user_not_found",
                request_id=request_id,
            )
            return None
        if not verify_password(password, user.password_hash):
            self._record_auth_failure(
                subject=normalized_email,
                reason="password_mismatch",
                request_id=request_id,
            )
            return None
        auth_failure_tracker_repo.clear(self.session, normalized_email)
        return user

    def revoke_tokens_for_user(self, *, user: User) -> User:
        return user_repo.bump_token_version(self.session, user)

    def _record_auth_failure(self, *, subject: str, reason: str, request_id: str | None) -> None:
        settings = get_settings()
        AUTH_FAILURES_TOTAL.labels(reason=reason).inc()

        now = datetime.now(UTC)
        tracker = auth_failure_tracker_repo.get_or_create(self.session, subject)
        window_delta = timedelta(seconds=settings.auth_failure_alert_window_seconds)
        window_started_at = self._normalize_dt(tracker.window_started_at)

        if window_started_at is None or now - window_started_at > window_delta:
            tracker.failure_count = 0
            tracker.window_started_at = now
            tracker.alert_emitted_at = None

        tracker.failure_count += 1
        tracker.last_failed_at = now
        tracker.last_request_id = request_id
        auth_failure_tracker_repo.save(self.session, tracker)

        if (
            tracker.failure_count >= settings.auth_failure_alert_threshold
            and tracker.alert_emitted_at is None
        ):
            tracker.alert_emitted_at = now
            auth_failure_tracker_repo.save(self.session, tracker)
            AUTH_FAILURE_ALERTS_TOTAL.inc()
            logger.warning(
                "auth failure alert triggered",
                extra={
                    "request_id": request_id or "-",
                    "subject": subject,
                    "failure_count": tracker.failure_count,
                    "window_seconds": settings.auth_failure_alert_window_seconds,
                },
            )

    @staticmethod
    def _normalize_dt(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
