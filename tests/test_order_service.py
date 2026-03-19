import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.orm import Session

from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItem, OrderItemType
from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.repos.order_item_repo import OrderItemCreate
from mealmetric.services.order_service import OrderCreateResult, OrderCreationError, OrderService


class _FakeSession:
    pass


def _valid_basket_snapshot() -> dict[str, object]:
    return {
        "currency": "usd",
        "subtotal_amount_cents": 2000,
        "tax_amount_cents": 100,
        "total_amount_cents": 2100,
        "items": [
            {
                "item_type": "product",
                "external_price_id": "price_123",
                "description": "Starter plan",
                "quantity": 1,
                "unit_amount_cents": 2000,
                "subtotal_amount_cents": 2000,
                "tax_amount_cents": 100,
                "total_amount_cents": 2100,
            }
        ],
    }


def test_create_order_from_successful_payment_session_creates_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = cast(Session, _FakeSession())
    service = OrderService(session)
    payment_session_id = uuid.uuid4()
    client_user_id = uuid.uuid4()
    created_order_id = uuid.uuid4()
    captured_items: list[object] = []
    captured_order_kwargs: dict[str, object] = {}

    payment_session = PaymentSession(
        user_id=client_user_id,
        stripe_checkout_session_id="cs_1",
        stripe_payment_intent_id="pi_1",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        basket_snapshot=_valid_basket_snapshot(),
    )
    payment_session.id = payment_session_id

    monkeypatch.setattr(
        "mealmetric.services.order_service.payment_session_repo.get_by_id",
        lambda _session, target_id: payment_session if target_id == payment_session_id else None,
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.get_by_payment_session_id",
        lambda _session, _payment_session_id: None,
    )

    def _create_order(_session: Session, **kwargs: object) -> Order:
        captured_order_kwargs.update(kwargs)
        return Order(
            id=created_order_id,
            payment_session_id=uuid.UUID(str(kwargs["payment_session_id"])),
            client_user_id=uuid.UUID(str(kwargs["client_user_id"])),
            order_payment_status=OrderPaymentStatus.PAID,
            fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
            currency=str(kwargs["currency"]),
            subtotal_amount_cents=int(cast(int, kwargs["subtotal_amount_cents"])),
            tax_amount_cents=int(cast(int, kwargs["tax_amount_cents"])),
            total_amount_cents=int(cast(int, kwargs["total_amount_cents"])),
        )

    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.create_order",
        _create_order,
    )

    def _capture_items(
        _session: Session, *, order_id: uuid.UUID, items: list[object]
    ) -> list[OrderItem]:
        assert order_id == created_order_id
        captured_items.extend(items)
        return []

    monkeypatch.setattr(
        "mealmetric.services.order_service.order_item_repo.create_order_items",
        _capture_items,
    )

    result = service.create_order_from_successful_payment_session(
        payment_session_id=payment_session_id,
        trigger_event_type="checkout.session.completed",
        trigger_event_id="evt_1",
        request_id="req_1",
    )

    assert result == OrderCreateResult(outcome="created", order_id=created_order_id)
    assert captured_order_kwargs["client_user_id"] == client_user_id
    assert len(captured_items) == 1
    captured_item = cast(OrderItemCreate, captured_items[0])
    assert captured_item.item_type == OrderItemType.PRODUCT
    assert captured_item.external_price_id == "price_123"
    assert captured_item.description == "Starter plan"
    assert captured_item.quantity == 1
    assert captured_item.unit_amount_cents == 2000
    assert captured_item.subtotal_amount_cents == 2000
    assert captured_item.tax_amount_cents == 100
    assert captured_item.total_amount_cents == 2100


def test_create_order_from_successful_payment_session_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = cast(Session, _FakeSession())
    service = OrderService(session)
    payment_session_id = uuid.uuid4()
    existing_order_id = uuid.uuid4()
    client_user_id = uuid.uuid4()

    payment_session = PaymentSession(
        user_id=client_user_id,
        stripe_checkout_session_id="cs_dup",
        stripe_payment_intent_id="pi_dup",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        basket_snapshot=_valid_basket_snapshot(),
    )
    payment_session.id = payment_session_id

    monkeypatch.setattr(
        "mealmetric.services.order_service.payment_session_repo.get_by_id",
        lambda _session, target_id: payment_session if target_id == payment_session_id else None,
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.get_by_payment_session_id",
        lambda _session, _payment_session_id: Order(
            id=existing_order_id,
            payment_session_id=payment_session_id,
            client_user_id=client_user_id,
            order_payment_status=OrderPaymentStatus.PAID,
            fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
            currency="usd",
            subtotal_amount_cents=2000,
            tax_amount_cents=100,
            total_amount_cents=2100,
        ),
    )

    result = service.create_order_from_successful_payment_session(
        payment_session_id=payment_session_id,
        trigger_event_type="checkout.session.completed",
        trigger_event_id="evt_dup",
        request_id="req_dup",
    )

    assert result == OrderCreateResult(outcome="duplicate_skipped", order_id=existing_order_id)


