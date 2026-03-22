from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.api.schemas.vendor import (
    MealPlanAvailabilityListResponse,
    MealPlanAvailabilityRead,
    MealPlanItemRead,
    MealPlanListResponse,
    MealPlanRead,
    MealPlanSummaryRead,
    VendorListResponse,
    VendorRead,
    VendorSummaryRead,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role
from mealmetric.repos import vendor_repo
from mealmetric.services.vendor_service import (
    MealPlanAvailabilityView,
    MealPlanDetailView,
    MealPlanItemView,
    MealPlanSummaryView,
    VendorDetailView,
    VendorNotFoundError,
    VendorService,
    VendorSummaryView,
    VendorValidationError,
)

router = APIRouter(
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-meal-plans"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    return db


def _translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VendorNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, VendorValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


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


def _normalize_optional_query(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = raw.strip()
    return normalized or None


def _normalize_zip_filters(
    zip_code: str | None,
    zip_codes: list[str] | None,
) -> tuple[str | None, tuple[str, ...] | None]:
    try:
        normalized_zip_codes = vendor_repo.normalize_zip_filters(zip_codes)
        if zip_codes is not None:
            return None, normalized_zip_codes or None
        return vendor_repo.normalize_zip_filter(zip_code), None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


def _meal_plan_item_to_read(view: MealPlanItemView) -> MealPlanItemRead:
    return MealPlanItemRead(
        id=view.id,
        vendor_menu_item_id=view.vendor_menu_item_id,
        slug=view.slug,
        name=view.name,
        quantity=view.quantity,
        position=view.position,
        notes=view.notes,
        price_cents=view.price_cents,
        currency_code=view.currency_code,
        calories=view.calories,
    )


def _meal_plan_availability_to_read(view: MealPlanAvailabilityView) -> MealPlanAvailabilityRead:
    return MealPlanAvailabilityRead(
        id=view.id,
        pickup_window_id=view.pickup_window_id,
        pickup_window_label=view.pickup_window_label,
        pickup_start_at=view.pickup_start_at,
        pickup_end_at=view.pickup_end_at,
        availability_status=view.availability_status,
        pickup_window_status=view.pickup_window_status,
        inventory_count=view.inventory_count,
    )


def _meal_plan_summary_to_read(view: MealPlanSummaryView) -> MealPlanSummaryRead:
    return MealPlanSummaryRead(
        id=view.id,
        vendor_id=view.vendor_id,
        vendor_name=view.vendor_name,
        vendor_zip_code=view.vendor_zip_code,
        slug=view.slug,
        name=view.name,
        description=view.description,
        status=view.status,
        total_price_cents=view.total_price_cents,
        total_calories=view.total_calories,
        item_count=view.item_count,
        availability_count=view.availability_count,
    )


def _vendor_summary_to_read(view: VendorSummaryView) -> VendorSummaryRead:
    return VendorSummaryRead(
        id=view.id,
        slug=view.slug,
        name=view.name,
        status=view.status,
        meal_plan_count=view.meal_plan_count,
    )


def _vendor_to_read(view: VendorDetailView) -> VendorRead:
    return VendorRead(
        id=view.id,
        slug=view.slug,
        name=view.name,
        description=view.description,
        zip_code=view.zip_code,
        status=view.status,
        meal_plans=[_meal_plan_summary_to_read(item) for item in view.meal_plans],
        meal_plan_count=view.meal_plan_count,
    )


def _meal_plan_to_read(view: MealPlanDetailView) -> MealPlanRead:
    return MealPlanRead(
        id=view.id,
        vendor_id=view.vendor_id,
        vendor_name=view.vendor_name,
        vendor_zip_code=view.vendor_zip_code,
        slug=view.slug,
        name=view.name,
        description=view.description,
        status=view.status,
        total_price_cents=view.total_price_cents,
        total_calories=view.total_calories,
        item_count=view.item_count,
        availability_count=view.availability_count,
        items=[_meal_plan_item_to_read(item) for item in view.items],
        availability=[_meal_plan_availability_to_read(item) for item in view.availability],
    )


@router.get("/vendors", response_model=VendorListResponse)
def list_vendors(db: DBSessionDep) -> VendorListResponse:
    session = _require_db(db)
    service = VendorService(session)
    view = service.list_vendors()
    items = [_vendor_summary_to_read(item) for item in view.items]
    return VendorListResponse(items=items, count=len(items))


@router.get("/vendors/{vendor_id}", response_model=VendorRead)
def get_vendor_detail(vendor_id: UUID, db: DBSessionDep) -> VendorRead:
    session = _require_db(db)
    service = VendorService(session)
    try:
        view = service.get_vendor_detail(vendor_id=vendor_id)
    except Exception as exc:
        raise _translate_service_error(exc) from exc
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found")
    return _vendor_to_read(view)


@router.get("/meal-plans", response_model=MealPlanListResponse)
def list_meal_plans(
    db: DBSessionDep,
    vendor_id: UUID | None = None,
    q: str | None = None,
    calorie_min: Annotated[int | None, Query(ge=0)] = None,
    calorie_max: Annotated[int | None, Query(ge=0)] = None,
    price_min_cents: Annotated[int | None, Query(ge=0)] = None,
    price_max_cents: Annotated[int | None, Query(ge=0)] = None,
    zip_code: Annotated[str | None, Query(min_length=3, max_length=16)] = None,
    zip_codes: Annotated[list[str] | None, Query()] = None,
    budget_min_cents: Annotated[int | None, Query(ge=0)] = None,
    budget_max_cents: Annotated[int | None, Query(ge=0)] = None,
    available_on: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    pickup_window_id: UUID | None = None,
) -> MealPlanListResponse:
    session = _require_db(db)
    service = VendorService(session)
    normalized_zip_code, normalized_zip_codes = _normalize_zip_filters(zip_code, zip_codes)
    view = service.list_meal_plans(
        vendor_id=vendor_id,
        q=_normalize_optional_query(q),
        calorie_min=calorie_min,
        calorie_max=calorie_max,
        price_min_cents=price_min_cents,
        price_max_cents=price_max_cents,
        zip_code=normalized_zip_code,
        zip_codes=normalized_zip_codes,
        budget_min_cents=budget_min_cents,
        budget_max_cents=budget_max_cents,
        available_on=_parse_iso_date(available_on, "invalid_available_on"),
        pickup_window_id=pickup_window_id,
    )
    items = [_meal_plan_summary_to_read(item) for item in view.items]
    return MealPlanListResponse(items=items, count=len(items))


@router.get("/meal-plans/{meal_plan_id}", response_model=MealPlanRead)
def get_meal_plan_detail(meal_plan_id: UUID, db: DBSessionDep) -> MealPlanRead:
    session = _require_db(db)
    service = VendorService(session)
    try:
        view = service.get_meal_plan_detail(meal_plan_id=meal_plan_id)
    except Exception as exc:
        raise _translate_service_error(exc) from exc
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="meal_plan_not_found")
    return _meal_plan_to_read(view)


@router.get(
    "/meal-plans/{meal_plan_id}/availability",
    response_model=MealPlanAvailabilityListResponse,
)
def list_meal_plan_availability(
    meal_plan_id: UUID,
    db: DBSessionDep,
) -> MealPlanAvailabilityListResponse:
    session = _require_db(db)
    service = VendorService(session)
    meal_plan = service.get_meal_plan_detail(meal_plan_id=meal_plan_id)
    if meal_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="meal_plan_not_found")
    items = [_meal_plan_availability_to_read(item) for item in meal_plan.availability]
    return MealPlanAvailabilityListResponse(items=items, count=len(items))
