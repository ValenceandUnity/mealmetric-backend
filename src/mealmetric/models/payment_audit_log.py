import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mealmetric.db.base import Base
from mealmetric.models.payment_session import PaymentStatus


class PaymentTransitionSource(StrEnum):
    CHECKOUT_API = "checkout_api"
    STRIPE_WEBHOOK = "stripe_webhook"
    SYSTEM = "system"


class PaymentAuditLog(Base):
    __tablename__ = "payment_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    from_payment_status: Mapped[PaymentStatus | None] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=True,
        index=True,
    )
    to_payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=False,
        index=True,
    )
    transition_source: Mapped[PaymentTransitionSource] = mapped_column(
        Enum(PaymentTransitionSource, name="payment_transition_source", native_enum=False),
        nullable=False,
        default=PaymentTransitionSource.SYSTEM,
        server_default=PaymentTransitionSource.SYSTEM.value,
        index=True,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
