import uuid
from typing import cast

from sqlalchemy.orm import Session

from mealmetric.models.payment_audit_log import PaymentTransitionSource
from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.repos import payment_audit_log_repo, payment_session_repo


class _FakeSession:
    def __init__(self) -> None:
        self.scalar_result: object | None = None
        self.added: list[object] = []
        self.flush_count = 0

    def scalar(self, _stmt: object) -> object | None:
        return self.scalar_result

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_count += 1


def test_get_by_checkout_session_id_returns_scalar_result() -> None:
    session = _FakeSession()
    expected = PaymentSession(
        stripe_checkout_session_id="cs_lookup",
        stripe_payment_intent_id=None,
        payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
    )
    session.scalar_result = expected

    result = payment_session_repo.get_by_checkout_session_id(cast(Session, session), "cs_lookup")

    assert result is expected


def test_get_by_payment_intent_id_returns_scalar_result() -> None:
    session = _FakeSession()
    expected = PaymentSession(
        stripe_checkout_session_id="cs_lookup_pi",
        stripe_payment_intent_id="pi_lookup",
        payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
    )
    session.scalar_result = expected

    result = payment_session_repo.get_by_payment_intent_id(cast(Session, session), "pi_lookup")

    assert result is expected


def test_create_and_save_payment_session() -> None:
    session = _FakeSession()

    created = payment_session_repo.create_payment_session(
        cast(Session, session),
        stripe_checkout_session_id="cs_create",
        payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
        user_id=uuid.uuid4(),
        stripe_price_id="price_123",
        stripe_payment_intent_id="pi_create",
    )

    assert created.stripe_checkout_session_id == "cs_create"
    assert created.stripe_payment_intent_id == "pi_create"
    assert session.flush_count == 1
    assert session.added[-1] is created

    saved = payment_session_repo.save_payment_session(cast(Session, session), created)
    assert saved is created
    assert session.flush_count == 2


def test_append_transition_persists_audit_row() -> None:
    session = _FakeSession()
    payment_session_id = uuid.uuid4()

    audit_row = payment_audit_log_repo.append_transition(
        cast(Session, session),
        payment_session_id=payment_session_id,
        stripe_event_id="evt_audit_1",
        from_payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
        to_payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        transition_source=PaymentTransitionSource.STRIPE_WEBHOOK,
        message="applied_webhook",
    )

    assert audit_row.payment_session_id == payment_session_id
    assert audit_row.stripe_event_id == "evt_audit_1"
    assert audit_row.transition_source == PaymentTransitionSource.STRIPE_WEBHOOK
    assert session.flush_count == 1
