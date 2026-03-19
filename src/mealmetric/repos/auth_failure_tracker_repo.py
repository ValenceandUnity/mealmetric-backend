from sqlalchemy import select
from sqlalchemy.orm import Session

from mealmetric.models.auth_failure_tracker import AuthFailureTracker


def get_by_subject(session: Session, subject: str) -> AuthFailureTracker | None:
    stmt = select(AuthFailureTracker).where(AuthFailureTracker.subject == subject)
    return session.scalar(stmt)


def get_or_create(session: Session, subject: str) -> AuthFailureTracker:
    tracker = get_by_subject(session, subject)
    if tracker is not None:
        return tracker

    tracker = AuthFailureTracker(subject=subject)
    session.add(tracker)
    session.flush()
    return tracker


def save(session: Session, tracker: AuthFailureTracker) -> AuthFailureTracker:
    session.add(tracker)
    session.flush()
    return tracker


def clear(session: Session, subject: str) -> None:
    tracker = get_by_subject(session, subject)
    if tracker is None:
        return

    tracker.failure_count = 0
    tracker.window_started_at = None
    tracker.last_failed_at = None
    tracker.alert_emitted_at = None
    tracker.last_request_id = None
    session.add(tracker)
    session.flush()
