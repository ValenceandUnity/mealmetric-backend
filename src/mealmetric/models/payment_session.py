import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base

if TYPE_CHECKING:
    from mealmetric.models.order import Order


class PaymentStatus(StrEnum):
    CHECKOUT_SESSION_CREATED = "checkout_session_created"
    CHECKOUT_SESSION_COMPLETED = "checkout_session_completed"
    PAYMENT_INTENT_SUCCEEDED = "payment_intent_succeeded"
    PAYMENT_INTENT_FAILED = "payment_intent_failed"


class PaymentSession(Base):
    __tablename__ = "payment_sessions"
    __table_args__ = (
        UniqueConstraint(
            "stripe_checkout_session_id", name="uq_payment_sessions_stripe_checkout_session_id"
        ),
        UniqueConstraint(
            "stripe_payment_intent_id", name="uq_payment_sessions_stripe_payment_intent_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stripe_checkout_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=False,
        default=PaymentStatus.CHECKOUT_SESSION_CREATED,
        server_default=PaymentStatus.CHECKOUT_SESSION_CREATED.value,
        index=True,
    )
    basket_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    order: Mapped["Order | None"] = relationship(
        "Order", back_populates="payment_session", uselist=False
    )
