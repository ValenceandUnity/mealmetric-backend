import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.recommendation import MealPlanRecommendation, MealPlanRecommendationStatus
from mealmetric.models.user import Role, User
from mealmetric.models.vendor import MealPlan, Vendor


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _load_migration_module(filename: str, module_name: str) -> object:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recommendation_migration_lineage_and_upgrade_downgrade() -> None:
    module = cast(
        Any,
        _load_migration_module(
            "4a7c9e1d2b3f_add_pt_meal_plan_recommendations.py",
            "phase_j5_recommendations",
        ),
    )

    assert module.down_revision == "1c2d4e6f8a9b"

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id UUID NOT NULL PRIMARY KEY,
                    email VARCHAR NOT NULL,
                    password_hash VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE meal_plans (
                    id UUID NOT NULL PRIMARY KEY,
                    vendor_id UUID NOT NULL,
                    slug VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

        inspector = sa.inspect(conn)
        assert "pt_meal_plan_recommendations" in inspector.get_table_names()
        index_names = {
            index["name"] for index in inspector.get_indexes("pt_meal_plan_recommendations")
        }
        assert {
            "ix_pt_meal_plan_recommendations_pt_user_id",
            "ix_pt_meal_plan_recommendations_client_user_id",
            "ix_pt_meal_plan_recommendations_meal_plan_id",
            "ix_pt_meal_plan_recommendations_status",
            "ix_pt_meal_plan_recommendations_recommended_at",
            "ix_pt_meal_plan_recommendations_pt_client_order",
            "ix_pt_meal_plan_recommendations_client_order",
        }.issubset(index_names)

        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()

        assert "pt_meal_plan_recommendations" not in sa.inspect(conn).get_table_names()


def test_recommendation_table_registered_in_metadata() -> None:
    assert "pt_meal_plan_recommendations" in Base.metadata.tables


def test_recommendation_model_defaults_and_relationships() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt_user = User(email="pt@example.com", password_hash="hash", role=Role.PT)
        client_user = User(email="client@example.com", password_hash="hash", role=Role.CLIENT)
        vendor = Vendor(slug="alpha", name="Alpha")
        db.add_all([pt_user, client_user, vendor])
        db.flush()

        meal_plan = MealPlan(vendor_id=vendor.id, slug="lean-pack", name="Lean Pack")
        db.add(meal_plan)
        db.flush()

        recommendation = MealPlanRecommendation(
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan.id,
            recommended_at=datetime(2026, 3, 16, 21, 10, tzinfo=UTC),
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)

        assert recommendation.status == MealPlanRecommendationStatus.ACTIVE
        assert recommendation.meal_plan.id == meal_plan.id
        assert recommendation.created_at is not None
        assert recommendation.updated_at is not None


def test_recommendation_explicit_status_persists() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt_user = User(email="pt2@example.com", password_hash="hash", role=Role.PT)
        client_user = User(email="client2@example.com", password_hash="hash", role=Role.CLIENT)
        vendor = Vendor(slug="beta", name="Beta")
        db.add_all([pt_user, client_user, vendor])
        db.flush()

        meal_plan = MealPlan(vendor_id=vendor.id, slug="recovery-pack", name="Recovery Pack")
        db.add(meal_plan)
        db.flush()

        recommendation = MealPlanRecommendation(
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=meal_plan.id,
            status=MealPlanRecommendationStatus.WITHDRAWN,
            recommended_at=datetime(2026, 3, 16, 21, 20, tzinfo=UTC),
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)

        assert recommendation.status == MealPlanRecommendationStatus.WITHDRAWN


def test_recommendation_requires_existing_meal_plan() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt_user = User(email="pt3@example.com", password_hash="hash", role=Role.PT)
        client_user = User(email="client3@example.com", password_hash="hash", role=Role.CLIENT)
        db.add_all([pt_user, client_user])
        db.flush()

        recommendation = MealPlanRecommendation(
            pt_user_id=pt_user.id,
            client_user_id=client_user.id,
            meal_plan_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            recommended_at=datetime(2026, 3, 16, 21, 30, tzinfo=UTC),
        )
        db.add(recommendation)

        with pytest.raises(IntegrityError):
            db.commit()
