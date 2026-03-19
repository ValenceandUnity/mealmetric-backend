import pytest
from fastapi.testclient import TestClient

stripe = pytest.importorskip("stripe")


def test_checkout_stripe_failure(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_create(**_kwargs: object) -> None:
        raise stripe.APIError("boom")

    monkeypatch.setattr(stripe.checkout.Session, "create", _fake_create)

    response = client.post(
        "/api/checkout/session",
        json={"price_id": "price_abc123", "quantity": 1},
        headers=auth_headers,
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to create checkout session."}
