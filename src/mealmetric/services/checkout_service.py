import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.core.settings import Settings
from mealmetric.models.payment_session import PaymentStatus
from mealmetric.repos import payment_session_repo
from mealmetric.services.stripe_service import (
    CheckoutSessionResult,
    StripeService,
)


class CheckoutPersistenceError(Exception):
    """Raised when checkout persistence fails."""


@dataclass(frozen=True, slots=True)
class CheckoutSnapshotContext:
    currency: str
    description: str | None
    unit_amount_cents: int | None
    subtotal_amount_cents: int | None
    tax_amount_cents: int | None
    total_amount_cents: int | None
    meal_plan_id: uuid.UUID | None
    pickup_window_id: uuid.UUID | None
    recommendation_id: uuid.UUID | None


class CheckoutService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session
        self._stripe_service = StripeService(settings)

    def create_checkout_session(
        self,
        *,
        price_id: str,
        quantity: int,
        user_id: uuid.UUID,
        currency: str = "usd",
        description: str | None = None,
        unit_amount_cents: int | None = None,
        subtotal_amount_cents: int | None = None,
        tax_amount_cents: int | None = None,
        total_amount_cents: int | None = None,
        meal_plan_id: uuid.UUID | None = None,
        pickup_window_id: uuid.UUID | None = None,
        recommendation_id: uuid.UUID | None = None,
    ) -> CheckoutSessionResult:
        stripe_result = self._stripe_service.create_checkout_session(
            price_id=price_id, quantity=quantity
        )
        snapshot = self._build_basket_snapshot(
            price_id=price_id,
            quantity=quantity,
            context=CheckoutSnapshotContext(
                currency=currency,
                description=description,
                unit_amount_cents=unit_amount_cents,
                subtotal_amount_cents=subtotal_amount_cents,
                tax_amount_cents=tax_amount_cents,
                total_amount_cents=total_amount_cents,
                meal_plan_id=meal_plan_id,
                pickup_window_id=pickup_window_id,
                recommendation_id=recommendation_id,
            ),
        )

        try:
            payment_session_repo.create_payment_session(
                self._session,
                user_id=user_id,
                stripe_price_id=price_id,
                stripe_checkout_session_id=stripe_result.session_id,
                stripe_payment_intent_id=stripe_result.payment_intent_id,
                payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
                basket_snapshot=snapshot,
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise CheckoutPersistenceError("payment_session_persist_failed") from exc

        return stripe_result

    @staticmethod
    def _build_basket_snapshot(
        *,
        price_id: str,
        quantity: int,
        context: CheckoutSnapshotContext,
    ) -> dict[str, object]:
        normalized_currency = context.currency.strip().lower()
        normalized_description = (
            context.description.strip() if context.description is not None else None
        )
        unit_amount_cents = context.unit_amount_cents or 0
        subtotal_amount_cents = (
            context.subtotal_amount_cents
            if context.subtotal_amount_cents is not None
            else unit_amount_cents * quantity
        )
        tax_amount_cents = context.tax_amount_cents if context.tax_amount_cents is not None else 0
        total_amount_cents = (
            context.total_amount_cents
            if context.total_amount_cents is not None
            else subtotal_amount_cents + tax_amount_cents
        )

        item_snapshot: dict[str, object] = {
            "item_type": "product",
            "external_price_id": price_id,
            "description": normalized_description,
            "quantity": quantity,
            "unit_amount_cents": unit_amount_cents,
            "subtotal_amount_cents": subtotal_amount_cents,
            "tax_amount_cents": tax_amount_cents,
            "total_amount_cents": total_amount_cents,
        }

        snapshot: dict[str, object] = {
            "currency": normalized_currency,
            "items": [item_snapshot],
            "line_items": [dict(item_snapshot)],
            "subtotal_amount_cents": subtotal_amount_cents,
            "tax_amount_cents": tax_amount_cents,
            "total_amount_cents": total_amount_cents,
        }
        if context.meal_plan_id is not None:
            snapshot["meal_plan_id"] = str(context.meal_plan_id)
        if context.pickup_window_id is not None:
            snapshot["pickup_window_id"] = str(context.pickup_window_id)
        if context.recommendation_id is not None:
            recommendation_id = str(context.recommendation_id)
            snapshot["recommendation_id"] = recommendation_id
            snapshot["meal_plan_recommendation_id"] = recommendation_id
        return snapshot