def test_create_order_requires_successful_payment_status(monkeypatch: pytest.MonkeyPatch) -> None:
    session = cast(Session, _FakeSession())
    service = OrderService(session)
    payment_session_id = uuid.uuid4()

    payment_session = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_fail",
        stripe_payment_intent_id="pi_fail",
        payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
        basket_snapshot=_valid_basket_snapshot(),
    )
    payment_session.id = payment_session_id

    monkeypatch.setattr(
        "mealmetric.services.order_service.payment_session_repo.get_by_id",
        lambda _session, _target_id: payment_session,
    )
    create_called = {"value": False}

    def _unexpected_create_order(*_args: object, **_kwargs: object) -> Order:
        create_called["value"] = True
        raise AssertionError("create_order should not be called for unsuccessful payments")

    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.create_order",
        _unexpected_create_order,
    )

    with pytest.raises(OrderCreationError, match="payment_not_successful"):
        service.create_order_from_successful_payment_session(
            payment_session_id=payment_session_id,
            trigger_event_type="checkout.session.completed",
            trigger_event_id="evt_fail",
            request_id="req_fail",
        )
    assert create_called["value"] is False


def test_create_order_requires_basket_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    session = cast(Session, _FakeSession())
    service = OrderService(session)
    payment_session_id = uuid.uuid4()

    payment_session = PaymentSession(
        user_id=uuid.uuid4(),
        stripe_checkout_session_id="cs_no_basket",
        stripe_payment_intent_id="pi_no_basket",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        basket_snapshot=None,
    )
    payment_session.id = payment_session_id

    monkeypatch.setattr(
        "mealmetric.services.order_service.payment_session_repo.get_by_id",
        lambda _session, _target_id: payment_session,
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.get_by_payment_session_id",
        lambda _session, _payment_session_id: None,
    )

    with pytest.raises(OrderCreationError, match="basket_snapshot_missing"):
        service.create_order_from_successful_payment_session(
            payment_session_id=payment_session_id,
            trigger_event_type="checkout.session.completed",
            trigger_event_id="evt_no_basket",
            request_id="req_no_basket",
        )


def test_create_order_requires_payment_session_user(monkeypatch: pytest.MonkeyPatch) -> None:
    session = cast(Session, _FakeSession())
    service = OrderService(session)
    payment_session_id = uuid.uuid4()

    payment_session = PaymentSession(
        user_id=None,
        stripe_checkout_session_id="cs_no_user",
        stripe_payment_intent_id="pi_no_user",
        payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        basket_snapshot=_valid_basket_snapshot(),
    )
    payment_session.id = payment_session_id

    monkeypatch.setattr(
        "mealmetric.services.order_service.payment_session_repo.get_by_id",
        lambda _session, _target_id: payment_session,
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.get_by_payment_session_id",
        lambda _session, _payment_session_id: None,
    )

    with pytest.raises(OrderCreationError, match="payment_session_user_missing"):
        service.create_order_from_successful_payment_session(
            payment_session_id=payment_session_id,
            trigger_event_type="checkout.session.completed",
            trigger_event_id="evt_no_user",
            request_id="req_no_user",
        )


def test_admin_read_and_list_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    session = cast(Session, _FakeSession())
    service = OrderService(session)
    order_id = uuid.uuid4()
    payment_session_id = uuid.uuid4()
    client_user_id = uuid.uuid4()

    order = Order(
        id=order_id,
        payment_session_id=payment_session_id,
        client_user_id=client_user_id,
        order_payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
        currency="usd",
        subtotal_amount_cents=1200,
        tax_amount_cents=0,
        total_amount_cents=1200,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    item = OrderItem(
        order_id=order_id,
        item_type=OrderItemType.PRODUCT,
        quantity=1,
        unit_amount_cents=1200,
        subtotal_amount_cents=1200,
        tax_amount_cents=0,
        total_amount_cents=1200,
    )

    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.get_by_id",
        lambda _session, target_id: order if target_id == order_id else None,
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.get_by_payment_session_id",
        lambda _session, target_id: order if target_id == payment_session_id else None,
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_repo.list_orders",
        lambda _session, **kwargs: [order],
    )
    monkeypatch.setattr(
        "mealmetric.services.order_service.order_item_repo.get_by_order_id",
        lambda _session, target_order_id: [item] if target_order_id == order_id else [],
    )

    by_id = service.get_order_by_id(order_id=order_id)
    assert by_id is not None
    assert by_id.order.id == order_id
    assert by_id.order.client_user_id == client_user_id
    assert len(by_id.items) == 1

    by_payment_session = service.get_order_by_payment_session_id(
        payment_session_id=payment_session_id
    )
    assert by_payment_session is not None
    assert by_payment_session.order.payment_session_id == payment_session_id

    listed = service.list_orders_for_admin(limit=10)
    assert len(listed) == 1
    assert listed[0].order.id == order_id
    assert listed[0].items[0].order_id == order_id
