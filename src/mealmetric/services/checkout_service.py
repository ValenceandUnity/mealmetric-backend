import uuid

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
    ) -> CheckoutSessionResult:
        stripe_result = self._stripe_service.create_checkout_session(
            price_id=price_id, quantity=quantity
        )

        try:
            payment_session_repo.create_payment_session(
                self._session,
                user_id=user_id,
                stripe_price_id=price_id,
                stripe_checkout_session_id=stripe_result.session_id,
                stripe_payment_intent_id=stripe_result.payment_intent_id,
                payment_status=PaymentStatus.CHECKOUT_SESSION_CREATED,
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise CheckoutPersistenceError("payment_session_persist_failed") from exc

        return stripe_result
