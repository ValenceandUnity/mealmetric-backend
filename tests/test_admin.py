import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealmetric.models.payment_session import PaymentStatus
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.services.reconciliation_service import (
    ReconciliationPaymentMismatch,
    ReconciliationReport,
    ReconciliationSubscriptionMismatch,
    ReconciliationWebhookMismatch,
)
from mealmetric.services.stripe_webhook_service import (
    StripeWebhookIngressError,
    StripeWebhookReplayResult,
)


def _register(client: TestClient, email: str, role: str, bff_headers: dict[str, str]) -> str:
    payload = {"email": email, "password": "securepass1", "role": role}
    content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = client.post(
        "/auth/register",
        content=content,
        headers={**bff_headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def test_admin_ping_requires_auth(client: TestClient) -> None:
    response = client.get("/admin/ping")
    assert response.status_code == 401


def test_admin_ping_requires_bff_header(client: TestClient, bff_headers: dict[str, str]) -> None:
    token = _register(client, f"client-bff-route-{uuid4()}@example.com", "admin", bff_headers)
    response = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_admin_ping_forbidden_for_non_admin(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    token = _register(client, f"client-admin-route-{uuid4()}@example.com", "client", bff_headers)
    response = client.get(
        "/admin/ping",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 403


def test_admin_ping_allows_admin(client: TestClient, signed_bff_headers) -> None:  # type: ignore[no-untyped-def]
    register_payload = {
        "email": f"admin-admin-route-{uuid4()}@example.com",
        "password": "securepass1",
        "role": "admin",
    }
    register_headers = signed_bff_headers(
        method="POST",
        path_with_query="/auth/register",
        body=json.dumps(register_payload, separators=(",", ":")).encode("utf-8"),
    )
    token = _register(client, register_payload["email"], "admin", register_headers)
    response = client.get(
        "/admin/ping",
        headers={
            "Authorization": f"Bearer {token}",
            **signed_bff_headers(method="GET", path_with_query="/admin/ping"),
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_admin_webhook_list_forbidden_for_non_admin(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    token = _register(client, f"client-webhook-list-{uuid4()}@example.com", "client", bff_headers)
    response = client.get(
        "/admin/payments/webhooks",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 403


def test_admin_webhook_list_requires_bff_header(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    token = _register(client, f"admin-webhook-bff-{uuid4()}@example.com", "admin", bff_headers)
    response = client.get(
        "/admin/payments/webhooks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_admin_webhook_list_allows_admin(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-list-{uuid4()}@example.com", "admin", bff_headers)

    now = datetime.now(UTC)
    event = StripeWebhookEvent(
        stripe_event_id="evt_admin_list_1",
        event_type="payment_intent.payment_failed",
        processing_status=WebhookProcessingStatus.FAILED,
        payload={"id": "evt_admin_list_1"},
        payload_sha256="a" * 64,
        request_id="req-admin-list",
        processing_error="stripe_timeout",
        received_at=now,
        processed_at=now,
    )
    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.list_webhook_events",
        lambda self, *, session, limit, processing_status=None: [event],
    )

    response = client.get(
        "/admin/payments/webhooks",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["stripe_event_id"] == "evt_admin_list_1"
    assert payload["items"][0]["processing_status"] == "failed"


def test_admin_webhook_detail_returns_event(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-detail-{uuid4()}@example.com", "admin", bff_headers)

    now = datetime.now(UTC)
    event = StripeWebhookEvent(
        stripe_event_id="evt_admin_detail_1",
        event_type="checkout.session.completed",
        processing_status=WebhookProcessingStatus.PROCESSED,
        payload={"id": "evt_admin_detail_1", "type": "checkout.session.completed"},
        payload_sha256="b" * 64,
        request_id="req-admin-detail",
        received_at=now,
        processed_at=now,
    )
    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.get_webhook_event",
        lambda self, *, session, stripe_event_id: (
            event if stripe_event_id == event.stripe_event_id else None
        ),
    )

    response = client.get(
        "/admin/payments/webhooks/evt_admin_detail_1",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["stripe_event_id"] == "evt_admin_detail_1"
    assert payload["payload"]["type"] == "checkout.session.completed"


def test_admin_webhook_replay_failed_event_safe(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-replay-{uuid4()}@example.com", "admin", bff_headers)

    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.replay_webhook_event",
        lambda self, *, session, stripe_event_id, request_id: StripeWebhookReplayResult(
            outcome="replayed",
            event_id=stripe_event_id,
            processing_status=WebhookProcessingStatus.PROCESSED,
            detail="webhook_event_replayed",
        ),
    )

    response = client.post(
        "/admin/payments/webhooks/evt_admin_replay_1/replay",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 200
    assert response.json() == {
        "stripe_event_id": "evt_admin_replay_1",
        "outcome": "replayed",
        "processing_status": "processed",
        "detail": "webhook_event_replayed",
    }


def test_admin_webhook_replay_processed_event_noop(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-noop-{uuid4()}@example.com", "admin", bff_headers)

    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.replay_webhook_event",
        lambda self, *, session, stripe_event_id, request_id: StripeWebhookReplayResult(
            outcome="noop",
            event_id=stripe_event_id,
            processing_status=WebhookProcessingStatus.PROCESSED,
            detail="webhook_event_already_terminal",
        ),
    )

    response = client.post(
        "/admin/payments/webhooks/evt_admin_noop_1/replay",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "noop"


def test_admin_webhook_list_db_unavailable_returns_503(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-list-db-{uuid4()}@example.com", "admin", bff_headers)

    def _raise_db_unavailable(
        self: object,
        *,
        session: object,
        limit: int,
        processing_status: object | None = None,
    ) -> list[StripeWebhookEvent]:
        raise StripeWebhookIngressError("db_unavailable")

    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.list_webhook_events",
        _raise_db_unavailable,
    )

    response = client.get(
        "/admin/payments/webhooks",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "db_unavailable"}


def test_admin_webhook_detail_not_found_returns_404(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-404-{uuid4()}@example.com", "admin", bff_headers)

    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.get_webhook_event",
        lambda self, *, session, stripe_event_id: None,
    )

    response = client.get(
        "/admin/payments/webhooks/evt_missing",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "webhook_event_not_found"}


def test_admin_webhook_replay_not_found_returns_404(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-webhook-r404-{uuid4()}@example.com", "admin", bff_headers)

    monkeypatch.setattr(
        "mealmetric.api.admin.StripeWebhookIngressService.replay_webhook_event",
        lambda self, *, session, stripe_event_id, request_id: StripeWebhookReplayResult(
            outcome="not_found",
            event_id=stripe_event_id,
            processing_status=None,
            detail="webhook_event_not_found",
        ),
    )

    response = client.post(
        "/admin/payments/webhooks/evt_missing/replay",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "webhook_event_not_found"}


def test_admin_reconciliation_run_returns_report(
    client: TestClient,
    signed_bff_headers: Callable[..., dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_payload = {
        "email": f"admin-reconcile-{uuid4()}@example.com",
        "password": "securepass1",
        "role": "admin",
    }
    register_headers = signed_bff_headers(
        method="POST",
        path_with_query="/auth/register",
        body=json.dumps(register_payload, separators=(",", ":")).encode("utf-8"),
    )
    token = _register(client, register_payload["email"], "admin", register_headers)
    now = datetime.now(UTC)
    monkeypatch.setattr(
        "mealmetric.api.admin.ReconciliationService.run",
        lambda self, *, stale_window_seconds=900: ReconciliationReport(
            generated_at=now,
            stale_window_seconds=stale_window_seconds,
            payment_sessions_missing_orders=(
                ReconciliationPaymentMismatch(
                    payment_session_id=uuid4(),
                    checkout_session_id="cs_missing_order_1",
                    payment_status=PaymentStatus.PAYMENT_INTENT_SUCCEEDED,
                ),
            ),
            webhook_processing_gaps=(
                ReconciliationWebhookMismatch(
                    stripe_event_id="evt_gap_1",
                    event_type="checkout.session.completed",
                    processing_status=WebhookProcessingStatus.FAILED,
                    received_at=now,
                    processing_error="event_processing_failed",
                ),
            ),
            subscriptions_missing_lifecycle_linkage=(
                ReconciliationSubscriptionMismatch(
                    subscription_id=uuid4(),
                    stripe_subscription_id="sub_missing_link_1",
                    status="active",
                ),
            ),
        ),
    )

    response = client.post(
        "/admin/payments/reconciliation/run",
        headers={
            "Authorization": f"Bearer {token}",
            **signed_bff_headers(
                method="POST",
                path_with_query="/admin/payments/reconciliation/run",
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["payment_sessions_missing_orders"][0]["checkout_session_id"] == "cs_missing_order_1"
    )
    assert payload["webhook_processing_gaps"][0]["stripe_event_id"] == "evt_gap_1"
    assert (
        payload["subscriptions_missing_lifecycle_linkage"][0]["stripe_subscription_id"]
        == "sub_missing_link_1"
    )
