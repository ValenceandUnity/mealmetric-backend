import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus


def _query_by_stripe_event_id(stripe_event_id: str) -> Select[tuple[StripeWebhookEvent]]:
    return select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == stripe_event_id)


def get_by_stripe_event_id(session: Session, stripe_event_id: str) -> StripeWebhookEvent | None:
    return session.scalar(_query_by_stripe_event_id(stripe_event_id))


def list_events(
    session: Session,
    *,
    limit: int,
    processing_status: WebhookProcessingStatus | None = None,
) -> list[StripeWebhookEvent]:
    statement = select(StripeWebhookEvent)
    if processing_status is not None:
        statement = statement.where(StripeWebhookEvent.processing_status == processing_status)
    statement = statement.order_by(desc(StripeWebhookEvent.received_at)).limit(limit)
    return list(session.scalars(statement))


def is_duplicate_event(session: Session, stripe_event_id: str) -> bool:
    return get_by_stripe_event_id(session, stripe_event_id) is not None


def create_event_receipt(
    session: Session,
    *,
    stripe_event_id: str,
    event_type: str,
    payload: dict[str, object],
    payload_sha256: str,
    request_id: str | None,
    payment_session_id: uuid.UUID | None = None,
) -> StripeWebhookEvent:
    event = StripeWebhookEvent(
        stripe_event_id=stripe_event_id,
        event_type=event_type,
        processing_status=WebhookProcessingStatus.RECEIVED,
        payment_session_id=payment_session_id,
        payload=payload,
        payload_sha256=payload_sha256,
        request_id=request_id,
    )
    session.add(event)
    session.flush()
    return event


def set_processing_status(
    session: Session,
    event: StripeWebhookEvent,
    *,
    status: WebhookProcessingStatus,
    processing_error: str | None = None,
) -> StripeWebhookEvent:
    event.processing_status = status
    event.processing_error = processing_error
    if status in {
        WebhookProcessingStatus.PROCESSED,
        WebhookProcessingStatus.FAILED,
        WebhookProcessingStatus.IGNORED,
    }:
        event.processed_at = datetime.now(UTC)
    session.add(event)
    session.flush()
    return event


def list_failed_or_stale_events(
    session: Session,
    *,
    stale_before: datetime,
) -> list[StripeWebhookEvent]:
    stmt = (
        select(StripeWebhookEvent)
        .where(
            (StripeWebhookEvent.processing_status == WebhookProcessingStatus.FAILED)
            | (
                StripeWebhookEvent.processing_status.in_(
                    (
                        WebhookProcessingStatus.RECEIVED,
                        WebhookProcessingStatus.PROCESSING,
                    )
                )
                & (StripeWebhookEvent.received_at <= stale_before)
            )
        )
        .order_by(StripeWebhookEvent.received_at.asc(), StripeWebhookEvent.stripe_event_id.asc())
    )
    return list(session.scalars(stmt))
