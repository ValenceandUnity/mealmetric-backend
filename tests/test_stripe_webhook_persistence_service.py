import uuid
from dataclasses import dataclass

import pytest

from mealmetric.models.payment_audit_log import PaymentAuditLog, PaymentTransitionSource
from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.services.order_service import OrderCreateResult, OrderCreationError
from mealmetric.services.stripe_webhook_service import (
    StripeWebhookIngressError,
    StripeWebhookIngressResult,
    StripeWebhookIngressService,
)


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


@dataclass
class _FakeSettings:
    stripe_webhook_secret: str = "whsec_test_123"
    stripe_api_version: str | None = None
    stripe_webhook_mode: str = "process"


@dataclass
class _FakeStripeEvent:
    id: str
    type: str


@dataclass
class _InMemoryState:
    webhook_events: dict[str, StripeWebhookEvent]
    payment_sessions_by_checkout: dict[str, PaymentSession]
    payment_sessions_by_intent: dict[str, PaymentSession]
    audit_logs: list[PaymentAuditLog]
    order_creation_calls: list[uuid.UUID]
    order_creation_mode: str


def _install_in_memory_repos(monkeypatch: pytest.MonkeyPatch) -> _InMemoryState:
    state = _InMemoryState(
        webhook_events={},
        payment_sessions_by_checkout={},
        payment_sessions_by_intent={},
        audit_logs=[],
        order_creation_calls=[],
        order_creation_mode="created",
    )

    def _get_event(_session: object, stripe_event_id: str) -> StripeWebhookEvent | None:
        return state.webhook_events.get(stripe_event_id)

    def _create_event(
        _session: object,
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
            payload=payload,
            payload_sha256=payload_sha256,
            request_id=request_id,
            payment_session_id=payment_session_id,
        )
        state.webhook_events[stripe_event_id] = event
        return event

    def _set_event_status(
        _session: object,
        event: StripeWebhookEvent,
        *,
        status: WebhookProcessingStatus,
        processing_error: str | None = None,
    ) -> StripeWebhookEvent:
        event.processing_status = status
        event.processing_error = processing_error
        return event

    def _get_by_checkout(_session: object, checkout_id: str) -> PaymentSession | None:
        return state.payment_sessions_by_checkout.get(checkout_id)

    def _get_by_intent(_session: object, intent_id: str) -> PaymentSession | None:
        return state.payment_sessions_by_intent.get(intent_id)

    def _save_payment_session(_session: object, payment_session: PaymentSession) -> PaymentSession:
        state.payment_sessions_by_checkout[payment_session.stripe_checkout_session_id] = (
            payment_session
        )
        if payment_session.stripe_payment_intent_id is not None:
            state.payment_sessions_by_intent[payment_session.stripe_payment_intent_id] = (
                payment_session
            )
        return payment_session

    def _append_transition(
        _session: object,
        *,
        payment_session_id: uuid.UUID,
        stripe_event_id: str | None,
        from_payment_status: PaymentStatus | None,
        to_payment_status: PaymentStatus,
        transition_source: PaymentTransitionSource,
        message: str | None = None,
    ) -> PaymentAuditLog:
        audit_row = PaymentAuditLog(
            payment_session_id=payment_session_id,
            stripe_event_id=stripe_event_id,
            from_payment_status=from_payment_status,
            to_payment_status=to_payment_status,
            transition_source=transition_source,
            message=message,
        )
        state.audit_logs.append(audit_row)
        return audit_row

    def _create_order_from_successful_payment_session(
        self: object,
        *,
        payment_session_id: uuid.UUID,
        trigger_event_type: str,
        trigger_event_id: str | None,
        request_id: str,
    ) -> OrderCreateResult:
        _ = self
        _ = trigger_event_type
        _ = trigger_event_id
        _ = request_id
        state.order_creation_calls.append(payment_session_id)
        if state.order_creation_mode == "error":
            raise OrderCreationError("basket_snapshot_missing")
        if state.order_creation_mode == "duplicate":
            return OrderCreateResult(outcome="duplicate_skipped", order_id=uuid.uuid4())
        return OrderCreateResult(outcome="created", order_id=uuid.uuid4())

    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.stripe_webhook_event_repo.get_by_stripe_event_id",
        _get_event,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.stripe_webhook_event_repo.create_event_receipt",
        _create_event,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.stripe_webhook_event_repo.set_processing_status",
        _set_event_status,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.stripe_webhook_event_repo.list_events",
        lambda _session, *, limit, processing_status=None: list(
            state.webhook_events.values()
        )[  # noqa: ARG005
            :limit
        ],
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.payment_session_repo.get_by_checkout_session_id",
        _get_by_checkout,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.payment_session_repo.get_by_payment_intent_id",
        _get_by_intent,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.payment_session_repo.save_payment_session",
        _save_payment_session,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.payment_audit_log_repo.append_transition",
        _append_transition,
    )
    monkeypatch.setattr(
        "mealmetric.services.stripe_webhook_service.OrderService.create_order_from_successful_payment_session",
        _create_order_from_successful_payment_session,
    )

    return state


