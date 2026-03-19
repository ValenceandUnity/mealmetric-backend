import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base

if TYPE_CHECKING:
    from mealmetric.models.order import Order


class OrderItemType(StrEnum):
    PRODUCT = "product"
    ADJUSTMENT = "adjustment"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[OrderItemType] = mapped_column(
        Enum(OrderItemType, name="order_item_type", native_enum=False),
        nullable=False,
        default=OrderItemType.PRODUCT,
        server_default=OrderItemType.PRODUCT.value,
        index=True,
    )
    external_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    order: Mapped["Order"] = relationship("Order", back_populates="items")
