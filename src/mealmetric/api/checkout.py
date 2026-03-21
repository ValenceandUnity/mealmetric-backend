from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_trusted_caller
from mealmetric.core.settings import get_settings
from mealmetric.db.session import get_db
from mealmetric.models.user import User
from mealmetric.services.checkout_service import (
    CheckoutPersistenceError,
    CheckoutService,
)
from mealmetric.services.stripe_service import StripeServiceError

router = APIRouter(
    prefix="/api/checkout",
    dependencies=[Depends(require_trusted_caller)],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


class CheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_id: str
    quantity: int
    currency: str = Field(default="usd", min_length=3, max_length=3)
    description: str | None = None
    unit_amount_cents: int | None = Field(default=None, ge=0)
    subtotal_amount_cents: int | None = Field(default=None, ge=0)
    tax_amount_cents: int | None = Field(default=None, ge=0)
    total_amount_cents: int | None = Field(default=None, ge=0)
    meal_plan_id: UUID | None = None
    pickup_window_id: UUID | None = None
    recommendation_id: UUID | None = None


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


@router.post("/session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    payload: CheckoutSessionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: DBSessionDep = None,
) -> CheckoutSessionResponse:
    if not payload.price_id or not payload.price_id.startswith("price_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid price_id. It must be non-empty and start with 'price_'.",
        )
    if payload.quantity < 1 or payload.quantity > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid quantity. It must be between 1 and 100.",
        )
    normalized_currency = payload.currency.strip().lower()
    if len(normalized_currency) != 3 or not normalized_currency.isalpha():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid currency. It must be a 3-letter alphabetic code.",
        )

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    service = CheckoutService(get_settings(), db)

    try:
        result = service.create_checkout_session(
            price_id=payload.price_id,
            quantity=payload.quantity,
            user_id=current_user.id,
            currency=normalized_currency,
            description=payload.description,
            unit_amount_cents=payload.unit_amount_cents,
            subtotal_amount_cents=payload.subtotal_amount_cents,
            tax_amount_cents=payload.tax_amount_cents,
            total_amount_cents=payload.total_amount_cents,
            meal_plan_id=payload.meal_plan_id,
            pickup_window_id=payload.pickup_window_id,
            recommendation_id=payload.recommendation_id,
        )
    except StripeServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to create checkout session.",
        ) from exc
    except CheckoutPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to persist checkout session.",
        ) from exc

    return CheckoutSessionResponse(
        checkout_url=result.checkout_url, session_id=result.session_id
    )
