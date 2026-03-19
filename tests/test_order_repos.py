import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItem, OrderItemType
from mealmetric.models.payment_session import PaymentStatus
from mealmetric.models.user import User
from mealmetric.repos import order_item_repo, order_repo
from mealmetric.repos.order_item_repo import OrderItemCreate
from mealmetric.repos.payment_session_repo import create_payment_session


class _FakeSession:
    def __init__(self) -> None:
        self.scalar_result: object | None = None
        self.scalars_result: list[object] = []
        self.last_scalar_stmt: object | None = None
        self.last_scalars_stmt: object | None = None
        self.added: list[object] = []
        self.added_all: list[object] = []
        self.flush_count = 0

    def scalar(self, stmt: object) -> object | None:
        self.last_scalar_stmt = stmt
        return self.scalar_result

    def scalars(self, stmt: object) -> list[object]:
        self.last_scalars_stmt = stmt
        return self.scalars_result

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def add_all(self, objs: list[object]) -> None:
        self.added_all.extend(objs)

    def flush(self) -> None:
        self.flush_count += 1


def test_create_order_persists_and_flushes() -> None:
    session = _FakeSession()
    payment_session_id = uuid.uuid4()
    client_user_id = uuid.uuid4()

    created = order_repo.create_order(
        cast(Session, session),
        payment_session_id=payment_session_id,
        client_user_id=client_user_id,
        currency="usd",
        subtotal_amount_cents=1000,
        tax_amount_cents=80,
        total_amount_cents=1080,
    )

    assert created.payment_session_id == payment_session_id
    assert created.client_user_id == client_user_id
    assert created.order_payment_status == OrderPaymentStatus.PENDING
    assert created.fulfillment_status == OrderFulfillmentStatus.UNFULFILLED
    assert created.currency == "usd"
    assert created.subtotal_amount_cents == 1000
    assert created.tax_amount_cents == 80
    assert created.total_amount_cents == 1080
    assert session.added[-1] is created
    assert session.flush_count == 1


def test_get_order_queries() -> None:
    session = _FakeSession()
    expected = Order(
        payment_session_id=uuid.uuid4(),
        client_user_id=uuid.uuid4(),
        order_payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
        currency="usd",
        subtotal_amount_cents=100,
        tax_amount_cents=0,
        total_amount_cents=100,
    )
    session.scalar_result = expected

    by_id = order_repo.get_by_id(cast(Session, session), uuid.uuid4())
    assert by_id is expected
    assert session.last_scalar_stmt is not None

    by_payment_session_id = order_repo.get_by_payment_session_id(
        cast(Session, session), uuid.uuid4()
    )
    assert by_payment_session_id is expected
    assert session.last_scalar_stmt is not None


def test_list_orders_with_admin_filters() -> None:
    session = _FakeSession()
    user_id = uuid.uuid4()
    order = Order(
        payment_session_id=uuid.uuid4(),
        client_user_id=user_id,
        order_payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=OrderFulfillmentStatus.FULFILLED,
        currency="usd",
        subtotal_amount_cents=100,
        tax_amount_cents=0,
        total_amount_cents=100,
    )
    session.scalars_result = [order]

    created_from = datetime(2026, 3, 1, tzinfo=UTC)
    created_to = datetime(2026, 3, 15, tzinfo=UTC)

    result = order_repo.list_orders(
        cast(Session, session),
        limit=25,
        offset=10,
        payment_session_id=uuid.uuid4(),
        user_id=user_id,
        order_payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=OrderFulfillmentStatus.FULFILLED,
        created_from=created_from,
        created_to=created_to,
    )

    assert result == [order]
    assert session.last_scalars_stmt is not None
    statement_text = str(cast(Any, session.last_scalars_stmt))
    assert "orders.client_user_id" in statement_text
    assert "order_payment_status" in statement_text
    assert "fulfillment_status" in statement_text
    assert "created_at" in statement_text


def test_create_order_items_bulk_insert() -> None:
    session = _FakeSession()
    order_id = uuid.uuid4()

    created = order_item_repo.create_order_items(
        cast(Session, session),
        order_id=order_id,
        items=[
            OrderItemCreate(
                item_type=OrderItemType.PRODUCT,
                external_price_id="price_1",
                description="Meal Plan",
                quantity=2,
                unit_amount_cents=500,
                subtotal_amount_cents=1000,
                tax_amount_cents=0,
                total_amount_cents=1000,
            ),
            OrderItemCreate(
                item_type=OrderItemType.ADJUSTMENT,
                description="Promo",
                quantity=1,
                unit_amount_cents=-100,
                subtotal_amount_cents=-100,
                tax_amount_cents=0,
                total_amount_cents=-100,
            ),
        ],
    )

    assert len(created) == 2
    assert all(item.order_id == order_id for item in created)
    assert len(session.added_all) == 2
    assert session.flush_count == 1


def test_get_order_items_by_order_id() -> None:
    session = _FakeSession()
    expected = OrderItem(
        order_id=uuid.uuid4(),
        item_type=OrderItemType.PRODUCT,
        quantity=1,
        unit_amount_cents=100,
        subtotal_amount_cents=100,
        tax_amount_cents=0,
        total_amount_cents=100,
    )
    session.scalars_result = [expected]

    result = order_item_repo.get_by_order_id(cast(Session, session), uuid.uuid4())

    assert result == [expected]
    assert session.last_scalars_stmt is not None


def test_unique_payment_session_linkage_enforced() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

    with session_local() as db:
        user = User(email="unique-link@example.com", password_hash="hash")
        db.add(user)
        db.flush()

        payment_session = create_payment_session(
            db,
            user_id=user.id,
            stripe_checkout_session_id="cs_unique_order_link",
            payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
            stripe_payment_intent_id="pi_unique_order_link",
            basket_snapshot={
                "currency": "usd",
                "items": [
                    {
                        "item_type": "product",
                        "quantity": 1,
                        "unit_amount_cents": 1000,
                        "subtotal_amount_cents": 1000,
                        "tax_amount_cents": 0,
                        "total_amount_cents": 1000,
                    }
                ],
            },
        )

        order_repo.create_order(
            db,
            payment_session_id=payment_session.id,
            client_user_id=user.id,
            currency="usd",
            subtotal_amount_cents=1000,
            tax_amount_cents=0,
            total_amount_cents=1000,
            order_payment_status=OrderPaymentStatus.PAID,
            fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
        )
        db.commit()

        with pytest.raises(IntegrityError):
            order_repo.create_order(
                db,
                payment_session_id=payment_session.id,
                client_user_id=user.id,
                currency="usd",
                subtotal_amount_cents=1000,
                tax_amount_cents=0,
                total_amount_cents=1000,
                order_payment_status=OrderPaymentStatus.PAID,
                fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
            )
            db.commit()
        db.rollback()
