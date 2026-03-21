from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.vendor import (
    MealPlanListResponse,
    MealPlanSummaryRead,
    VendorMetricsResponse,
    VendorPortalIdentityRead,
    VendorPortalMeResponse,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.vendor_portal_service import (
    VendorPortalAccessError,
    VendorPortalMeView,
    VendorPortalService,
)
from mealmetric.services.vendor_service import MealPlanSummaryView, VendorDetailView

router = APIRouter(
    prefix="/vendor",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.VENDOR))],
    tags=["vendor-portal"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="db_unavailable")
    return db


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VendorPortalAccessError):
        detail = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if detail in {"vendor_membership_not_found", "vendor_not_found"}
            else status.HTTP_403_FORBIDDEN
        )
        return HTTPException(status_code=status_code, detail=detail)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


def _meal_plan_to_read(plan: MealPlanSummaryView) -> MealPlanSummaryRead:
    return MealPlanSummaryRead(
        id=plan.id,
        vendor_id=plan.vendor_id,
        vendor_name=plan.vendor_name,
        vendor_zip_code=plan.vendor_zip_code,
        slug=plan.slug,
        name=plan.name,
        description=plan.description,
        status=plan.status,
        total_price_cents=plan.total_price_cents,
        total_calories=plan.total_calories,
        item_count=plan.item_count,
        availability_count=plan.availability_count,
    )


def _vendor_identity_to_read(vendor: VendorDetailView) -> VendorPortalIdentityRead:
    return VendorPortalIdentityRead(
        id=vendor.id,
        slug=vendor.slug,
        name=vendor.name,
        description=vendor.description,
        zip_code=vendor.zip_code,
        status=vendor.status,
        meal_plan_count=vendor.meal_plan_count,
    )


def _me_to_read(view: VendorPortalMeView) -> VendorPortalMeResponse:
    return VendorPortalMeResponse(
        user_id=view.user_id,
        email=view.email,
        vendor_ids=list(view.vendor_ids),
        default_vendor=(
            _vendor_identity_to_read(view.default_vendor) if view.default_vendor is not None else None
        ),
        vendors=[_vendor_identity_to_read(item) for item in view.vendors],
    )


@router.get("/me", response_model=VendorPortalMeResponse)
def get_vendor_me(db: DBSessionDep, current_user: CurrentUserDep) -> VendorPortalMeResponse:
    session = _require_db(db)
    service = VendorPortalService(session)
    try:
        return _me_to_read(service.get_me(current_user=current_user))
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/meal-plans", response_model=MealPlanListResponse)
def list_vendor_meal_plans(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    vendor_id: UUID | None = None,
) -> MealPlanListResponse:
    session = _require_db(db)
    service = VendorPortalService(session)
    try:
        view = service.list_meal_plans(current_user=current_user, vendor_id=vendor_id)
    except Exception as exc:
        raise _translate_error(exc) from exc
    items = [_meal_plan_to_read(item) for item in view.items]
    return MealPlanListResponse(items=items, count=len(items))


@router.get("/metrics", response_model=VendorMetricsResponse)
def get_vendor_metrics(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    vendor_id: UUID | None = None,
) -> VendorMetricsResponse:
    session = _require_db(db)
    service = VendorPortalService(session)
    try:
        view = service.get_metrics(current_user=current_user, vendor_id=vendor_id)
    except Exception as exc:
        raise _translate_error(exc) from exc
    return VendorMetricsResponse(
        vendor_id=view.vendor_id,
        vendor_name=view.vendor_name,
        zip_code=view.zip_code,
        total_meal_plans=view.total_meal_plans,
        published_meal_plans=view.published_meal_plans,
        draft_meal_plans=view.draft_meal_plans,
        total_availability_entries=view.total_availability_entries,
        open_pickup_windows=view.open_pickup_windows,
    )
