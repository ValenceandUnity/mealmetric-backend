import hashlib
import hmac
import json
import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from mealmetric.services.stripe_webhook_service import (
    StripeWebhookIngressError,
    StripeWebhookIngressResult,
    StripeWebhookIngressService,
)


def _stripe_signature_header(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode()
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


def _event_payload() -> bytes:
    return json.dumps(
        {
            "id": "evt_test_webhook_1",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_123"}},
        }
    ).encode("utf-8")


def test_stripe_webhook_valid_signature_accepted_without_bff(
    configured_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
        MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY="false",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")
    monkeypatch.setattr(
        StripeWebhookIngressService,
        "ingest_event",
        lambda self, *, session, event, payload, request_id: StripeWebhookIngressResult(
            duplicate=False,
            mode="ingest_only",
            event_id="evt_test_webhook_1",
        ),
    )

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"received": True, "duplicate": False}


def test_stripe_webhook_invalid_signature_rejected(
    configured_client: Callable[..., TestClient],
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": "t=1,v1=deadbeef", "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Stripe signature."}


def test_stripe_webhook_missing_signature_rejected(
    configured_client: Callable[..., TestClient],
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Missing Stripe-Signature header."}


def test_stripe_webhook_duplicate_delivery_returns_200(
    configured_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")

    def _raise_duplicate(
        self: StripeWebhookIngressService,
        *,
        session: object,
        event: object,
        payload: bytes,
        request_id: str,
    ) -> StripeWebhookIngressResult:
        return StripeWebhookIngressResult(duplicate=True, mode="ingest_only", event_id="evt_dup")

    monkeypatch.setattr(StripeWebhookIngressService, "ingest_event", _raise_duplicate)

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"received": True, "duplicate": True}


def test_stripe_webhook_logs_request_id(
    configured_client: Callable[..., TestClient],
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")
    monkeypatch.setattr(
        StripeWebhookIngressService,
        "ingest_event",
        lambda self, *, session, event, payload, request_id: StripeWebhookIngressResult(
            duplicate=False,
            mode="ingest_only",
            event_id="evt_test_webhook_1",
        ),
    )

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={
            "Stripe-Signature": signature,
            "Content-Type": "application/json",
            "X-Request-ID": "req-webhook-123",
        },
    )

    assert response.status_code == 200
    stdout, _ = capfd.readouterr()
    assert '"request_id": "req-webhook-123"' in stdout


def test_stripe_webhook_kill_switch_blocked(configured_client: Callable[..., TestClient]) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
        KILL_SWITCH_ENABLED="true",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable"}


def test_stripe_webhook_disabled_returns_503(
    configured_client: Callable[..., TestClient],
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="false",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Stripe webhooks are disabled."}


def test_stripe_webhook_db_unavailable_returns_503(
    configured_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")

    def _raise_db_unavailable(
        self: StripeWebhookIngressService,
        *,
        session: object,
        event: object,
        payload: bytes,
        request_id: str,
    ) -> StripeWebhookIngressResult:
        raise StripeWebhookIngressError("db_unavailable")

    monkeypatch.setattr(StripeWebhookIngressService, "ingest_event", _raise_db_unavailable)

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Webhook ingress unavailable."}


def test_stripe_webhook_unexpected_ingress_error_returns_503(
    configured_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    client: TestClient = configured_client(
        STRIPE_WEBHOOKS_ENABLED="true",
        STRIPE_WEBHOOK_SECRET="whsec_test_123",
    )
    payload = _event_payload()
    signature = _stripe_signature_header(payload, "whsec_test_123")

    def _raise_unexpected(
        self: StripeWebhookIngressService,
        *,
        session: object,
        event: object,
        payload: bytes,
        request_id: str,
    ) -> StripeWebhookIngressResult:
        raise StripeWebhookIngressError("unexpected_stripe_api_version")

    monkeypatch.setattr(StripeWebhookIngressService, "ingest_event", _raise_unexpected)

    response = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Webhook ingress unavailable."}
