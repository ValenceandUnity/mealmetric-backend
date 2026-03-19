from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.api.schemas.vendor import MealPlanListResponse, MealPlanSummaryRead
from mealmetric.db.session import get_db
from mealmetric.models.user import Role
from mealmetric.services.vendor_service import MealPlanSummaryView, VendorService

router = APIRouter(
    prefix="/pt",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.PT))],
    tags=["pt-meal-plans"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    return db


def _parse_iso_date(raw: str | None, detail: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from exc


def _meal_plan_summary_to_read(view: MealPlanSummaryView) -> MealPlanSummaryRead:
    return MealPlanSummaryRead(
        id=view.id,
        vendor_id=view.vendor_id,
        slug=view.slug,
        name=view.name,
        description=view.description,
        status=view.status,
        total_price_cents=view.total_price_cents,
        total_calories=view.total_calories,
        item_count=view.item_count,
        availability_count=view.availability_count,
    )


@router.get("/meal-plans/search", response_model=MealPlanListResponse)
def search_meal_plans(
    db: DBSessionDep,
    vendor_id: UUID | None = None,
    calorie_min: Annotated[int | None, Query(ge=0)] = None,
    calorie_max: Annotated[int | None, Query(ge=0)] = None,
    price_min_cents: Annotated[int | None, Query(ge=0)] = None,
    price_max_cents: Annotated[int | None, Query(ge=0)] = None,
    available_on: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    pickup_window_id: UUID | None = None,
) -> MealPlanListResponse:
    session = _require_db(db)
    service = VendorService(session)
    view = service.list_meal_plans(
        vendor_id=vendor_id,
        calorie_min=calorie_min,
        calorie_max=calorie_max,
        price_min_cents=price_min_cents,
        price_max_cents=price_max_cents,
        available_on=_parse_iso_date(available_on, "invalid_available_on"),
        pickup_window_id=pickup_window_id,
    )
    items = [_meal_plan_summary_to_read(item) for item in view.items]
    return MealPlanListResponse(items=items, count=len(items))