def _checkout_event_payload(session_id: str, payment_intent_id: str | None = None) -> bytes:
    payment_intent_value = "null" if payment_intent_id is None else f'"{payment_intent_id}"'
    return (
        '{"id":"evt_x","type":"checkout.session.completed","data":{"object":{"id":"'
        + session_id
        + '","payment_intent":'
        + payment_intent_value
        + "}}}"
    ).encode("utf-8")


def _payment_intent_payload(event_type: str, payment_intent_id: str) -> bytes:
    return (
        '{"id":"evt_x","type":"'
        + event_type
        + '","data":{"object":{"id":"'
        + payment_intent_id
        + '"}}}'
    ).encode("utf-8")


def test_checkout_session_completed_updates_existing_payment_session_and_creates_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    existing = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_update",
        stripe_payment_intent_id=None,
        payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
    )
    existing.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_update"] = existing

    result = service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_checkout_1", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_update", "pi_update"),
        request_id="req_checkout_1",
    )

    assert isinstance(result, StripeWebhookIngressResult)
    assert result.duplicate is False
    assert existing.payment_status == PaymentStatus.CHECKOUT_SESSION_COMPLETED
    assert existing.stripe_payment_intent_id == "pi_update"
    assert len(state.audit_logs) == 1
    assert len(state.order_creation_calls) == 1
    assert (
        state.webhook_events["evt_checkout_1"].processing_status
        == WebhookProcessingStatus.PROCESSED
    )


def test_checkout_session_completed_missing_payment_session_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_checkout_missing", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_missing", "pi_missing"),
        request_id="req_checkout_missing",
    )

    stored_event = state.webhook_events["evt_checkout_missing"]
    assert stored_event.processing_status == WebhookProcessingStatus.IGNORED
    assert stored_event.processing_error == "payment_session_not_seeded"
    assert state.order_creation_calls == []


def test_checkout_session_completed_order_creation_failure_marks_webhook_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    state.order_creation_mode = "error"
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    payment_session = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_fail_order",
        stripe_payment_intent_id="pi_fail_order",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
    )
    payment_session.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_fail_order"] = payment_session

    with pytest.raises(StripeWebhookIngressError, match="event_processing_failed"):
        service.ingest_event(
            session=session,  # type: ignore[arg-type]
            event=_FakeStripeEvent(id="evt_checkout_fail", type="checkout.session.completed"),
            payload=_checkout_event_payload("cs_fail_order", "pi_fail_order"),
            request_id="req_checkout_fail",
        )

    stored_event = state.webhook_events["evt_checkout_fail"]
    assert stored_event.processing_status == WebhookProcessingStatus.FAILED
    assert stored_event.processing_error == "order_creation_failed:basket_snapshot_missing"


