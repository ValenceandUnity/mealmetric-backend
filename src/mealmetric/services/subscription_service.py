import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from mealmetric.models.subscription import (
    MealPlanSubscription,
    MealPlanSubscriptionStatus,
    SubscriptionBillingInterval,
    SubscriptionInvoiceStatus,
)
from mealmetric.repos import subscription_repo, user_repo, vendor_repo

logger = logging.getLogger("mealmetric.subscriptions")


class SubscriptionSyncError(Exception):
    """Raised when Stripe subscription data cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class SubscriptionMealPlanSummaryView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    id: uuid.UUID
    stripe_subscription_id: str
    stripe_customer_id: str | None
    client_user_id: uuid.UUID
    meal_plan_id: uuid.UUID
    status: MealPlanSubscriptionStatus
    billing_interval: SubscriptionBillingInterval
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    latest_invoice_id: str | None
    latest_invoice_status: SubscriptionInvoiceStatus | None
    latest_stripe_event_id: str | None
    last_invoice_paid_at: datetime | None
    last_invoice_failed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    meal_plan: SubscriptionMealPlanSummaryView | None


@dataclass(frozen=True, slots=True)
class SubscriptionListView:
    items: tuple[SubscriptionView, ...]
    count: int


@dataclass(frozen=True, slots=True)
class SubscriptionSyncResult:
    outcome: str
    subscription_id: uuid.UUID | None
    note: str | None = None


class SubscriptionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def apply_stripe_event(
        self,
        *,
        stripe_event_id: str,
        event_type: str,
        payload: dict[str, object],
        request_id: str,
    ) -> SubscriptionSyncResult:
        obj = self._event_object(payload)
        if event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            result = self._apply_subscription_object(
                stripe_event_id=stripe_event_id,
                event_type=event_type,
                obj=obj,
                request_id=request_id,
            )
        elif event_type in {"invoice.paid", "invoice.payment_failed"}:
            result = self._apply_invoice_object(
                stripe_event_id=stripe_event_id,
                event_type=event_type,
                obj=obj,
                request_id=request_id,
            )
        else:
            raise SubscriptionSyncError("unsupported_subscription_event_type")

        if result.subscription_id is not None:
            logger.info(
                "subscription state synchronized",
                extra={
                    "request_id": request_id,
                    "event_id": stripe_event_id,
                    "event_type": event_type,
                    "subscription_id": str(result.subscription_id),
                    "sync_outcome": result.outcome,
                },
            )
        return result

    def list_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        limit: int,
        offset: int = 0,
    ) -> SubscriptionListView:
        subscriptions = subscription_repo.list_for_client(
            self._session,
            client_user_id=client_user_id,
            limit=limit,
            offset=offset,
        )
        items = tuple(self._to_view(item) for item in subscriptions)
        return SubscriptionListView(items=items, count=len(items))

    def list_for_admin(
        self,
        *,
        limit: int,
        offset: int = 0,
        client_user_id: uuid.UUID | None = None,
        status: MealPlanSubscriptionStatus | None = None,
    ) -> SubscriptionListView:
        subscriptions = subscription_repo.list_for_admin(
            self._session,
            limit=limit,
            offset=offset,
            client_user_id=client_user_id,
            status=status,
        )
        items = tuple(self._to_view(item) for item in subscriptions)
        return SubscriptionListView(items=items, count=len(items))

    def _apply_subscription_object(
        self,
        *,
        stripe_event_id: str,
        event_type: str,
        obj: dict[str, object],
        request_id: str,
    ) -> SubscriptionSyncResult:
        stripe_subscription_id = self._required_str(obj.get("id"), "stripe_subscription_id")
        subscription = subscription_repo.get_by_stripe_subscription_id(
            self._session,
            stripe_subscription_id,
        )
        if subscription is None:
            identifiers = self._extract_identifiers(obj.get("metadata"))
            if identifiers is None:
                return SubscriptionSyncResult(
                    outcome="ignored",
                    subscription_id=None,
                    note="subscription_metadata_missing",
                )
            client_user_id, meal_plan_id = identifiers
            if user_repo.get_by_id(self._session, client_user_id) is None:
                return SubscriptionSyncResult(
                    outcome="ignored",
                    subscription_id=None,
                    note="subscription_client_not_found",
                )
            if (
                vendor_repo.get_meal_plan_by_id_for_update(self._session, meal_plan_id=meal_plan_id)
                is None
            ):
                return SubscriptionSyncResult(
                    outcome="ignored",
                    subscription_id=None,
                    note="subscription_meal_plan_not_found",
                )
            subscription = subscription_repo.create_subscription(
                self._session,
                stripe_subscription_id=stripe_subscription_id,
                stripe_customer_id=self._optional_object_id(obj.get("customer")),
                client_user_id=client_user_id,
                meal_plan_id=meal_plan_id,
                status=self._coerce_subscription_status(obj.get("status")),
            )
            outcome = "created"
        else:
            outcome = "updated"

        subscription.stripe_customer_id = self._optional_object_id(obj.get("customer"))
        subscription.status = (
            MealPlanSubscriptionStatus.CANCELED
            if event_type == "customer.subscription.deleted"
            else self._coerce_subscription_status(obj.get("status"))
        )
        subscription.billing_interval = self._extract_billing_interval(obj)
        subscription.current_period_start = self._parse_timestamp(obj.get("current_period_start"))
        subscription.current_period_end = self._parse_timestamp(obj.get("current_period_end"))
        subscription.cancel_at_period_end = self._coerce_bool(obj.get("cancel_at_period_end"))
        subscription.canceled_at = self._parse_timestamp(obj.get("canceled_at"))
        subscription.latest_stripe_event_id = stripe_event_id
        subscription_repo.save_subscription(self._session, subscription)
        logger.info(
            "subscription lifecycle updated",
            extra={
                "request_id": request_id,
                "event_id": stripe_event_id,
                "stripe_subscription_id": stripe_subscription_id,
                "lifecycle_event_type": event_type,
            },
        )
        return SubscriptionSyncResult(
            outcome=outcome,
            subscription_id=subscription.id,
        )

    def _apply_invoice_object(
        self,
        *,
        stripe_event_id: str,
        event_type: str,
        obj: dict[str, object],
        request_id: str,
    ) -> SubscriptionSyncResult:
        stripe_subscription_id = self._optional_object_id(obj.get("subscription"))
        if stripe_subscription_id is None:
            return SubscriptionSyncResult(
                outcome="ignored",
                subscription_id=None,
                note="invoice_subscription_missing",
            )

        subscription = subscription_repo.get_by_stripe_subscription_id(
            self._session,
            stripe_subscription_id,
        )
        if subscription is None:
            return SubscriptionSyncResult(
                outcome="ignored",
                subscription_id=None,
                note="subscription_not_found_for_invoice",
            )

        subscription.stripe_customer_id = self._optional_object_id(obj.get("customer"))
        subscription.latest_invoice_id = self._required_str(obj.get("id"), "invoice_id")
        subscription.latest_stripe_event_id = stripe_event_id
        invoice_period = self._extract_invoice_period(obj)
        if invoice_period is not None:
            subscription.current_period_start, subscription.current_period_end = invoice_period

        if event_type == "invoice.paid":
            subscription.latest_invoice_status = SubscriptionInvoiceStatus.PAID
            if subscription.status != MealPlanSubscriptionStatus.CANCELED:
                subscription.status = MealPlanSubscriptionStatus.ACTIVE
            subscription.last_invoice_paid_at = self._parse_timestamp(
                self._status_transitions_value(obj.get("status_transitions"), "paid_at")
            ) or self._parse_timestamp(obj.get("created"))
        else:
            subscription.latest_invoice_status = SubscriptionInvoiceStatus.PAYMENT_FAILED
            if subscription.status != MealPlanSubscriptionStatus.CANCELED:
                subscription.status = MealPlanSubscriptionStatus.PAST_DUE
            subscription.last_invoice_failed_at = self._parse_timestamp(obj.get("created"))

        subscription_repo.save_subscription(self._session, subscription)
        logger.warning(
            "subscription invoice lifecycle updated",
            extra={
                "request_id": request_id,
                "event_id": stripe_event_id,
                "event_type": event_type,
                "subscription_id": str(subscription.id),
                "stripe_subscription_id": stripe_subscription_id,
            },
        )
        return SubscriptionSyncResult(outcome="updated", subscription_id=subscription.id)

    def _to_view(self, subscription: MealPlanSubscription) -> SubscriptionView:
        meal_plan = subscription.meal_plan
        meal_plan_view = (
            SubscriptionMealPlanSummaryView(
                id=meal_plan.id,
                vendor_id=meal_plan.vendor_id,
                slug=meal_plan.slug,
                name=meal_plan.name,
            )
            if meal_plan is not None
            else None
        )
        return SubscriptionView(
            id=subscription.id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            stripe_customer_id=subscription.stripe_customer_id,
            client_user_id=subscription.client_user_id,
            meal_plan_id=subscription.meal_plan_id,
            status=subscription.status,
            billing_interval=subscription.billing_interval,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            canceled_at=subscription.canceled_at,
            latest_invoice_id=subscription.latest_invoice_id,
            latest_invoice_status=subscription.latest_invoice_status,
            latest_stripe_event_id=subscription.latest_stripe_event_id,
            last_invoice_paid_at=subscription.last_invoice_paid_at,
            last_invoice_failed_at=subscription.last_invoice_failed_at,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
            meal_plan=meal_plan_view,
        )

    @staticmethod
    def _event_object(payload: dict[str, object]) -> dict[str, object]:
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise SubscriptionSyncError("invalid_subscription_payload")
        obj = data.get("object")
        if not isinstance(obj, Mapping):
            raise SubscriptionSyncError("invalid_subscription_payload")
        return dict(obj)

    @staticmethod
    def _required_str(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise SubscriptionSyncError(f"missing_or_invalid_{field_name}")
        return value

    @staticmethod
    def _optional_object_id(value: object) -> str | None:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, Mapping):
            id_value = value.get("id")
            if isinstance(id_value, str) and id_value:
                return id_value
        return None

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        return value if isinstance(value, bool) else False

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return datetime.fromtimestamp(value, tz=UTC)

    @staticmethod
    def _extract_identifiers(value: object) -> tuple[uuid.UUID, uuid.UUID] | None:
        if not isinstance(value, Mapping):
            return None
        client_raw = value.get("client_user_id")
        meal_plan_raw = value.get("meal_plan_id")
        if not isinstance(client_raw, str) or not isinstance(meal_plan_raw, str):
            return None
        try:
            return uuid.UUID(client_raw), uuid.UUID(meal_plan_raw)
        except ValueError:
            return None

    @staticmethod
    def _coerce_subscription_status(value: object) -> MealPlanSubscriptionStatus:
        if not isinstance(value, str):
            return MealPlanSubscriptionStatus.INCOMPLETE
        try:
            return MealPlanSubscriptionStatus(value)
        except ValueError:
            return MealPlanSubscriptionStatus.INCOMPLETE

    @staticmethod
    def _extract_billing_interval(obj: dict[str, object]) -> SubscriptionBillingInterval:
        items = obj.get("items")
        if not isinstance(items, Mapping):
            return SubscriptionBillingInterval.UNKNOWN
        data = items.get("data")
        if not isinstance(data, list) or not data:
            return SubscriptionBillingInterval.UNKNOWN
        first_item = data[0]
        if not isinstance(first_item, Mapping):
            return SubscriptionBillingInterval.UNKNOWN
        price = first_item.get("price")
        if not isinstance(price, Mapping):
            return SubscriptionBillingInterval.UNKNOWN
        recurring = price.get("recurring")
        if not isinstance(recurring, Mapping):
            return SubscriptionBillingInterval.UNKNOWN
        interval = recurring.get("interval")
        if not isinstance(interval, str):
            return SubscriptionBillingInterval.UNKNOWN
        try:
            return SubscriptionBillingInterval(interval)
        except ValueError:
            return SubscriptionBillingInterval.UNKNOWN

    @classmethod
    def _extract_invoice_period(
        cls,
        obj: dict[str, object],
    ) -> tuple[datetime, datetime] | None:
        lines = obj.get("lines")
        if not isinstance(lines, Mapping):
            return None
        data = lines.get("data")
        if not isinstance(data, list):
            return None
        for raw_line in data:
            if not isinstance(raw_line, Mapping):
                continue
            period = raw_line.get("period")
            if not isinstance(period, Mapping):
                continue
            start = cls._parse_timestamp(period.get("start"))
            end = cls._parse_timestamp(period.get("end"))
            if start is not None and end is not None:
                return start, end
        return None

    @staticmethod
    def _status_transitions_value(value: object, field_name: str) -> object | None:
        if not isinstance(value, Mapping):
            return None
        return value.get(field_name)
