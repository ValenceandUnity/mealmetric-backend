import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from mealmetric.core.observability import (
    ORDER_CREATED_TOTAL,
    ORDER_CREATION_FAILED_TOTAL,
    ORDER_DUPLICATE_SKIPPED_TOTAL,
)
from mealmetric.models.order import Order, OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.order_item import OrderItem, OrderItemType
from mealmetric.models.payment_session import PaymentStatus
from mealmetric.models.recommendation import MealPlanRecommendation, MealPlanRecommendationStatus
from mealmetric.models.vendor import (
    MealPlan,
    MealPlanStatus,
    VendorPickupWindow,
    VendorPickupWindowStatus,
)
from mealmetric.repos import (
    order_item_repo,
    order_repo,
    payment_session_repo,
    recommendation_repo,
    vendor_repo,
)
from mealmetric.repos.order_item_repo import OrderItemCreate

logger = logging.getLogger("mealmetric.orders")


class OrderCreationError(Exception):
    """Raised when order creation preconditions are not met."""


@dataclass(frozen=True, slots=True)
class OrderCreateResult:
    outcome: Literal["created", "duplicate_skipped"]
    order_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class OrderWithItems:
    order: Order
    items: list[OrderItem]


@dataclass(frozen=True, slots=True)
class ClientOrderMealPlanSummaryView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: MealPlanStatus
    total_price_cents: int
    total_calories: int
    item_count: int
    availability_count: int


@dataclass(frozen=True, slots=True)
class ClientOrderPickupWindowView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    label: str | None
    status: VendorPickupWindowStatus
    pickup_start_at: datetime
    pickup_end_at: datetime
    order_cutoff_at: datetime | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class ClientOrderRecommendationView:
    id: uuid.UUID
    pt_user_id: uuid.UUID
    client_user_id: uuid.UUID
    meal_plan_id: uuid.UUID
    status: MealPlanRecommendationStatus
    rationale: str | None
    recommended_at: datetime
    expires_at: datetime | None
    is_expired: bool


@dataclass(frozen=True, slots=True)
class ClientOrderItemView:
    id: uuid.UUID
    item_type: OrderItemType
    external_price_id: str | None
    description: str | None
    quantity: int
    unit_amount_cents: int
    subtotal_amount_cents: int
    tax_amount_cents: int
    total_amount_cents: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ClientOrderView:
    id: uuid.UUID
    payment_session_id: uuid.UUID
    client_user_id: uuid.UUID
    order_payment_status: OrderPaymentStatus
    fulfillment_status: OrderFulfillmentStatus
    currency: str
    subtotal_amount_cents: int
    tax_amount_cents: int
    total_amount_cents: int
    created_at: datetime
    updated_at: datetime
    meal_plan_context_type: Literal["direct_or_assigned", "pt_recommended"]
    meal_plan: ClientOrderMealPlanSummaryView | None
    pickup_window: ClientOrderPickupWindowView | None
    pt_recommendation: ClientOrderRecommendationView | None
    items: tuple[ClientOrderItemView, ...]


@dataclass(frozen=True, slots=True)
class ClientOrderListView:
    items: tuple[ClientOrderView, ...]
    count: int


@dataclass(frozen=True, slots=True)
class _ParsedOrderSnapshot:
    meal_plan_id: uuid.UUID | None
    pickup_window_id: uuid.UUID | None
    recommendation_id: uuid.UUID | None


