import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mealmetric.models.payment_session import PaymentStatus

stripe = pytest.importorskip("stripe")


def test_checkout_success_mocked(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_kwargs: dict[str, object] = {}
    captured_payment_session: dict[str, object] = {}

    class _Session:
        id = "cs_test_123"
        url = "https://checkout.stripe.com/c/pay/cs_test_123"
        payment_intent = "pi_test_123"

    def _fake_create(**kwargs: object) -> _Session:
        captured_kwargs.update(kwargs)
        return _Session()

    monkeypatch.setattr(stripe.checkout.Session, "create", _fake_create)

    def _fake_create_payment_session(
        _session: Session,
        *,
        stripe_checkout_session_id: str,
        payment_status: PaymentStatus,
        user_id: object | None,
        stripe_price_id: str | None = None,
        stripe_payment_intent_id: str | None = None,
        basket_snapshot: dict[str, object] | None = None,
    ) -> object:
        captured_payment_session["stripe_checkout_session_id"] = stripe_checkout_session_id
        captured_payment_session["payment_status"] = payment_status
        captured_payment_session["user_id"] = user_id
        captured_payment_session["stripe_price_id"] = stripe_price_id
        captured_payment_session["stripe_payment_intent_id"] = stripe_payment_intent_id
        captured_payment_session["basket_snapshot"] = basket_snapshot
        return object()

    monkeypatch.setattr(
        "mealmetric.services.checkout_service.payment_session_repo.create_payment_session",
        _fake_create_payment_session,
    )

    response = client.post(
        "/api/checkout/session",
        json={
            "price_id": "price_abc123",
            "quantity": 2,
            "currency": "USD",
            "description": "Lean Pack",
            "unit_amount_cents": 1500,
            "subtotal_amount_cents": 3000,
            "tax_amount_cents": 0,
            "total_amount_cents": 3000,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_123",
        "session_id": "cs_test_123",
    }
    assert captured_kwargs == {
        "mode": "payment",
        "line_items": [{"price": "price_abc123", "quantity": 2}],
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
    }
    assert captured_payment_session["stripe_checkout_session_id"] == "cs_test_123"
    assert captured_payment_session["payment_status"] == PaymentStatus.CHECKOUT_SESSION_CREATED
    assert captured_payment_session["stripe_price_id"] == "price_abc123"
    assert captured_payment_session["stripe_payment_intent_id"] == "pi_test_123"
    assert captured_payment_session["basket_snapshot"] == {
        "currency": "usd",
        "items": [
            {
                "item_type": "product",
                "external_price_id": "price_abc123",
                "description": "Lean Pack",
                "quantity": 2,
                "unit_amount_cents": 1500,
                "subtotal_amount_cents": 3000,
                "tax_amount_cents": 0,
                "total_amount_cents": 3000,
            }
        ],
        "line_items": [
            {
                "item_type": "product",
                "external_price_id": "price_abc123",
                "description": "Lean Pack",
                "quantity": 2,
                "unit_amount_cents": 1500,
                "subtotal_amount_cents": 3000,
                "tax_amount_cents": 0,
                "total_amount_cents": 3000,
            }
        ],
        "subtotal_amount_cents": 3000,
        "tax_amount_cents": 0,
        "total_amount_cents": 3000,
    }
