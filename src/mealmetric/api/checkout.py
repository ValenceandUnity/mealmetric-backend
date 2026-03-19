from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_trusted_caller
from mealmetric.core.settings import get_settings
from mealmetric.db.session import get_db
from mealmetric.models.user import User
from mealmetric.services.checkout_service import CheckoutPersistenceError, CheckoutService
from mealmetric.services.stripe_service import StripeServiceError

router = APIRouter(
    prefix="/api/checkout",
    dependencies=[Depends(require_trusted_caller)],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


class CheckoutSessionRequest(BaseModel):
    price_id: str
    quantity: int


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

    return CheckoutSessionResponse(checkout_url=result.checkout_url, session_id=result.session_id)
