import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from mealmetric.models.order_item import OrderItem, OrderItemType


@dataclass(frozen=True, slots=True)
class OrderItemCreate:
    quantity: int
    unit_amount_cents: int
    subtotal_amount_cents: int
    tax_amount_cents: int
    total_amount_cents: int
    item_type: OrderItemType = OrderItemType.PRODUCT
    external_price_id: str | None = None
    description: str | None = None


def _query_by_order_id(order_id: uuid.UUID) -> Select[tuple[OrderItem]]:
    return select(OrderItem).where(OrderItem.order_id == order_id)


def create_order_items(
    session: Session,
    *,
    order_id: uuid.UUID,
    items: Sequence[OrderItemCreate],
) -> list[OrderItem]:
    order_items = [
        OrderItem(
            order_id=order_id,
            item_type=item.item_type,
            external_price_id=item.external_price_id,
            description=item.description,
            quantity=item.quantity,
            unit_amount_cents=item.unit_amount_cents,
            subtotal_amount_cents=item.subtotal_amount_cents,
            tax_amount_cents=item.tax_amount_cents,
            total_amount_cents=item.total_amount_cents,
        )
        for item in items
    ]
    session.add_all(order_items)
    session.flush()
    return order_items


def get_by_order_id(session: Session, order_id: uuid.UUID) -> list[OrderItem]:
    statement = _query_by_order_id(order_id)
    return list(session.scalars(statement))
