from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.recommendation import (
    MealPlanRecommendationCreateRequest,
    MealPlanRecommendationListResponse,
    MealPlanRecommendationRead,
    RecommendationMealPlanSummaryRead,
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
    RecommendationValidationError,
)

router = APIRouter(
    prefix="/pt",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.PT))],
    tags=["pt-meal-plan-recommendations"],
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


def _run_mutation[T](db: Session, operation: Callable[[], T]) -> T:
    try:
        result = operation()
        db.commit()
        return result
    except (
        RecommendationConflictError,
        RecommendationNotFoundError,
        RecommendationPermissionError,
        RecommendationValidationError,
    ) as exc:
        db.rollback()
        raise _translate_service_error(exc) from exc


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


def _recommendation_to_read(view: MealPlanRecommendationView) -> MealPlanRecommendationRead:
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
        meal_plan=_meal_plan_summary_to_read(view.meal_plan),
        meal_plan_is_currently_discoverable=view.meal_plan_is_currently_discoverable,
        meal_plan_is_currently_available=view.meal_plan_is_currently_available,
    )


@router.post(
    "/clients/{client_id}/meal-plan-recommendations",
    response_model=MealPlanRecommendationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meal_plan_recommendation(
    client_id: UUID,
    payload: MealPlanRecommendationCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> MealPlanRecommendationRead:
    session = _require_db(db)
    service = MealPlanRecommendationService(session)

    def _operation() -> MealPlanRecommendationView:
        return service.create_recommendation(
            pt_user_id=current_user.id,
            client_user_id=client_id,
            meal_plan_id=payload.meal_plan_id,
            rationale=payload.rationale,
            recommended_at=payload.recommended_at,
            expires_at=payload.expires_at,
        )

    view = _run_mutation(session, _operation)
    return _recommendation_to_read(view)


@router.get(
    "/clients/{client_id}/meal-plan-recommendations",
    response_model=MealPlanRecommendationListResponse,
)
def list_meal_plan_recommendations_for_client(
    client_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> MealPlanRecommendationListResponse:
    session = _require_db(db)
    service = MealPlanRecommendationService(session)
    try:
        view = service.list_recommendations_for_pt_client(
            pt_user_id=current_user.id,
            client_user_id=client_id,
        )
    except (
        RecommendationConflictError,
        RecommendationNotFoundError,
        RecommendationPermissionError,
        RecommendationValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc

    items = [_recommendation_to_read(item) for item in view.items]
    return MealPlanRecommendationListResponse(items=items, count=len(items))
