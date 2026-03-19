import uuid
from datetime import UTC, datetime

from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.repos import stripe_webhook_event_repo


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.scalar_result: object | None = None
        self.flush_count = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_count += 1

    def scalar(self, _stmt: object) -> object | None:
        return self.scalar_result

    def scalars(self, _stmt: object) -> list[StripeWebhookEvent]:
        return [
            StripeWebhookEvent(
                stripe_event_id="evt_list_1",
                event_type="checkout.session.completed",
                payload={"id": "evt_list_1"},
                payload_sha256="d" * 64,
                request_id="req_list_1",
            )
        ]


def test_create_event_receipt_succeeds() -> None:
    session = _FakeSession()
    payload: dict[str, object] = {"id": "evt_1", "type": "checkout.session.completed"}

    event = stripe_webhook_event_repo.create_event_receipt(
        session,  # type: ignore[arg-type]
        stripe_event_id="evt_1",
        event_type="checkout.session.completed",
        payload=payload,
        payload_sha256="a" * 64,
        request_id="req_1",
        payment_session_id=uuid.uuid4(),
    )

    assert isinstance(event, StripeWebhookEvent)
    assert event.stripe_event_id == "evt_1"
    assert event.payload == payload
    assert event.payload_sha256 == "a" * 64
    assert event.processing_status == WebhookProcessingStatus.RECEIVED
    assert session.flush_count == 1
    assert session.added[-1] is event


def test_duplicate_event_detection() -> None:
    session = _FakeSession()
    session.scalar_result = StripeWebhookEvent(
        stripe_event_id="evt_dup",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_dup"},
        payload_sha256="b" * 64,
        request_id="req_dup",
    )

    assert stripe_webhook_event_repo.is_duplicate_event(session, "evt_dup")  # type: ignore[arg-type]


def test_set_processing_status_updates_state() -> None:
    session = _FakeSession()
    event = StripeWebhookEvent(
        stripe_event_id="evt_status",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_status"},
        payload_sha256="c" * 64,
        request_id="req_status",
    )

    updated = stripe_webhook_event_repo.set_processing_status(
        session,  # type: ignore[arg-type]
        event,
        status=WebhookProcessingStatus.PROCESSED,
        processing_error=None,
    )

    assert updated.processing_status == WebhookProcessingStatus.PROCESSED
    assert isinstance(updated.processed_at, datetime)
    assert updated.processed_at.tzinfo is UTC
    assert session.flush_count == 1


def test_list_events_returns_rows() -> None:
    session = _FakeSession()

    rows = stripe_webhook_event_repo.list_events(
        session,  # type: ignore[arg-type]
        limit=10,
        processing_status=None,
    )

    assert len(rows) == 1
    assert rows[0].stripe_event_id == "evt_list_1"
