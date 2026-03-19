import uuid

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session, selectinload

from mealmetric.models.subscription import MealPlanSubscription, MealPlanSubscriptionStatus


def _query_by_id(subscription_id: uuid.UUID) -> Select[tuple[MealPlanSubscription]]:
    return (
        select(MealPlanSubscription)
        .options(selectinload(MealPlanSubscription.meal_plan))
        .where(MealPlanSubscription.id == subscription_id)
    )


def _query_by_stripe_subscription_id(
    stripe_subscription_id: str,
) -> Select[tuple[MealPlanSubscription]]:
    return (
        select(MealPlanSubscription)
        .options(selectinload(MealPlanSubscription.meal_plan))
        .where(MealPlanSubscription.stripe_subscription_id == stripe_subscription_id)
    )


def get_by_id(session: Session, subscription_id: uuid.UUID) -> MealPlanSubscription | None:
    return session.scalar(_query_by_id(subscription_id))


def get_by_stripe_subscription_id(
    session: Session,
    stripe_subscription_id: str,
) -> MealPlanSubscription | None:
    return session.scalar(_query_by_stripe_subscription_id(stripe_subscription_id))


def create_subscription(
    session: Session,
    *,
    stripe_subscription_id: str,
    stripe_customer_id: str | None,
    client_user_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    status: MealPlanSubscriptionStatus,
) -> MealPlanSubscription:
    subscription = MealPlanSubscription(
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
        client_user_id=client_user_id,
        meal_plan_id=meal_plan_id,
        status=status,
    )
    session.add(subscription)
    session.flush()
    return subscription


def save_subscription(
    session: Session,
    subscription: MealPlanSubscription,
) -> MealPlanSubscription:
    session.add(subscription)
    session.flush()
    return subscription


def list_for_client(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    limit: int,
    offset: int = 0,
) -> list[MealPlanSubscription]:
    stmt = (
        select(MealPlanSubscription)
        .options(selectinload(MealPlanSubscription.meal_plan))
        .where(MealPlanSubscription.client_user_id == client_user_id)
        .order_by(desc(MealPlanSubscription.created_at), MealPlanSubscription.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def list_for_admin(
    session: Session,
    *,
    limit: int,
    offset: int = 0,
    client_user_id: uuid.UUID | None = None,
    status: MealPlanSubscriptionStatus | None = None,
) -> list[MealPlanSubscription]:
    stmt = (
        select(MealPlanSubscription)
        .options(selectinload(MealPlanSubscription.meal_plan))
        .order_by(desc(MealPlanSubscription.created_at), MealPlanSubscription.id.asc())
        .offset(offset)
        .limit(limit)
    )
    if client_user_id is not None:
        stmt = stmt.where(MealPlanSubscription.client_user_id == client_user_id)
    if status is not None:
        stmt = stmt.where(MealPlanSubscription.status == status)
    return list(session.scalars(stmt))


def list_missing_lifecycle_linkage(session: Session) -> list[MealPlanSubscription]:
    stmt = (
        select(MealPlanSubscription)
        .options(selectinload(MealPlanSubscription.meal_plan))
        .where(MealPlanSubscription.latest_stripe_event_id.is_(None))
        .where(MealPlanSubscription.status != MealPlanSubscriptionStatus.INCOMPLETE)
        .order_by(MealPlanSubscription.created_at.asc(), MealPlanSubscription.id.asc())
    )
    return list(session.scalars(stmt))
