from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mealmetric.db.session import get_db
from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItem, OrderItemType
from mealmetric.services.order_service import OrderWithItems


def _register(client: TestClient, email: str, role: str, bff_headers: dict[str, str]) -> str:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "securepass1", "role": role},
        headers=bff_headers,
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _sample_order_with_items() -> OrderWithItems:
    now = datetime.now(UTC)
    client_user_id = uuid4()
    order = Order(
        id=uuid4(),
        payment_session_id=uuid4(),
        client_user_id=client_user_id,
        order_payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
        currency="usd",
        subtotal_amount_cents=2500,
        tax_amount_cents=200,
        total_amount_cents=2700,
        created_at=now,
        updated_at=now,
    )
    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        item_type=OrderItemType.PRODUCT,
        external_price_id="price_abc",
        description="Meal Plan",
        quantity=1,
        unit_amount_cents=2500,
        subtotal_amount_cents=2500,
        tax_amount_cents=200,
        total_amount_cents=2700,
        created_at=now,
    )
    return OrderWithItems(order=order, items=[item])


def test_admin_orders_requires_auth(client: TestClient) -> None:
    response = client.get("/admin/orders")
    assert response.status_code == 401


def test_admin_orders_requires_trusted_caller(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    token = _register(client, f"admin-orders-bff-{uuid4()}@example.com", "admin", bff_headers)
    response = client.get("/admin/orders", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_admin_orders_forbidden_for_non_admin(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    token = _register(client, f"client-orders-{uuid4()}@example.com", "client", bff_headers)
    response = client.get(
        "/admin/orders",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )
    assert response.status_code == 403


def test_admin_orders_list_returns_orders(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-orders-list-{uuid4()}@example.com", "admin", bff_headers)
    sample = _sample_order_with_items()

    monkeypatch.setattr(
        "mealmetric.api.admin_orders.OrderService.list_orders_for_admin",
        lambda self, **kwargs: [sample],
    )

    response = client.get(
        "/admin/orders?limit=25&offset=0",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == str(sample.order.id)
    assert payload["items"][0]["client_user_id"] == str(sample.order.client_user_id)
    assert payload["items"][0]["items"][0]["id"] == str(sample.items[0].id)


def test_admin_order_detail_returns_404_when_missing(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-order-detail-{uuid4()}@example.com", "admin", bff_headers)

    monkeypatch.setattr(
        "mealmetric.api.admin_orders.OrderService.get_order_by_id",
        lambda self, *, order_id: None,
    )

    response = client.get(
        f"/admin/orders/{uuid4()}",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "order_not_found"}


def test_admin_order_by_payment_session_returns_order(
    client: TestClient,
    bff_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _register(client, f"admin-order-payment-{uuid4()}@example.com", "admin", bff_headers)
    sample = _sample_order_with_items()

    monkeypatch.setattr(
        "mealmetric.api.admin_orders.OrderService.get_order_by_payment_session_id",
        lambda self, *, payment_session_id: sample,
    )

    response = client.get(
        f"/admin/payment-sessions/{sample.order.payment_session_id}/order",
        headers={"Authorization": f"Bearer {token}", **bff_headers},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["payment_session_id"] == str(sample.order.payment_session_id)
    assert payload["client_user_id"] == str(sample.order.client_user_id)
    assert payload["items"][0]["external_price_id"] == "price_abc"


def test_admin_orders_db_unavailable_returns_503(
    client: TestClient,
    bff_headers: dict[str, str],
) -> None:
    token = _register(client, f"admin-order-db-{uuid4()}@example.com", "admin", bff_headers)

    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.get(
            "/admin/orders",
            headers={"Authorization": f"Bearer {token}", **bff_headers},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "db_unavailable"}
