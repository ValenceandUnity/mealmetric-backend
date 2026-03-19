import hashlib
import hmac
import importlib
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast
from urllib.parse import parse_qs

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.core.observability import (
    ORDER_CREATION_WEBHOOK_FAILURE_TOTAL,
    PAYMENT_LIFECYCLE_TRANSITIONS_TOTAL,
    STRIPE_WEBHOOK_PROCESSED_TOTAL,
    STRIPE_WEBHOOK_PROCESSING_SECONDS,
    STRIPE_WEBHOOK_RECEIVED_TOTAL,
)
from mealmetric.core.settings import Settings
from mealmetric.models.payment_audit_log import PaymentTransitionSource
from mealmetric.models.payment_session import PaymentStatus
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.repos import payment_audit_log_repo, payment_session_repo, stripe_webhook_event_repo
from mealmetric.services.order_service import OrderCreationError, OrderService
from mealmetric.services.subscription_service import SubscriptionService, SubscriptionSyncError

logger = logging.getLogger("mealmetric.webhooks.stripe")
_MAX_FAILURE_ERROR_CHARS = 1000

_STATUS_RANK: dict[PaymentStatus, int] = {
    PaymentStatus.CHECKOUT_SESSION_CREATED: 10,
    PaymentStatus.CHECKOUT_SESSION_COMPLETED: 20,
    PaymentStatus.PAYMENT_INTENT_FAILED: 30,
    PaymentStatus.PAYMENT_INTENT_SUCCEEDED: 40,
}

try:
    _stripe_module: Any | None = importlib.import_module("stripe")
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    _stripe_module = None


def _require_stripe() -> Any:
    if _stripe_module is None:
        raise StripeWebhookIngressError("stripe_sdk_not_installed")
    return _stripe_module


class StripeWebhookIngressError(Exception):
    """Raised when Stripe webhook ingress validation fails."""


class StripeEventLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def type(self) -> str: ...


@dataclass(frozen=True)
class StripeWebhookIngressResult:
    duplicate: bool
    mode: str
    event_id: str


@dataclass(frozen=True)
class EventProcessingOutcome:
    status: WebhookProcessingStatus
    payment_session_id: uuid.UUID | None
    note: str | None = None


@dataclass(frozen=True)
class StripeWebhookReplayResult:
    outcome: Literal["replayed", "noop", "failed", "not_found"]
    event_id: str
    processing_status: WebhookProcessingStatus | None
    detail: str


