import uuid
from datetime import datetime

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session, selectinload

from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus


def _query_by_id(order_id: uuid.UUID) -> Select[tuple[Order]]:
    return select(Order).where(Order.id == order_id)


def _query_by_payment_session_id(payment_session_id: uuid.UUID) -> Select[tuple[Order]]:
    return select(Order).where(Order.payment_session_id == payment_session_id)


def create_order(
    session: Session,
    *,
    payment_session_id: uuid.UUID,
    client_user_id: uuid.UUID,
    currency: str,
    subtotal_amount_cents: int,
    tax_amount_cents: int,
    total_amount_cents: int,
    order_payment_status: OrderPaymentStatus = OrderPaymentStatus.PENDING,
    fulfillment_status: OrderFulfillmentStatus = OrderFulfillmentStatus.UNFULFILLED,
) -> Order:
    order = Order(
        payment_session_id=payment_session_id,
        client_user_id=client_user_id,
        order_payment_status=order_payment_status,
        fulfillment_status=fulfillment_status,
        currency=currency,
        subtotal_amount_cents=subtotal_amount_cents,
        tax_amount_cents=tax_amount_cents,
        total_amount_cents=total_amount_cents,
    )
    session.add(order)
    session.flush()
    return order


def get_by_id(session: Session, order_id: uuid.UUID) -> Order | None:
    return session.scalar(_query_by_id(order_id))


def get_by_payment_session_id(session: Session, payment_session_id: uuid.UUID) -> Order | None:
    return session.scalar(_query_by_payment_session_id(payment_session_id))


def list_orders(
    session: Session,
    *,
    limit: int,
    offset: int = 0,
    payment_session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    order_payment_status: OrderPaymentStatus | None = None,
    fulfillment_status: OrderFulfillmentStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[Order]:
    statement: Select[tuple[Order]] = select(Order)

    if user_id is not None:
        statement = statement.where(Order.client_user_id == user_id)

    if payment_session_id is not None:
        statement = statement.where(Order.payment_session_id == payment_session_id)
    if order_payment_status is not None:
        statement = statement.where(Order.order_payment_status == order_payment_status)
    if fulfillment_status is not None:
        statement = statement.where(Order.fulfillment_status == fulfillment_status)
    if created_from is not None:
        statement = statement.where(Order.created_at >= created_from)
    if created_to is not None:
        statement = statement.where(Order.created_at <= created_to)

    statement = statement.order_by(desc(Order.created_at)).offset(offset).limit(limit)
    return list(session.scalars(statement))


def list_orders_for_client(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    limit: int,
    offset: int = 0,
) -> list[Order]:
    statement: Select[tuple[Order]] = (
        select(Order)
        .options(selectinload(Order.payment_session))
        .where(Order.client_user_id == client_user_id)
        .order_by(desc(Order.created_at), desc(Order.id))
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement))
