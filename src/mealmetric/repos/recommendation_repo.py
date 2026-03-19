import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.interfaces import ORMOption

from mealmetric.models.recommendation import MealPlanRecommendation, MealPlanRecommendationStatus
from mealmetric.models.vendor import (
    MealPlan,
    MealPlanAvailability,
    MealPlanItem,
)


def _recommendation_load_options() -> tuple[ORMOption, ...]:
    return (
        selectinload(MealPlanRecommendation.meal_plan).selectinload(MealPlan.vendor),
        selectinload(MealPlanRecommendation.meal_plan)
        .selectinload(MealPlan.items)
        .selectinload(MealPlanItem.vendor_menu_item),
        selectinload(MealPlanRecommendation.meal_plan)
        .selectinload(MealPlan.availability_entries)
        .selectinload(MealPlanAvailability.pickup_window),
    )


def create_recommendation(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    status: MealPlanRecommendationStatus,
    rationale: str | None,
    recommended_at: datetime,
    expires_at: datetime | None,
) -> MealPlanRecommendation:
    recommendation = MealPlanRecommendation(
        pt_user_id=pt_user_id,
        client_user_id=client_user_id,
        meal_plan_id=meal_plan_id,
        status=status,
        rationale=rationale,
        recommended_at=recommended_at,
        expires_at=expires_at,
    )
    session.add(recommendation)
    session.flush()
    return recommendation


def get_recommendation_by_id(
    session: Session,
    *,
    recommendation_id: uuid.UUID,
) -> MealPlanRecommendation | None:
    stmt: Select[tuple[MealPlanRecommendation]] = (
        select(MealPlanRecommendation)
        .options(*_recommendation_load_options())
        .where(MealPlanRecommendation.id == recommendation_id)
    )
    return session.scalar(stmt)


def save_recommendation(
    session: Session,
    recommendation: MealPlanRecommendation,
) -> MealPlanRecommendation:
    session.add(recommendation)
    session.flush()
    return recommendation


def list_recommendations_for_pt(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
) -> list[MealPlanRecommendation]:
    stmt: Select[tuple[MealPlanRecommendation]] = (
        select(MealPlanRecommendation)
        .options(*_recommendation_load_options())
        .where(MealPlanRecommendation.pt_user_id == pt_user_id)
        .order_by(
            MealPlanRecommendation.recommended_at.desc(),
            MealPlanRecommendation.created_at.desc(),
            MealPlanRecommendation.id.desc(),
        )
    )
    return list(session.scalars(stmt))


def list_recommendations_for_client(
    session: Session,
    *,
    client_user_id: uuid.UUID,
) -> list[MealPlanRecommendation]:
    stmt: Select[tuple[MealPlanRecommendation]] = (
        select(MealPlanRecommendation)
        .options(*_recommendation_load_options())
        .where(MealPlanRecommendation.client_user_id == client_user_id)
        .order_by(
            MealPlanRecommendation.recommended_at.desc(),
            MealPlanRecommendation.created_at.desc(),
            MealPlanRecommendation.id.desc(),
        )
    )
    return list(session.scalars(stmt))


def list_recommendations_for_pt_client(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> list[MealPlanRecommendation]:
    stmt: Select[tuple[MealPlanRecommendation]] = (
        select(MealPlanRecommendation)
        .options(*_recommendation_load_options())
        .where(
            MealPlanRecommendation.pt_user_id == pt_user_id,
            MealPlanRecommendation.client_user_id == client_user_id,
        )
        .order_by(
            MealPlanRecommendation.recommended_at.desc(),
            MealPlanRecommendation.created_at.desc(),
            MealPlanRecommendation.id.desc(),
        )
    )
    return list(session.scalars(stmt))


def list_recommendations_for_ids(
    session: Session,
    *,
    recommendation_ids: Sequence[uuid.UUID],
) -> list[MealPlanRecommendation]:
    if not recommendation_ids:
        return []
    stmt: Select[tuple[MealPlanRecommendation]] = (
        select(MealPlanRecommendation)
        .options(*_recommendation_load_options())
        .where(MealPlanRecommendation.id.in_(tuple(recommendation_ids)))
        .order_by(
            MealPlanRecommendation.recommended_at.desc(),
            MealPlanRecommendation.created_at.desc(),
            MealPlanRecommendation.id.desc(),
        )
    )
    return list(session.scalars(stmt))
