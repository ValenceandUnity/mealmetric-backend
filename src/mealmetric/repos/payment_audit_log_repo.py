import uuid

from sqlalchemy.orm import Session

from mealmetric.models.payment_audit_log import PaymentAuditLog, PaymentTransitionSource
from mealmetric.models.payment_session import PaymentStatus


def append_transition(
    session: Session,
    *,
    payment_session_id: uuid.UUID,
    stripe_event_id: str | None,
    from_payment_status: PaymentStatus | None,
    to_payment_status: PaymentStatus,
    transition_source: PaymentTransitionSource,
    message: str | None = None,
) -> PaymentAuditLog:
    audit_row = PaymentAuditLog(
        payment_session_id=payment_session_id,
        stripe_event_id=stripe_event_id,
        from_payment_status=from_payment_status,
        to_payment_status=to_payment_status,
        transition_source=transition_source,
        message=message,
    )
    session.add(audit_row)
    session.flush()
    return audit_row
