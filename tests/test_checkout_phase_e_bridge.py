import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.models.payment_session import PaymentStatus
from mealmetric.services.checkout_service import (
    CheckoutPersistenceError,
    CheckoutService,
)
from mealmetric.services.stripe_service import CheckoutSessionResult


@dataclass
class _FakeSettings:
    stripe_secret_key: str = "sk_test_123"
    stripe_success_url: str = "https://example.com/success"
    stripe_cancel_url: str = "https://example.com/cancel"


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


def test_checkout_service_seeds_payment_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = _FakeSession()
    service = CheckoutService(_FakeSettings(), fake_db)  # type: ignore[arg-type]
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "mealmetric.services.checkout_service.StripeService.create_checkout_session",
        lambda self, *, price_id, quantity: CheckoutSessionResult(
            session_id="cs_seed_123",
            checkout_url="https://checkout.stripe.com/c/pay/cs_seed_123",
            payment_intent_id="pi_seed_123",
        ),
    )

    def _fake_create_payment_session(
        _session: Session,
        *,
        stripe_checkout_session_id: str,
        payment_status: PaymentStatus,
        user_id: uuid.UUID | None = None,
        stripe_price_id: str | None = None,
        stripe_payment_intent_id: str | None = None,
        basket_snapshot: dict[str, object] | None = None,
    ) -> object:
        captured["stripe_checkout_session_id"] = stripe_checkout_session_id
        captured["payment_status"] = payment_status
        captured["user_id"] = user_id
        captured["stripe_price_id"] = stripe_price_id
        captured["stripe_payment_intent_id"] = stripe_payment_intent_id
        captured["basket_snapshot"] = basket_snapshot
        return object()

    monkeypatch.setattr(
        "mealmetric.services.checkout_service.payment_session_repo.create_payment_session",
        _fake_create_payment_session,
    )

    user_id = uuid.uuid4()
    result = service.create_checkout_session(
        price_id="price_seed", quantity=1, user_id=user_id
    )

    assert result.session_id == "cs_seed_123"
    assert captured == {
        "stripe_checkout_session_id": "cs_seed_123",
        "payment_status": PaymentStatus.CHECKOUT_SESSION_CREATED,
        "user_id": user_id,
        "stripe_price_id": "price_seed",
        "stripe_payment_intent_id": "pi_seed_123",
        "basket_snapshot": {
            "currency": "usd",
            "items": [
                {
                    "item_type": "product",
                    "external_price_id": "price_seed",
                    "description": None,
                    "quantity": 1,
                    "unit_amount_cents": 0,
                    "subtotal_amount_cents": 0,
                    "tax_amount_cents": 0,
                    "total_amount_cents": 0,
                }
            ],
            "line_items": [
                {
                    "item_type": "product",
                    "external_price_id": "price_seed",
                    "description": None,
                    "quantity": 1,
                    "unit_amount_cents": 0,
                    "subtotal_amount_cents": 0,
                    "tax_amount_cents": 0,
                    "total_amount_cents": 0,
                }
            ],
            "subtotal_amount_cents": 0,
            "tax_amount_cents": 0,
            "total_amount_cents": 0,
        },
    }
    assert fake_db.commit_count == 1
    assert fake_db.rollback_count == 0


def test_checkout_service_rollback_on_persistence_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = _FakeSession()
    service = CheckoutService(_FakeSettings(), fake_db)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "mealmetric.services.checkout_service.StripeService.create_checkout_session",
        lambda self, *, price_id, quantity: CheckoutSessionResult(
            session_id="cs_seed_456",
            checkout_url="https://checkout.stripe.com/c/pay/cs_seed_456",
            payment_intent_id="pi_seed_456",
        ),
    )

    def _raise_integrity_error(
        _session: Session,
        *,
        stripe_checkout_session_id: str,
        payment_status: PaymentStatus,
        user_id: uuid.UUID | None = None,
        stripe_price_id: str | None = None,
        stripe_payment_intent_id: str | None = None,
        basket_snapshot: dict[str, object] | None = None,
    ) -> object:
        raise IntegrityError("insert", {}, Exception("dup"))

    monkeypatch.setattr(
        "mealmetric.services.checkout_service.payment_session_repo.create_payment_session",
        _raise_integrity_error,
    )

    with pytest.raises(CheckoutPersistenceError):
        service.create_checkout_session(
            price_id="price_seed", quantity=1, user_id=uuid.uuid4()
        )

    assert fake_db.commit_count == 0
    assert fake_db.rollback_count == 1