class StripeWebhookIngressService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stripe = _stripe_module

    def verify_and_parse_event(self, *, payload: bytes, signature: str) -> StripeEventLike:
        secret = self._settings.stripe_webhook_secret
        if not secret:
            raise StripeWebhookIngressError("webhook_secret_not_configured")

        if self._stripe is not None:
            try:
                event = self._stripe.Webhook.construct_event(
                    payload=payload,
                    sig_header=signature,
                    secret=secret,
                )
            except (ValueError, self._stripe.SignatureVerificationError) as exc:
                raise StripeWebhookIngressError("invalid_stripe_signature") from exc
        else:
            event = self._construct_event_without_sdk(
                payload=payload, signature=signature, secret=secret
            )

        if self._settings.stripe_api_version is not None:
            event_api_version = getattr(event, "api_version", None)
            if event_api_version != self._settings.stripe_api_version:
                raise StripeWebhookIngressError("unexpected_stripe_api_version")

        return cast(StripeEventLike, event)

    def ingest_event(
        self,
        *,
        session: Session | None,
        event: StripeEventLike,
        payload: bytes,
        request_id: str,
    ) -> StripeWebhookIngressResult:
        if session is None:
            raise StripeWebhookIngressError("db_unavailable")

        event_id = getattr(event, "id", None)
        event_type = getattr(event, "type", None)
        if not isinstance(event_id, str) or not event_id:
            raise StripeWebhookIngressError("invalid_event_id")
        if not isinstance(event_type, str) or not event_type:
            raise StripeWebhookIngressError("invalid_event_type")

        STRIPE_WEBHOOK_RECEIVED_TOTAL.labels(event_type=event_type).inc()

        existing = stripe_webhook_event_repo.get_by_stripe_event_id(session, event_id)
        if existing is not None:
            if (
                self._settings.stripe_webhook_mode == "process"
                and existing.processing_status == WebhookProcessingStatus.FAILED
            ):
                self._reprocess_failed_existing_event(
                    session=session,
                    webhook_event=existing,
                    request_id=request_id,
                )
                return StripeWebhookIngressResult(
                    duplicate=True,
                    mode=self._settings.stripe_webhook_mode,
                    event_id=event_id,
                )

            logger.info(
                "stripe webhook duplicate delivery",
                extra={"request_id": request_id, "event_id": event_id, "event_type": event_type},
            )
            STRIPE_WEBHOOK_PROCESSED_TOTAL.labels(event_type=event_type, status="duplicate").inc()
            return StripeWebhookIngressResult(
                duplicate=True,
                mode=self._settings.stripe_webhook_mode,
                event_id=event_id,
            )

        payload_dict = self._parse_payload(payload)
        payload_sha256 = hashlib.sha256(payload).hexdigest()

        try:
            stripe_webhook_event_repo.create_event_receipt(
                session,
                stripe_event_id=event_id,
                event_type=event_type,
                payload=payload_dict,
                payload_sha256=payload_sha256,
                request_id=request_id,
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            logger.info(
                "stripe webhook duplicate detected by unique constraint",
                extra={"request_id": request_id, "event_id": event_id, "event_type": event_type},
            )
            STRIPE_WEBHOOK_PROCESSED_TOTAL.labels(event_type=event_type, status="duplicate").inc()
            return StripeWebhookIngressResult(
                duplicate=True,
                mode=self._settings.stripe_webhook_mode,
                event_id=event_id,
            )
        except Exception:
            session.rollback()
            raise

        if self._settings.stripe_webhook_mode == "process":
            self._process_persisted_event(
                session=session,
                stripe_event_id=event_id,
                event_type=event_type,
                payload=payload_dict,
                request_id=request_id,
            )
        else:
            STRIPE_WEBHOOK_PROCESSED_TOTAL.labels(
                event_type=event_type, status="received_only"
            ).inc()

        logger.info(
            "stripe webhook receipt persisted",
            extra={
                "request_id": request_id,
                "event_id": event_id,
                "event_type": event_type,
                "mode": self._settings.stripe_webhook_mode,
            },
        )
        return StripeWebhookIngressResult(
            duplicate=False,
            mode=self._settings.stripe_webhook_mode,
            event_id=event_id,
        )

    def mark_processing(
        self,
        *,
        session: Session | None,
        stripe_event_id: str,
        request_id: str,
    ) -> StripeWebhookEvent | None:
        return self._set_status(
            session=session,
            stripe_event_id=stripe_event_id,
            status=WebhookProcessingStatus.PROCESSING,
            request_id=request_id,
        )

    def mark_processed(
        self,
        *,
        session: Session | None,
        stripe_event_id: str,
        request_id: str,
    ) -> StripeWebhookEvent | None:
        return self._set_status(
            session=session,
            stripe_event_id=stripe_event_id,
            status=WebhookProcessingStatus.PROCESSED,
            request_id=request_id,
        )

    def mark_failed(
        self,
        *,
        session: Session | None,
        stripe_event_id: str,
        error: str,
        request_id: str,
    ) -> StripeWebhookEvent | None:
        safe_error = error.strip()[:_MAX_FAILURE_ERROR_CHARS] if error.strip() else "unknown_error"
        return self._set_status(
            session=session,
            stripe_event_id=stripe_event_id,
            status=WebhookProcessingStatus.FAILED,
            processing_error=safe_error,
            request_id=request_id,
        )

    def list_webhook_events(
        self,
        *,
        session: Session | None,
        limit: int,
        processing_status: WebhookProcessingStatus | None = None,
    ) -> list[StripeWebhookEvent]:
        if session is None:
            raise StripeWebhookIngressError("db_unavailable")
        safe_limit = min(max(limit, 1), 200)
        return stripe_webhook_event_repo.list_events(
            session,
            limit=safe_limit,
            processing_status=processing_status,
        )

    def get_webhook_event(
        self,
        *,
        session: Session | None,
        stripe_event_id: str,
    ) -> StripeWebhookEvent | None:
        if session is None:
            raise StripeWebhookIngressError("db_unavailable")
        return stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)

    def replay_webhook_event(
        self,
        *,
        session: Session | None,
        stripe_event_id: str,
        request_id: str,
    ) -> StripeWebhookReplayResult:
        if session is None:
            raise StripeWebhookIngressError("db_unavailable")

        webhook_event = stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)
        if webhook_event is None:
            return StripeWebhookReplayResult(
                outcome="not_found",
                event_id=stripe_event_id,
                processing_status=None,
                detail="webhook_event_not_found",
            )

        if webhook_event.processing_status in {
            WebhookProcessingStatus.PROCESSED,
            WebhookProcessingStatus.IGNORED,
        }:
            return StripeWebhookReplayResult(
                outcome="noop",
                event_id=webhook_event.stripe_event_id,
                processing_status=webhook_event.processing_status,
                detail="webhook_event_already_terminal",
            )

        try:
            self._process_persisted_event(
                session=session,
                stripe_event_id=webhook_event.stripe_event_id,
                event_type=webhook_event.event_type,
                payload=webhook_event.payload,
                request_id=request_id,
            )
        except StripeWebhookIngressError:
            failed = stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)
            return StripeWebhookReplayResult(
                outcome="failed",
                event_id=stripe_event_id,
                processing_status=failed.processing_status if failed is not None else None,
                detail="webhook_event_replay_failed",
            )

        updated = stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)
        return StripeWebhookReplayResult(
            outcome="replayed",
            event_id=stripe_event_id,
            processing_status=updated.processing_status if updated is not None else None,
            detail="webhook_event_replayed",
        )

    def _process_persisted_event(
        self,
        *,
        session: Session,
        stripe_event_id: str,
        event_type: str,
        payload: dict[str, object],
        request_id: str,
    ) -> None:
        webhook_event = stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)
        if webhook_event is None:
            raise StripeWebhookIngressError("webhook_event_not_found")

        started_at = time.perf_counter()
        try:
            logger.info(
                "stripe webhook processing started",
                extra={
                    "request_id": request_id,
                    "event_id": stripe_event_id,
                    "event_type": event_type,
                },
            )
            stripe_webhook_event_repo.set_processing_status(
                session,
                webhook_event,
                status=WebhookProcessingStatus.PROCESSING,
            )

            if event_type == "checkout.session.completed":
                outcome = self._handle_checkout_session_completed(
                    session=session,
                    stripe_event_id=stripe_event_id,
                    payload=payload,
                    request_id=request_id,
                )
            elif event_type == "payment_intent.succeeded":
                outcome = self._handle_payment_intent_event(
                    session=session,
                    stripe_event_id=stripe_event_id,
                    payload=payload,
                    target_status=PaymentStatus.PAYMENT_INTENT_SUCCEEDED,
                )
            elif event_type == "payment_intent.payment_failed":
                outcome = self._handle_payment_intent_event(
                    session=session,
                    stripe_event_id=stripe_event_id,
                    payload=payload,
                    target_status=PaymentStatus.PAYMENT_INTENT_FAILED,
                )
            elif event_type in {
                "customer.subscription.created",
                "customer.subscription.updated",
                "customer.subscription.deleted",
                "invoice.paid",
                "invoice.payment_failed",
            }:
                outcome = self._handle_subscription_event(
                    session=session,
                    stripe_event_id=stripe_event_id,
                    event_type=event_type,
                    payload=payload,
                    request_id=request_id,
                )
            else:
                outcome = EventProcessingOutcome(
                    status=WebhookProcessingStatus.IGNORED,
                    payment_session_id=None,
                    note="unsupported_event_type",
                )

            if outcome.payment_session_id is not None:
                webhook_event.payment_session_id = outcome.payment_session_id

            stripe_webhook_event_repo.set_processing_status(
                session,
                webhook_event,
                status=outcome.status,
                processing_error=(
                    outcome.note if outcome.status == WebhookProcessingStatus.IGNORED else None
                ),
            )
            session.commit()
            status_label = outcome.status.value
            duration = time.perf_counter() - started_at
            STRIPE_WEBHOOK_PROCESSED_TOTAL.labels(event_type=event_type, status=status_label).inc()
            STRIPE_WEBHOOK_PROCESSING_SECONDS.labels(
                event_type=event_type,
                status=status_label,
            ).observe(duration)
            logger.info(
                "stripe webhook processing completed",
                extra={
                    "request_id": request_id,
                    "event_id": stripe_event_id,
                    "event_type": event_type,
                    "status": status_label,
                },
            )
        except Exception as exc:
            session.rollback()
            error_message = str(exc)
            if event_type == "checkout.session.completed" and isinstance(exc, OrderCreationError):
                ORDER_CREATION_WEBHOOK_FAILURE_TOTAL.inc()
                error_message = f"order_creation_failed:{exc}"
            self._record_processing_failure(
                session=session,
                stripe_event_id=stripe_event_id,
                request_id=request_id,
                error_message=error_message,
            )
            duration = time.perf_counter() - started_at
            STRIPE_WEBHOOK_PROCESSED_TOTAL.labels(event_type=event_type, status="failed").inc()
            STRIPE_WEBHOOK_PROCESSING_SECONDS.labels(
                event_type=event_type,
                status="failed",
            ).observe(duration)
            raise StripeWebhookIngressError("event_processing_failed") from exc

    def _handle_checkout_session_completed(
        self,
        *,
        session: Session,
        stripe_event_id: str,
        payload: dict[str, object],
        request_id: str,
    ) -> EventProcessingOutcome:
        obj = self._event_object(payload)
        checkout_session_id = self._required_str(obj.get("id"), "checkout_session_id")
        payment_intent_id = self._optional_object_id(obj.get("payment_intent"))

        payment_session = payment_session_repo.get_by_checkout_session_id(
            session, checkout_session_id
        )
        if payment_session is None:
            return EventProcessingOutcome(
                status=WebhookProcessingStatus.IGNORED,
                payment_session_id=None,
                note="payment_session_not_seeded",
            )

        changed = False
        if (
            payment_intent_id is not None
            and payment_session.stripe_payment_intent_id != payment_intent_id
        ):
            payment_session.stripe_payment_intent_id = payment_intent_id
            changed = True

        if self._should_transition(
            current=payment_session.payment_status,
            target=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
        ):
            old_status = payment_session.payment_status
            payment_session.payment_status = PaymentStatus.CHECKOUT_SESSION_COMPLETED
            self._append_transition(
                session=session,
                payment_session_id=payment_session.id,
                stripe_event_id=stripe_event_id,
                from_payment_status=old_status,
                to_payment_status=PaymentStatus.CHECKOUT_SESSION_COMPLETED,
                transition_source=PaymentTransitionSource.STRIPE_WEBHOOK,
                message="applied_checkout_session_completed_webhook",
            )
            changed = True

        if changed:
            payment_session_repo.save_payment_session(session, payment_session)

        self._attempt_order_creation_for_checkout_completion(
            session=session,
            payment_session_id=payment_session.id,
            stripe_event_id=stripe_event_id,
            request_id=request_id,
        )

        return EventProcessingOutcome(
            status=WebhookProcessingStatus.PROCESSED,
            payment_session_id=payment_session.id,
        )

    def _handle_payment_intent_event(
        self,
        *,
        session: Session,
        stripe_event_id: str,
        payload: dict[str, object],
        target_status: PaymentStatus,
    ) -> EventProcessingOutcome:
        obj = self._event_object(payload)
        payment_intent_id = self._required_str(obj.get("id"), "payment_intent_id")

        payment_session = payment_session_repo.get_by_payment_intent_id(session, payment_intent_id)
        if payment_session is None:
            # Keep a durable event record and mark ignored so later reconciliation can re-link it.
            return EventProcessingOutcome(
                status=WebhookProcessingStatus.IGNORED,
                payment_session_id=None,
                note="payment_session_not_found_for_payment_intent",
            )

        if self._should_transition(current=payment_session.payment_status, target=target_status):
            old_status = payment_session.payment_status
            payment_session.payment_status = target_status
            payment_session_repo.save_payment_session(session, payment_session)
            self._append_transition(
                session=session,
                payment_session_id=payment_session.id,
                stripe_event_id=stripe_event_id,
                from_payment_status=old_status,
                to_payment_status=target_status,
                transition_source=PaymentTransitionSource.STRIPE_WEBHOOK,
                message=f"applied_{target_status.value}_webhook",
            )

        return EventProcessingOutcome(
            status=WebhookProcessingStatus.PROCESSED,
            payment_session_id=payment_session.id,
        )

    def _attempt_order_creation_for_checkout_completion(
        self,
        *,
        session: Session,
        payment_session_id: uuid.UUID,
        stripe_event_id: str,
        request_id: str,
    ) -> str:
        order_service = OrderService(session)
        result = order_service.create_order_from_successful_payment_session(
            payment_session_id=payment_session_id,
            trigger_event_type="checkout.session.completed",
            trigger_event_id=stripe_event_id,
            request_id=request_id,
        )
        logger.info(
            "order creation orchestration finished",
            extra={
                "request_id": request_id,
                "event_id": stripe_event_id,
                "payment_session_id": str(payment_session_id),
                "order_creation_outcome": result.outcome,
                "order_id": str(result.order_id),
            },
        )
        return result.outcome

    def _handle_subscription_event(
        self,
        *,
        session: Session,
        stripe_event_id: str,
        event_type: str,
        payload: dict[str, object],
        request_id: str,
    ) -> EventProcessingOutcome:
        service = SubscriptionService(session)
        try:
            result = service.apply_stripe_event(
                stripe_event_id=stripe_event_id,
                event_type=event_type,
                payload=payload,
                request_id=request_id,
            )
        except SubscriptionSyncError as exc:
            raise StripeWebhookIngressError(str(exc)) from exc

        if result.outcome == "ignored":
            return EventProcessingOutcome(
                status=WebhookProcessingStatus.IGNORED,
                payment_session_id=None,
                note=result.note,
            )
        return EventProcessingOutcome(
            status=WebhookProcessingStatus.PROCESSED,
            payment_session_id=None,
        )

    def _reprocess_failed_existing_event(
        self,
        *,
        session: Session,
        webhook_event: StripeWebhookEvent,
        request_id: str,
    ) -> None:
        logger.info(
            "retrying previously failed webhook event",
            extra={
                "request_id": request_id,
                "event_id": webhook_event.stripe_event_id,
                "event_type": webhook_event.event_type,
            },
        )
        self._process_persisted_event(
            session=session,
            stripe_event_id=webhook_event.stripe_event_id,
            event_type=webhook_event.event_type,
            payload=webhook_event.payload,
            request_id=request_id,
        )

    def _set_status(
        self,
        *,
        session: Session | None,
        stripe_event_id: str,
        status: WebhookProcessingStatus,
        request_id: str,
        processing_error: str | None = None,
    ) -> StripeWebhookEvent | None:
        if session is None:
            raise StripeWebhookIngressError("db_unavailable")

        event = stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)
        if event is None:
            return None

        updated_event = stripe_webhook_event_repo.set_processing_status(
            session,
            event,
            status=status,
            processing_error=processing_error,
        )
        session.commit()
        logger.info(
            "stripe webhook status updated",
            extra={
                "request_id": request_id,
                "event_id": stripe_event_id,
                "status": status.value,
            },
        )
        return updated_event

    def _record_processing_failure(
        self,
        *,
        session: Session,
        stripe_event_id: str,
        request_id: str,
        error_message: str,
    ) -> None:
        safe_error = error_message.strip()[:_MAX_FAILURE_ERROR_CHARS] or "unknown_error"
        try:
            event = stripe_webhook_event_repo.get_by_stripe_event_id(session, stripe_event_id)
            if event is None:
                return
            stripe_webhook_event_repo.set_processing_status(
                session,
                event,
                status=WebhookProcessingStatus.FAILED,
                processing_error=safe_error,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "failed to record webhook processing failure",
                extra={"request_id": request_id, "event_id": stripe_event_id},
            )

    def _append_transition(
        self,
        *,
        session: Session,
        payment_session_id: uuid.UUID,
        stripe_event_id: str | None,
        from_payment_status: PaymentStatus | None,
        to_payment_status: PaymentStatus,
        transition_source: PaymentTransitionSource,
        message: str | None = None,
    ) -> None:
        payment_audit_log_repo.append_transition(
            session,
            payment_session_id=payment_session_id,
            stripe_event_id=stripe_event_id,
            from_payment_status=from_payment_status,
            to_payment_status=to_payment_status,
            transition_source=transition_source,
            message=message,
        )
        from_status = from_payment_status.value if from_payment_status is not None else "none"
        PAYMENT_LIFECYCLE_TRANSITIONS_TOTAL.labels(
            from_status=from_status,
            to_status=to_payment_status.value,
            source=transition_source.value,
        ).inc()

    @staticmethod
    def _parse_payload(payload: bytes) -> dict[str, object]:
        decoded = payload.decode("utf-8")
        parsed = json.loads(decoded)
        if not isinstance(parsed, Mapping):
            raise StripeWebhookIngressError("invalid_event_payload")
        return dict(parsed)

    @staticmethod
    def _event_object(payload: dict[str, object]) -> dict[str, object]:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise StripeWebhookIngressError("invalid_event_payload")
        obj = data.get("object")
        if not isinstance(obj, Mapping):
            raise StripeWebhookIngressError("invalid_event_payload")
        return dict(obj)

    @staticmethod
    def _required_str(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise StripeWebhookIngressError(f"missing_or_invalid_{field_name}")
        return value

    @staticmethod
    def _optional_object_id(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and value:
            return value
        if isinstance(value, Mapping):
            id_value = value.get("id")
            if isinstance(id_value, str) and id_value:
                return id_value
        return None

    @staticmethod
    def _should_transition(*, current: PaymentStatus, target: PaymentStatus) -> bool:
        return _STATUS_RANK[target] > _STATUS_RANK[current]

    @staticmethod
    def _construct_event_without_sdk(
        *,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> StripeEventLike:
        timestamp, expected_signature = StripeWebhookIngressService._parse_signature_header(
            signature
        )
        signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode()
        actual_signature = hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise StripeWebhookIngressError("invalid_stripe_signature")

        try:
            parsed = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise StripeWebhookIngressError("invalid_stripe_signature") from exc

        if not isinstance(parsed, Mapping):
            raise StripeWebhookIngressError("invalid_stripe_signature")

        event_id = parsed.get("id")
        event_type = parsed.get("type")
        if not isinstance(event_id, str) or not isinstance(event_type, str):
            raise StripeWebhookIngressError("invalid_stripe_signature")

        return cast(
            StripeEventLike,
            _FallbackStripeEvent(
                id=event_id,
                type=event_type,
                api_version=parsed.get("api_version"),
            ),
        )

    @staticmethod
    def _parse_signature_header(signature: str) -> tuple[str, str]:
        parsed = parse_qs(signature.replace(",", "&"), keep_blank_values=True)
        timestamps = parsed.get("t")
        signatures = parsed.get("v1")
        if not timestamps or not signatures:
            raise StripeWebhookIngressError("invalid_stripe_signature")
        timestamp = timestamps[0]
        signed_digest = signatures[0]
        if not timestamp or not signed_digest:
            raise StripeWebhookIngressError("invalid_stripe_signature")
        return timestamp, signed_digest


@dataclass(frozen=True)
class _FallbackStripeEvent:
    id: str
    type: str
    api_version: object | None = None
