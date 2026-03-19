from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.client_orders import (
    ClientOrderItemRead,
    ClientOrderListResponse,
    ClientOrderMealPlanRead,
    ClientOrderPickupWindowRead,
    ClientOrderRead,
    ClientOrderRecommendationRead,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.order_service import ClientOrderListView, ClientOrderView, OrderService

router = APIRouter(
    prefix="/client",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-orders"],
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


def _to_order_read(view: ClientOrderView) -> ClientOrderRead:
    return ClientOrderRead(
        id=view.id,
        payment_session_id=view.payment_session_id,
        client_user_id=view.client_user_id,
        order_payment_status=view.order_payment_status,
        fulfillment_status=view.fulfillment_status,
        currency=view.currency,
        subtotal_amount_cents=view.subtotal_amount_cents,
        tax_amount_cents=view.tax_amount_cents,
        total_amount_cents=view.total_amount_cents,
        created_at=view.created_at,
        updated_at=view.updated_at,
        meal_plan_context_type=view.meal_plan_context_type,
        meal_plan=(
            ClientOrderMealPlanRead(
                id=view.meal_plan.id,
                vendor_id=view.meal_plan.vendor_id,
                slug=view.meal_plan.slug,
                name=view.meal_plan.name,
                description=view.meal_plan.description,
                status=view.meal_plan.status,
                total_price_cents=view.meal_plan.total_price_cents,
                total_calories=view.meal_plan.total_calories,
                item_count=view.meal_plan.item_count,
                availability_count=view.meal_plan.availability_count,
            )
            if view.meal_plan is not None
            else None
        ),
        pickup_window=(
            ClientOrderPickupWindowRead(
                id=view.pickup_window.id,
                vendor_id=view.pickup_window.vendor_id,
                label=view.pickup_window.label,
                status=view.pickup_window.status,
                pickup_start_at=view.pickup_window.pickup_start_at,
                pickup_end_at=view.pickup_window.pickup_end_at,
                order_cutoff_at=view.pickup_window.order_cutoff_at,
                notes=view.pickup_window.notes,
            )
            if view.pickup_window is not None
            else None
        ),
        pt_recommendation=(
            ClientOrderRecommendationRead(
                id=view.pt_recommendation.id,
                pt_user_id=view.pt_recommendation.pt_user_id,
                client_user_id=view.pt_recommendation.client_user_id,
                meal_plan_id=view.pt_recommendation.meal_plan_id,
                status=view.pt_recommendation.status,
                rationale=view.pt_recommendation.rationale,
                recommended_at=view.pt_recommendation.recommended_at,
                expires_at=view.pt_recommendation.expires_at,
                is_expired=view.pt_recommendation.is_expired,
            )
            if view.pt_recommendation is not None
            else None
        ),
        items=[
            ClientOrderItemRead(
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
            for item in view.items
        ],
    )


def _to_list_response(view: ClientOrderListView) -> ClientOrderListResponse:
    items = [_to_order_read(item) for item in view.items]
    return ClientOrderListResponse(items=items, count=len(items))


@router.get("/orders", response_model=ClientOrderListResponse)
def list_client_orders(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientOrderListResponse:
    session = _require_db(db)
    service = OrderService(session)
    view = service.list_orders_for_client(
        client_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return _to_list_response(view)


@router.get("/upcoming-pickups", response_model=ClientOrderListResponse)
def list_client_upcoming_pickups(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientOrderListResponse:
    session = _require_db(db)
    service = OrderService(session)
    view = service.list_upcoming_pickups_for_client(
        client_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return _to_list_response(view)
