import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.order import Order
from mealmetric.models.payment_session import PaymentStatus
from mealmetric.models.user import User
from mealmetric.repos import order_item_repo
from mealmetric.repos.payment_session_repo import create_payment_session
from mealmetric.services.order_service import OrderCreationError, OrderService


def _basket_snapshot() -> dict[str, object]:
    return {
        "currency": "usd",
        "subtotal_amount_cents": 1000,
        "tax_amount_cents": 0,
        "total_amount_cents": 1000,
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
    }


def test_order_creation_rolls_back_when_order_items_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

    with session_local() as db:
        user = User(email="tx-rollback@example.com", password_hash="hash")
        db.add(user)
        db.flush()

        payment_session = create_payment_session(
            db,
            user_id=user.id,
            stripe_checkout_session_id="cs_tx_rollback",
            payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
            stripe_payment_intent_id="pi_tx_rollback",
            basket_snapshot=_basket_snapshot(),
        )
        db.commit()

        def _raise_on_items(
            _session: Session,
            *,
            order_id: uuid.UUID,
            items: list[order_item_repo.OrderItemCreate],
        ) -> list[object]:
            _ = order_id
            _ = items
            raise RuntimeError("simulated_order_items_failure")

        monkeypatch.setattr(order_item_repo, "create_order_items", _raise_on_items)

        service = OrderService(db)
        with pytest.raises(OrderCreationError, match="order_persist_failed"):
            service.create_order_from_successful_payment_session(
                payment_session_id=payment_session.id,
                trigger_event_type="checkout.session.completed",
                trigger_event_id="evt_tx_rollback",
                request_id="req_tx_rollback",
            )
        db.rollback()

        order = db.scalar(select(Order).where(Order.payment_session_id == payment_session.id))
        assert order is None
