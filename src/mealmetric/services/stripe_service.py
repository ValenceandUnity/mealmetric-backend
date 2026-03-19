import importlib
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from mealmetric.core.settings import Settings

logger = logging.getLogger("mealmetric.stripe")


class StripeServiceError(Exception):
    """Raised when Stripe session creation fails."""


try:
    _stripe_module: Any | None = importlib.import_module("stripe")
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    _stripe_module = None


def _require_stripe() -> Any:
    if _stripe_module is None:
        raise StripeServiceError("stripe_sdk_not_installed")
    return _stripe_module


class _FallbackStripeError(Exception):
    """Fallback Stripe-compatible error base."""


class _FallbackAPIError(_FallbackStripeError):
    """Fallback Stripe-compatible API error."""


class _FallbackCheckoutSession:
    @staticmethod
    def create(**_: object) -> object:
        raise StripeServiceError("stripe_sdk_not_installed")


class _FallbackStripeModule:
    StripeError = _FallbackStripeError
    APIError = _FallbackAPIError
    checkout = SimpleNamespace(Session=_FallbackCheckoutSession)
    api_key: str | None = None


@dataclass(frozen=True)
class CheckoutSessionResult:
    session_id: str
    checkout_url: str
    payment_intent_id: str | None


class StripeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stripe = _stripe_module or _FallbackStripeModule()

    def create_checkout_session(self, *, price_id: str, quantity: int) -> CheckoutSessionResult:
        if _stripe_module is None:
            raise StripeServiceError("stripe_sdk_not_installed")

        self._stripe.api_key = self._settings.stripe_secret_key
        try:
            session = self._stripe.checkout.Session.create(
                mode="payment",
                line_items=[{"price": price_id, "quantity": quantity}],
                success_url=str(self._settings.stripe_success_url),
                cancel_url=str(self._settings.stripe_cancel_url),
            )
        except self._stripe.StripeError as exc:
            logger.exception("stripe checkout session creation failed")
            raise StripeServiceError("checkout_session_creation_failed") from exc

        session_id = getattr(session, "id", None)
        checkout_url = getattr(session, "url", None)
        payment_intent = getattr(session, "payment_intent", None)
        payment_intent_id = payment_intent if isinstance(payment_intent, str) else None
        if not isinstance(session_id, str) or not isinstance(checkout_url, str):
            logger.error("stripe returned invalid checkout session payload")
            raise StripeServiceError("checkout_session_creation_failed")

        return CheckoutSessionResult(
            session_id=session_id,
            checkout_url=checkout_url,
            payment_intent_id=payment_intent_id,
        )
