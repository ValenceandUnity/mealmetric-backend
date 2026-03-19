import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from mealmetric.models.payment_session import PaymentSession, PaymentStatus
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.models.subscription import MealPlanSubscription
from mealmetric.repos import payment_session_repo, stripe_webhook_event_repo, subscription_repo


@dataclass(frozen=True, slots=True)
class ReconciliationPaymentMismatch:
    payment_session_id: uuid.UUID
    checkout_session_id: str
    payment_status: PaymentStatus


@dataclass(frozen=True, slots=True)
class ReconciliationWebhookMismatch:
    stripe_event_id: str
    event_type: str
    processing_status: WebhookProcessingStatus
    received_at: datetime
    processing_error: str | None


@dataclass(frozen=True, slots=True)
class ReconciliationSubscriptionMismatch:
    subscription_id: uuid.UUID
    stripe_subscription_id: str
    status: str


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    generated_at: datetime
    stale_window_seconds: int
    payment_sessions_missing_orders: tuple[ReconciliationPaymentMismatch, ...]
    webhook_processing_gaps: tuple[ReconciliationWebhookMismatch, ...]
    subscriptions_missing_lifecycle_linkage: tuple[ReconciliationSubscriptionMismatch, ...]


class ReconciliationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def run(self, *, stale_window_seconds: int = 900) -> ReconciliationReport:
        generated_at = datetime.now(UTC)
        stale_before = generated_at - timedelta(seconds=stale_window_seconds)

        payments = payment_session_repo.list_successful_without_order(
            self._session,
            statuses=(
                PaymentStatus.CHECKOUT_SESSION_COMPLETED,
                PaymentStatus.PAYMENT_INTENT_SUCCEEDED,
            ),
        )
        webhooks = stripe_webhook_event_repo.list_failed_or_stale_events(
            self._session,
            stale_before=stale_before,
        )
        subscriptions = subscription_repo.list_missing_lifecycle_linkage(self._session)

        return ReconciliationReport(
            generated_at=generated_at,
            stale_window_seconds=stale_window_seconds,
            payment_sessions_missing_orders=tuple(
                self._to_payment_mismatch(item) for item in payments
            ),
            webhook_processing_gaps=tuple(self._to_webhook_mismatch(item) for item in webhooks),
            subscriptions_missing_lifecycle_linkage=tuple(
                self._to_subscription_mismatch(item) for item in subscriptions
            ),
        )

    @staticmethod
    def _to_payment_mismatch(item: PaymentSession) -> ReconciliationPaymentMismatch:
        return ReconciliationPaymentMismatch(
            payment_session_id=item.id,
            checkout_session_id=item.stripe_checkout_session_id,
            payment_status=item.payment_status,
        )

    @staticmethod
    def _to_webhook_mismatch(item: StripeWebhookEvent) -> ReconciliationWebhookMismatch:
        received_at = item.received_at
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=UTC)
        return ReconciliationWebhookMismatch(
            stripe_event_id=item.stripe_event_id,
            event_type=item.event_type,
            processing_status=item.processing_status,
            received_at=received_at,
            processing_error=item.processing_error,
        )

    @staticmethod
    def _to_subscription_mismatch(item: MealPlanSubscription) -> ReconciliationSubscriptionMismatch:
        return ReconciliationSubscriptionMismatch(
            subscription_id=item.id,
            stripe_subscription_id=item.stripe_subscription_id,
            status=item.status.value,
        )