def test_checkout_session_completed_duplicate_order_is_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    state.order_creation_mode = "duplicate"
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    payment_session = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_dup_order",
        stripe_payment_intent_id="pi_dup_order",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
    )
    payment_session.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_dup_order"] = payment_session

    service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_checkout_dup_order", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_dup_order", "pi_dup_order"),
        request_id="req_checkout_dup_order",
    )

    stored_event = state.webhook_events["evt_checkout_dup_order"]
    assert stored_event.processing_status == WebhookProcessingStatus.PROCESSED
    assert len(state.order_creation_calls) == 1


def test_payment_intent_succeeded_marks_paid_and_does_not_create_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    existing = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_success",
        stripe_payment_intent_id="pi_success",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
    )
    existing.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_success"] = existing
    state.payment_sessions_by_intent["pi_success"] = existing

    service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_pi_success", type="payment_intent.succeeded"),
        payload=_payment_intent_payload("payment_intent.succeeded", "pi_success"),
        request_id="req_pi_success",
    )

    assert existing.payment_status == PaymentStatus.PAYMENT_INTENT_SUCCEEDED
    assert state.order_creation_calls == []


def test_payment_intent_failed_marks_failed_and_does_not_create_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    existing = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_failed",
        stripe_payment_intent_id="pi_failed",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
    )
    existing.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_failed"] = existing
    state.payment_sessions_by_intent["pi_failed"] = existing

    service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_pi_failed", type="payment_intent.payment_failed"),
        payload=_payment_intent_payload("payment_intent.payment_failed", "pi_failed"),
        request_id="req_pi_failed",
    )

    assert existing.payment_status == PaymentStatus.PAYMENT_INTENT_FAILED
    assert state.order_creation_calls == []


def test_duplicate_checkout_delivery_does_not_create_second_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    existing = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_dup_checkout",
        stripe_payment_intent_id="pi_dup_checkout",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
    )
    existing.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_dup_checkout"] = existing

    first = service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_checkout_dup", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_dup_checkout", "pi_dup_checkout"),
        request_id="req_checkout_dup_1",
    )
    second = service.ingest_event(
        session=session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_checkout_dup", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_dup_checkout", "pi_dup_checkout"),
        request_id="req_checkout_dup_2",
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert len(state.order_creation_calls) == 1


def test_duplicate_delivery_uses_persisted_receipt_as_durable_idempotency_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    first_session = _FakeSession()
    second_session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    existing = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_durable_dup",
        stripe_payment_intent_id="pi_durable_dup",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
    )
    existing.id = uuid.uuid4()
    state.payment_sessions_by_checkout["cs_durable_dup"] = existing

    first = service.ingest_event(
        session=first_session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_durable_dup", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_durable_dup", "pi_durable_dup"),
        request_id="req_durable_dup_1",
    )
    second = service.ingest_event(
        session=second_session,  # type: ignore[arg-type]
        event=_FakeStripeEvent(id="evt_durable_dup", type="checkout.session.completed"),
        payload=_checkout_event_payload("cs_durable_dup", "pi_durable_dup"),
        request_id="req_durable_dup_2",
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert state.webhook_events["evt_durable_dup"].stripe_event_id == "evt_durable_dup"


def test_replay_checkout_event_noops_when_already_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _install_in_memory_repos(monkeypatch)
    session = _FakeSession()
    service = StripeWebhookIngressService(_FakeSettings())  # type: ignore[arg-type]

    state.webhook_events["evt_checkout_noop"] = StripeWebhookEvent(
        stripe_event_id="evt_checkout_noop",
        event_type="checkout.session.completed",
        processing_status=WebhookProcessingStatus.PROCESSED,
        payload={"data": {"object": {"id": "cs_noop", "payment_intent": "pi_noop"}}},
        payload_sha256="f" * 64,
        request_id="req_checkout_noop",
    )

    result = service.replay_webhook_event(
        session=session,  # type: ignore[arg-type]
        stripe_event_id="evt_checkout_noop",
        request_id="req_checkout_noop",
    )

    assert result.outcome == "noop"
    assert state.order_creation_calls == []