class OrderService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_order_from_successful_payment_session(
        self,
        *,
        payment_session_id: uuid.UUID,
        trigger_event_type: str,
        trigger_event_id: str | None,
        request_id: str,
    ) -> OrderCreateResult:
        payment_session = payment_session_repo.get_by_id(self._session, payment_session_id)
        if payment_session is None:
            self._record_creation_failure(
                reason="payment_session_not_found",
                payment_session_id=payment_session_id,
                trigger_event_type=trigger_event_type,
                trigger_event_id=trigger_event_id,
                request_id=request_id,
            )
            raise OrderCreationError("payment_session_not_found")

        if payment_session.payment_status not in {
            PaymentStatus.CHECKOUT_SESSION_COMPLETED,
            PaymentStatus.PAYMENT_INTENT_SUCCEEDED,
        }:
            self._record_creation_failure(
                reason="payment_not_successful",
                payment_session_id=payment_session_id,
                trigger_event_type=trigger_event_type,
                trigger_event_id=trigger_event_id,
                request_id=request_id,
            )
            raise OrderCreationError("payment_not_successful")

        existing_order = order_repo.get_by_payment_session_id(self._session, payment_session_id)
        if existing_order is not None:
            ORDER_DUPLICATE_SKIPPED_TOTAL.inc()
            logger.info(
                "order creation skipped; order already exists",
                extra={
                    "request_id": request_id,
                    "payment_session_id": str(payment_session_id),
                    "order_id": str(existing_order.id),
                    "trigger_event_type": trigger_event_type,
                    "trigger_event_id": trigger_event_id,
                },
            )
            return OrderCreateResult(outcome="duplicate_skipped", order_id=existing_order.id)

        if payment_session.user_id is None:
            self._record_creation_failure(
                reason="payment_session_user_missing",
                payment_session_id=payment_session_id,
                trigger_event_type=trigger_event_type,
                trigger_event_id=trigger_event_id,
                request_id=request_id,
            )
            raise OrderCreationError("payment_session_user_missing")

        basket_snapshot = payment_session.basket_snapshot
        if not isinstance(basket_snapshot, Mapping):
            self._record_creation_failure(
                reason="basket_snapshot_missing",
                payment_session_id=payment_session_id,
                trigger_event_type=trigger_event_type,
                trigger_event_id=trigger_event_id,
                request_id=request_id,
            )
            raise OrderCreationError("basket_snapshot_missing")

        try:
            currency, subtotal_amount_cents, tax_amount_cents, total_amount_cents, item_creates = (
                self._parse_basket_snapshot(dict(basket_snapshot))
            )
            order = order_repo.create_order(
                self._session,
                payment_session_id=payment_session_id,
                client_user_id=payment_session.user_id,
                currency=currency,
                subtotal_amount_cents=subtotal_amount_cents,
                tax_amount_cents=tax_amount_cents,
                total_amount_cents=total_amount_cents,
                order_payment_status=OrderPaymentStatus.PAID,
                fulfillment_status=OrderFulfillmentStatus.UNFULFILLED,
            )
            order_item_repo.create_order_items(
                self._session,
                order_id=order.id,
                items=item_creates,
            )
        except OrderCreationError:
            self._record_creation_failure(
                reason="invalid_basket_snapshot",
                payment_session_id=payment_session_id,
                trigger_event_type=trigger_event_type,
                trigger_event_id=trigger_event_id,
                request_id=request_id,
            )
            raise
        except Exception as exc:
            self._record_creation_failure(
                reason="order_persist_failed",
                payment_session_id=payment_session_id,
                trigger_event_type=trigger_event_type,
                trigger_event_id=trigger_event_id,
                request_id=request_id,
            )
            raise OrderCreationError("order_persist_failed") from exc

        ORDER_CREATED_TOTAL.inc()
        logger.info(
            "order created from payment session",
            extra={
                "request_id": request_id,
                "payment_session_id": str(payment_session_id),
                "order_id": str(order.id),
                "trigger_event_type": trigger_event_type,
                "trigger_event_id": trigger_event_id,
            },
        )
        return OrderCreateResult(outcome="created", order_id=order.id)

    def get_order_by_id(self, *, order_id: uuid.UUID) -> OrderWithItems | None:
        order = order_repo.get_by_id(self._session, order_id)
        if order is None:
            return None
        items = order_item_repo.get_by_order_id(self._session, order.id)
        return OrderWithItems(order=order, items=items)

    def get_order_by_payment_session_id(
        self,
        *,
        payment_session_id: uuid.UUID,
    ) -> OrderWithItems | None:
        order = order_repo.get_by_payment_session_id(self._session, payment_session_id)
        if order is None:
            return None
        items = order_item_repo.get_by_order_id(self._session, order.id)
        return OrderWithItems(order=order, items=items)

    def list_orders_for_admin(
        self,
        *,
        limit: int,
        offset: int = 0,
        payment_session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        order_payment_status: OrderPaymentStatus | None = None,
        fulfillment_status: OrderFulfillmentStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[OrderWithItems]:
        orders = order_repo.list_orders(
            self._session,
            limit=limit,
            offset=offset,
            payment_session_id=payment_session_id,
            user_id=user_id,
            order_payment_status=order_payment_status,
            fulfillment_status=fulfillment_status,
            created_from=created_from,
            created_to=created_to,
        )
        return [
            OrderWithItems(
                order=order,
                items=order_item_repo.get_by_order_id(self._session, order.id),
            )
            for order in orders
        ]

    def list_orders_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        limit: int,
        offset: int = 0,
    ) -> ClientOrderListView:
        orders = order_repo.list_orders_for_client(
            self._session,
            client_user_id=client_user_id,
            limit=limit,
            offset=offset,
        )
        items = tuple(self._to_client_order_view(order) for order in orders)
        return ClientOrderListView(items=items, count=len(items))

    def list_upcoming_pickups_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        limit: int,
        offset: int = 0,
        now: datetime | None = None,
    ) -> ClientOrderListView:
        reference_time = now or datetime.now(UTC)
        orders = order_repo.list_orders_for_client(
            self._session,
            client_user_id=client_user_id,
            limit=max(limit + offset, limit),
            offset=0,
        )
        upcoming = [
            self._to_client_order_view(order)
            for order in orders
            if self._is_upcoming_pickup(order=order, reference_time=reference_time)
        ]
        sliced = tuple(upcoming[offset : offset + limit])
        return ClientOrderListView(items=sliced, count=len(sliced))

    def _record_creation_failure(
        self,
        *,
        reason: str,
        payment_session_id: uuid.UUID,
        trigger_event_type: str,
        trigger_event_id: str | None,
        request_id: str,
    ) -> None:
        ORDER_CREATION_FAILED_TOTAL.labels(reason=reason).inc()
        logger.warning(
            "order creation failed",
            extra={
                "request_id": request_id,
                "reason": reason,
                "payment_session_id": str(payment_session_id),
                "trigger_event_type": trigger_event_type,
                "trigger_event_id": trigger_event_id,
            },
        )

    def _parse_basket_snapshot(
        self,
        basket_snapshot: dict[str, object],
    ) -> tuple[str, int, int, int, list[OrderItemCreate]]:
        currency_raw = basket_snapshot.get("currency")
        if not isinstance(currency_raw, str) or len(currency_raw) != 3:
            raise OrderCreationError("invalid_basket_snapshot")
        currency = currency_raw.lower()

        items_raw = basket_snapshot.get("items")
        if not isinstance(items_raw, list) or not items_raw:
            raise OrderCreationError("invalid_basket_snapshot")

        item_creates: list[OrderItemCreate] = []
        for raw_item in items_raw:
            if not isinstance(raw_item, Mapping):
                raise OrderCreationError("invalid_basket_snapshot")
            item = dict(raw_item)

            item_type_raw = item.get("item_type", OrderItemType.PRODUCT.value)
            if not isinstance(item_type_raw, str):
                raise OrderCreationError("invalid_basket_snapshot")
            try:
                item_type = OrderItemType(item_type_raw)
            except ValueError as exc:
                raise OrderCreationError("invalid_basket_snapshot") from exc

            external_price_id = self._optional_str(item.get("external_price_id"))
            description = self._optional_str(item.get("description"))
            quantity = self._required_int(item.get("quantity"))
            unit_amount_cents = self._required_int(item.get("unit_amount_cents"))
            subtotal_amount_cents = self._required_int(item.get("subtotal_amount_cents"))
            tax_amount_cents = self._optional_int(item.get("tax_amount_cents"), default=0)
            total_amount_cents = self._required_int(item.get("total_amount_cents"))

            item_creates.append(
                OrderItemCreate(
                    item_type=item_type,
                    external_price_id=external_price_id,
                    description=description,
                    quantity=quantity,
                    unit_amount_cents=unit_amount_cents,
                    subtotal_amount_cents=subtotal_amount_cents,
                    tax_amount_cents=tax_amount_cents,
                    total_amount_cents=total_amount_cents,
                )
            )

        subtotal_amount_cents = self._optional_int(
            basket_snapshot.get("subtotal_amount_cents"),
            default=sum(item.subtotal_amount_cents for item in item_creates),
        )
        tax_amount_cents = self._optional_int(
            basket_snapshot.get("tax_amount_cents"),
            default=sum(item.tax_amount_cents for item in item_creates),
        )
        total_amount_cents = self._optional_int(
            basket_snapshot.get("total_amount_cents"),
            default=sum(item.total_amount_cents for item in item_creates),
        )

        return currency, subtotal_amount_cents, tax_amount_cents, total_amount_cents, item_creates

    @staticmethod
    def _required_int(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise OrderCreationError("invalid_basket_snapshot")
        return value

    @staticmethod
    def _optional_int(value: object, *, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise OrderCreationError("invalid_basket_snapshot")
        return value

    @staticmethod
    def _optional_str(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raise OrderCreationError("invalid_basket_snapshot")

    def _to_client_order_view(self, order: Order) -> ClientOrderView:
        snapshot = self._parse_order_snapshot(order.payment_session.basket_snapshot)
        meal_plan = (
            vendor_repo.get_meal_plan_by_id_for_update(
                self._session, meal_plan_id=snapshot.meal_plan_id
            )
            if snapshot.meal_plan_id is not None
            else None
        )
        pickup_window = (
            vendor_repo.get_vendor_pickup_window_by_id(
                self._session,
                pickup_window_id=snapshot.pickup_window_id,
            )
            if snapshot.pickup_window_id is not None
            else None
        )
        recommendation = self._resolve_grounded_recommendation(
            client_user_id=order.client_user_id,
            meal_plan_id=meal_plan.id if meal_plan is not None else snapshot.meal_plan_id,
            recommendation_id=snapshot.recommendation_id,
        )
        items = tuple(
            ClientOrderItemView(
                id=item.id,
                item_type=item.item_type,
                external_price_id=item.external_price_id,
                description=item.description,
                quantity=item.quantity,
                unit_amount_cents=item.unit_amount_cents,
                subtotal_amount_cents=item.subtotal_amount_cents,
                tax_amount_cents=item.tax_amount_cents,
                total_amount_cents=item.total_amount_cents,
                created_at=item.created_at,
            )
            for item in order_item_repo.get_by_order_id(self._session, order.id)
        )
        return ClientOrderView(
            id=order.id,
            payment_session_id=order.payment_session_id,
            client_user_id=order.client_user_id,
            order_payment_status=order.order_payment_status,
            fulfillment_status=order.fulfillment_status,
            currency=order.currency,
            subtotal_amount_cents=order.subtotal_amount_cents,
            tax_amount_cents=order.tax_amount_cents,
            total_amount_cents=order.total_amount_cents,
            created_at=order.created_at,
            updated_at=order.updated_at,
            meal_plan_context_type=(
                "pt_recommended" if recommendation is not None else "direct_or_assigned"
            ),
            meal_plan=self._build_meal_plan_summary(meal_plan) if meal_plan is not None else None,
            pickup_window=(
                self._build_pickup_window_view(pickup_window) if pickup_window is not None else None
            ),
            pt_recommendation=(
                self._build_recommendation_view(recommendation)
                if recommendation is not None
                else None
            ),
            items=items,
        )

    def _parse_order_snapshot(self, basket_snapshot: object) -> _ParsedOrderSnapshot:
        if not isinstance(basket_snapshot, Mapping):
            return _ParsedOrderSnapshot(
                meal_plan_id=None,
                pickup_window_id=None,
                recommendation_id=None,
            )

        snapshot = dict(basket_snapshot)
        return _ParsedOrderSnapshot(
            meal_plan_id=self._coerce_uuid(snapshot.get("meal_plan_id")),
            pickup_window_id=self._coerce_uuid(snapshot.get("pickup_window_id")),
            recommendation_id=self._coerce_uuid(
                snapshot.get("recommendation_id") or snapshot.get("meal_plan_recommendation_id")
            ),
        )

    def _resolve_grounded_recommendation(
        self,
        *,
        client_user_id: uuid.UUID,
        meal_plan_id: uuid.UUID | None,
        recommendation_id: uuid.UUID | None,
    ) -> MealPlanRecommendation | None:
        if recommendation_id is None or meal_plan_id is None:
            return None
        recommendations = recommendation_repo.list_recommendations_for_ids(
            self._session,
            recommendation_ids=(recommendation_id,),
        )
        if not recommendations:
            return None
        recommendation = recommendations[0]
        if recommendation.client_user_id != client_user_id:
            return None
        if recommendation.meal_plan_id != meal_plan_id:
            return None
        return recommendation

    def _build_meal_plan_summary(
        self,
        meal_plan: MealPlan,
    ) -> ClientOrderMealPlanSummaryView:
        ordered_items = sorted(meal_plan.items, key=lambda item: (item.position, str(item.id)))
        ordered_availability = sorted(
            meal_plan.availability_entries,
            key=lambda item: (item.pickup_window.pickup_start_at, str(item.id)),
        )
        return ClientOrderMealPlanSummaryView(
            id=meal_plan.id,
            vendor_id=meal_plan.vendor_id,
            slug=meal_plan.slug,
            name=meal_plan.name,
            description=meal_plan.description,
            status=meal_plan.status,
            total_price_cents=sum(
                item.vendor_menu_item.price_cents * item.quantity for item in ordered_items
            ),
            total_calories=sum(
                (item.vendor_menu_item.calories or 0) * item.quantity for item in ordered_items
            ),
            item_count=len(ordered_items),
            availability_count=len(ordered_availability),
        )

    def _build_pickup_window_view(
        self,
        pickup_window: VendorPickupWindow,
    ) -> ClientOrderPickupWindowView:
        return ClientOrderPickupWindowView(
            id=pickup_window.id,
            vendor_id=pickup_window.vendor_id,
            label=pickup_window.label,
            status=pickup_window.status,
            pickup_start_at=pickup_window.pickup_start_at,
            pickup_end_at=pickup_window.pickup_end_at,
            order_cutoff_at=pickup_window.order_cutoff_at,
            notes=pickup_window.notes,
        )

    def _build_recommendation_view(
        self,
        recommendation: MealPlanRecommendation,
    ) -> ClientOrderRecommendationView:
        return ClientOrderRecommendationView(
            id=recommendation.id,
            pt_user_id=recommendation.pt_user_id,
            client_user_id=recommendation.client_user_id,
            meal_plan_id=recommendation.meal_plan_id,
            status=recommendation.status,
            rationale=recommendation.rationale,
            recommended_at=recommendation.recommended_at,
            expires_at=recommendation.expires_at,
            is_expired=self._is_expired(recommendation.expires_at),
        )

    def _is_upcoming_pickup(self, *, order: Order, reference_time: datetime) -> bool:
        if order.fulfillment_status == OrderFulfillmentStatus.CANCELED:
            return False
        snapshot = self._parse_order_snapshot(order.payment_session.basket_snapshot)
        if snapshot.pickup_window_id is None:
            return False
        pickup_window = vendor_repo.get_vendor_pickup_window_by_id(
            self._session,
            pickup_window_id=snapshot.pickup_window_id,
        )
        if pickup_window is None:
            return False
        return self._normalize_dt(pickup_window.pickup_end_at) > reference_time

    @staticmethod
    def _coerce_uuid(value: object) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalize_dt(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    def _is_expired(self, expires_at: datetime | None) -> bool:
        if expires_at is None:
            return False
        return self._normalize_dt(expires_at) <= datetime.now(UTC)
