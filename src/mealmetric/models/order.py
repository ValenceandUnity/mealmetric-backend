import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base

if TYPE_CHECKING:
    from mealmetric.models.order_item import OrderItem
    from mealmetric.models.payment_session import PaymentSession


class OrderPaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class OrderFulfillmentStatus(StrEnum):
    UNFULFILLED = "unfulfilled"
    FULFILLED = "fulfilled"
    CANCELED = "canceled"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("payment_session_id", name="uq_orders_payment_session_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_payment_status: Mapped[OrderPaymentStatus] = mapped_column(
        Enum(OrderPaymentStatus, name="order_payment_status", native_enum=False),
        nullable=False,
        default=OrderPaymentStatus.PENDING,
        server_default=OrderPaymentStatus.PENDING.value,
        index=True,
    )
    fulfillment_status: Mapped[OrderFulfillmentStatus] = mapped_column(
        Enum(OrderFulfillmentStatus, name="order_fulfillment_status", native_enum=False),
        nullable=False,
        default=OrderFulfillmentStatus.UNFULFILLED,
        server_default=OrderFulfillmentStatus.UNFULFILLED.value,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    payment_session: Mapped["PaymentSession"] = relationship(
        "PaymentSession", back_populates="order"
    )
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )
