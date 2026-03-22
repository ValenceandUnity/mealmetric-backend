from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import (
    get_current_user,
    require_roles,
    require_trusted_caller,
)
from mealmetric.api.schemas.recommendation import (
    MealPlanRecommendationListResponse,
    MealPlanRecommendationRead,
    RecommendationMealPlanSummaryRead,
    RecommendationPtAttributionRead,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.recommendation_service import (
    MealPlanRecommendationService,
    MealPlanRecommendationView,
    RecommendationConflictError,
    RecommendationMealPlanSummaryView,
    RecommendationNotFoundError,
    RecommendationPermissionError,
    RecommendationPtAttributionView,
    RecommendationValidationError,
)

router = APIRouter(
    prefix="/client",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-meal-plan-recommendations"],
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


def _translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RecommendationNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, RecommendationConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, RecommendationPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, RecommendationValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


def _meal_plan_summary_to_read(
    view: RecommendationMealPlanSummaryView,
) -> RecommendationMealPlanSummaryRead:
    return RecommendationMealPlanSummaryRead(
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


def _pt_attribution_to_read(
    view: RecommendationPtAttributionView,
) -> RecommendationPtAttributionRead:
    return RecommendationPtAttributionRead(
        id=view.id,
        email=view.email,
        display_name=view.display_name,
    )


def _recommendation_to_read(
    view: MealPlanRecommendationView,
) -> MealPlanRecommendationRead:
    return MealPlanRecommendationRead(
        id=view.id,
        pt_user_id=view.pt_user_id,
        client_user_id=view.client_user_id,
        meal_plan_id=view.meal_plan_id,
        status=view.status,
        rationale=view.rationale,
        recommended_at=view.recommended_at,
        expires_at=view.expires_at,
        is_expired=view.is_expired,
        created_at=view.created_at,
        updated_at=view.updated_at,
        pt=_pt_attribution_to_read(view.pt),
        meal_plan=_meal_plan_summary_to_read(view.meal_plan),
        meal_plan_is_currently_discoverable=view.meal_plan_is_currently_discoverable,
        meal_plan_is_currently_available=view.meal_plan_is_currently_available,
    )


@router.get(
    "/meal-plan-recommendations",
    response_model=MealPlanRecommendationListResponse,
)
def list_client_meal_plan_recommendations(
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> MealPlanRecommendationListResponse:
    session = _require_db(db)
    service = MealPlanRecommendationService(session)
    try:
        view = service.list_recommendations_for_client(client_user_id=current_user.id)
    except (
        RecommendationConflictError,
        RecommendationNotFoundError,
        RecommendationPermissionError,
        RecommendationValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc

    items = [_recommendation_to_read(item) for item in view.items]
    return MealPlanRecommendationListResponse(items=items, count=len(items))
