from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.subscriptions import (
    SubscriptionListResponse,
    SubscriptionMealPlanRead,
    SubscriptionRead,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.subscription_service import (
    SubscriptionListView,
    SubscriptionService,
    SubscriptionView,
)

router = APIRouter(
    prefix="/client",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-subscriptions"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    return db


def _to_subscription_read(view: SubscriptionView) -> SubscriptionRead:
    return SubscriptionRead(
        id=view.id,
        stripe_subscription_id=view.stripe_subscription_id,
        stripe_customer_id=view.stripe_customer_id,
        client_user_id=view.client_user_id,
        meal_plan_id=view.meal_plan_id,
        status=view.status,
        billing_interval=view.billing_interval,
        current_period_start=view.current_period_start,
        current_period_end=view.current_period_end,
        cancel_at_period_end=view.cancel_at_period_end,
        canceled_at=view.canceled_at,
        latest_invoice_id=view.latest_invoice_id,
        latest_invoice_status=view.latest_invoice_status,
        latest_stripe_event_id=view.latest_stripe_event_id,
        last_invoice_paid_at=view.last_invoice_paid_at,
        last_invoice_failed_at=view.last_invoice_failed_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
        meal_plan=(
            SubscriptionMealPlanRead(
                id=view.meal_plan.id,
                vendor_id=view.meal_plan.vendor_id,
                slug=view.meal_plan.slug,
                name=view.meal_plan.name,
            )
            if view.meal_plan is not None
            else None
        ),
    )


def _to_list_response(view: SubscriptionListView) -> SubscriptionListResponse:
    items = [_to_subscription_read(item) for item in view.items]
    return SubscriptionListResponse(items=items, count=len(items))


@router.get("/subscriptions", response_model=SubscriptionListResponse)
def list_client_subscriptions(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubscriptionListResponse:
    session = _require_db(db)
    service = SubscriptionService(session)
    view = service.list_for_client(
        client_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return _to_list_response(view)
