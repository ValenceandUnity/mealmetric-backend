from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.recommendation import MealPlanRecommendationStatus
from mealmetric.models.user import Role, User
from mealmetric.models.vendor import MealPlan, Vendor
from mealmetric.repos import recommendation_repo


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _create_user(db: Session, *, email: str, role: Role) -> User:
    user = User(email=email, password_hash="hash", role=role)
    db.add(user)
    db.flush()
    return user


def _create_meal_plan(db: Session, *, slug: str) -> MealPlan:
    vendor = Vendor(slug=f"{slug}-vendor", name=f"{slug.title()} Vendor")
    db.add(vendor)
    db.flush()
    meal_plan = MealPlan(vendor_id=vendor.id, slug=slug, name=slug.title())
    db.add(meal_plan)
    db.flush()
    return meal_plan


def test_recommendation_repo_helpers_support_create_get_save_and_deterministic_lists() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt_user = _create_user(db, email="pt@example.com", role=Role.PT)
        second_pt_user = _create_user(db, email="pt-2@example.com", role=Role.PT)
        client_user = _create_user(db, email="client@example.com", role=Role.CLIENT)
        second_client_user = _create_user(db, email="client-2@example.com", role=Role.CLIENT)
        meal_plan_a = _create_meal_plan(db, slug="alpha")
        meal_plan_b = _create_meal_plan(db, slug="beta")
        meal_plan_c = _create_meal_plan(db, slug="gamma")

        recommendation_a = recommendation_repo.create_recommendation(
            db,
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan_a.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="Newest for scoped pair",
            recommended_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            expires_at=None,
        )
        recommendation_b = recommendation_repo.create_recommendation(
            db,
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan_b.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="Older for scoped pair",
            recommended_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            expires_at=None,
        )
        recommendation_c = recommendation_repo.create_recommendation(
            db,
            pt_user_id=second_pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan_c.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="Different PT",
            recommended_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
            expires_at=None,
        )
        recommendation_d = recommendation_repo.create_recommendation(
            db,
            pt_user_id=pt_user.id,
            client_user_id=second_client_user.id,
            meal_plan_id=meal_plan_c.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="Different client",
            recommended_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
            expires_at=None,
        )
        db.commit()

        fetched = recommendation_repo.get_recommendation_by_id(
            db,
            recommendation_id=recommendation_a.id,
        )
        assert fetched is not None
        assert fetched.meal_plan.slug == "alpha"

        assert [
            recommendation.id
            for recommendation in recommendation_repo.list_recommendations_for_pt_client(
                db,
                pt_user_id=pt_user.id,
                client_user_id=client_user.id,
            )
        ] == [recommendation_a.id, recommendation_b.id]

        assert [
            recommendation.id
            for recommendation in recommendation_repo.list_recommendations_for_client(
                db,
                client_user_id=client_user.id,
            )
        ] == [recommendation_a.id, recommendation_b.id, recommendation_c.id]

        assert [
            recommendation.id
            for recommendation in recommendation_repo.list_recommendations_for_pt(
                db,
                pt_user_id=pt_user.id,
            )
        ] == [recommendation_a.id, recommendation_b.id, recommendation_d.id]

        assert recommendation_b.status == MealPlanRecommendationStatus.ACTIVE
        recommendation_b.status = MealPlanRecommendationStatus.WITHDRAWN
        recommendation_repo.save_recommendation(db, recommendation_b)
        db.commit()
        db.refresh(recommendation_b)
        assert recommendation_b.status == MealPlanRecommendationStatus.WITHDRAWN


def test_recommendation_repo_breaks_recommended_at_ties_deterministically() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt_user = _create_user(db, email="tie-pt@example.com", role=Role.PT)
        client_user = _create_user(db, email="tie-client@example.com", role=Role.CLIENT)
        meal_plan_a = _create_meal_plan(db, slug="tie-a")
        meal_plan_b = _create_meal_plan(db, slug="tie-b")
        timestamp = datetime(2026, 3, 16, 18, 0, tzinfo=UTC)

        first = recommendation_repo.create_recommendation(
            db,
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan_a.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="first",
            recommended_at=timestamp,
            expires_at=None,
        )
        second = recommendation_repo.create_recommendation(
            db,
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan_b.id,
            status=MealPlanRecommendationStatus.ACTIVE,
            rationale="second",
            recommended_at=timestamp,
            expires_at=None,
        )
        db.commit()

        ordered = recommendation_repo.list_recommendations_for_pt_client(
            db,
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
        )

        assert len(ordered) == 2
        assert {ordered[0].id, ordered[1].id} == {first.id, second.id}
        assert ordered[0].recommended_at.replace(tzinfo=UTC) == timestamp
        assert ordered[1].recommended_at.replace(tzinfo=UTC) == timestamp
        assert ordered[0].id != ordered[1].id
