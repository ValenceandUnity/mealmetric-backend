import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from mealmetric.models.order import Order
from mealmetric.models.payment_session import PaymentSession, PaymentStatus


def _query_by_id(payment_session_id: uuid.UUID) -> Select[tuple[PaymentSession]]:
    return select(PaymentSession).where(PaymentSession.id == payment_session_id)


def _query_by_checkout_session_id(checkout_session_id: str) -> Select[tuple[PaymentSession]]:
    return select(PaymentSession).where(
        PaymentSession.stripe_checkout_session_id == checkout_session_id
    )


def _query_by_payment_intent_id(payment_intent_id: str) -> Select[tuple[PaymentSession]]:
    return select(PaymentSession).where(
        PaymentSession.stripe_payment_intent_id == payment_intent_id
    )


def get_by_id(session: Session, payment_session_id: uuid.UUID) -> PaymentSession | None:
    return session.scalar(_query_by_id(payment_session_id))


def get_by_checkout_session_id(session: Session, checkout_session_id: str) -> PaymentSession | None:
    return session.scalar(_query_by_checkout_session_id(checkout_session_id))


def get_by_payment_intent_id(session: Session, payment_intent_id: str) -> PaymentSession | None:
    return session.scalar(_query_by_payment_intent_id(payment_intent_id))


def create_payment_session(
    session: Session,
    *,
    stripe_checkout_session_id: str,
    payment_status: PaymentStatus,
    user_id: uuid.UUID | None = None,
    stripe_price_id: str | None = None,
    stripe_payment_intent_id: str | None = None,
    basket_snapshot: dict[str, object] | None = None,
) -> PaymentSession:
    payment_session = PaymentSession(
        user_id=user_id,
        stripe_price_id=stripe_price_id,
        stripe_checkout_session_id=stripe_checkout_session_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        payment_status=payment_status,
        basket_snapshot=basket_snapshot,
    )
    session.add(payment_session)
    session.flush()
    return payment_session


def save_payment_session(session: Session, payment_session: PaymentSession) -> PaymentSession:
    session.add(payment_session)
    session.flush()
    return payment_session


def list_successful_without_order(
    session: Session,
    *,
    statuses: Sequence[PaymentStatus],
) -> list[PaymentSession]:
    stmt = (
        select(PaymentSession)
        .outerjoin(Order, Order.payment_session_id == PaymentSession.id)
        .where(PaymentSession.payment_status.in_(tuple(statuses)))
        .where(Order.id.is_(None))
        .order_by(PaymentSession.created_at.asc(), PaymentSession.id.asc())
    )
    return list(session.scalars(stmt))
