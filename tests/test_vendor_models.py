import importlib.util
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
from mealmetric.models.user import User
from mealmetric.models.vendor import (
    MealPlan,
    MealPlanAvailability,
    MealPlanAvailabilityStatus,
    MealPlanItem,
    MealPlanStatus,
    Vendor,
    VendorMenuItem,
    VendorMenuItemStatus,
    VendorPickupWindow,
    VendorPickupWindowStatus,
    VendorStatus,
)


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


def _create_vendor(db: Session, *, slug: str) -> Vendor:
    vendor = Vendor(slug=slug, name=f"Vendor {slug}")
    db.add(vendor)
    db.flush()
    return vendor


def test_phase_j_vendor_migration_lineage_and_upgrade_downgrade() -> None:
    module = cast(
        Any,
        _load_migration_module(
            "1c2d4e6f8a9b_add_phase_j_vendor_domain_schema.py",
            "phase_j_vendor_domain",
        ),
    )

    assert set(module.down_revision) == {"b91f4f3b2c8d", "9f3a2d7c1b4e"}

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

        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

        inspector = sa.inspect(conn)
        expected_tables = {
            "vendors",
            "vendor_menu_items",
            "meal_plans",
            "meal_plan_items",
            "vendor_pickup_windows",
            "meal_plan_availability",
        }
        assert expected_tables.issubset(set(inspector.get_table_names()))

        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()

        remaining_tables = set(sa.inspect(conn).get_table_names())
        assert expected_tables.isdisjoint(remaining_tables)


def test_vendor_tables_registered_in_metadata() -> None:
    expected_tables = {
        "vendors",
        "vendor_menu_items",
        "meal_plans",
        "meal_plan_items",
        "vendor_pickup_windows",
        "meal_plan_availability",
    }
    assert expected_tables.issubset(set(Base.metadata.tables))


def test_vendor_slug_and_meal_plan_position_uniqueness_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        first_vendor = Vendor(slug="alpha", name="Alpha")
        second_vendor = Vendor(slug="alpha", name="Duplicate Alpha")
        db.add(first_vendor)
        db.commit()

        db.add(second_vendor)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        vendor = _create_vendor(db, slug="beta")
        menu_item_a = VendorMenuItem(
            vendor_id=vendor.id,
            slug="chicken-bowl",
            name="Chicken Bowl",
            price_cents=1299,
        )
        menu_item_b = VendorMenuItem(
            vendor_id=vendor.id,
            slug="salad-bowl",
            name="Salad Bowl",
            price_cents=1099,
        )
        meal_plan = MealPlan(vendor_id=vendor.id, slug="lean-week", name="Lean Week")
        db.add_all([menu_item_a, menu_item_b, meal_plan])
        db.flush()

        first_item = MealPlanItem(
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item_a.id,
            quantity=1,
            position=0,
        )
        db.add(first_item)
        db.commit()

        duplicate_position = MealPlanItem(
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item_b.id,
            quantity=1,
            position=0,
        )
        db.add(duplicate_position)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_meal_plan_item_vendor_pairing_is_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor_a = _create_vendor(db, slug="vendor-a")
        vendor_b = _create_vendor(db, slug="vendor-b")
        meal_plan = MealPlan(vendor_id=vendor_a.id, slug="vendor-a-plan", name="Vendor A Plan")
        menu_item = VendorMenuItem(
            vendor_id=vendor_b.id,
            slug="vendor-b-item",
            name="Vendor B Item",
            price_cents=1399,
        )
        db.add_all([meal_plan, menu_item])
        db.flush()

        mismatched_item = MealPlanItem(
            vendor_id=vendor_a.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item.id,
            quantity=1,
            position=0,
        )
        db.add(mismatched_item)

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_meal_plan_availability_vendor_pairing_and_uniqueness_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor_a = _create_vendor(db, slug="availability-a")
        vendor_b = _create_vendor(db, slug="availability-b")
        meal_plan = MealPlan(vendor_id=vendor_a.id, slug="plan-a", name="Plan A")
        pickup_window_a = VendorPickupWindow(
            vendor_id=vendor_a.id,
            label="Friday PM",
            pickup_start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            pickup_end_at=datetime(2026, 3, 20, 19, 0, tzinfo=UTC),
        )
        pickup_window_b = VendorPickupWindow(
            vendor_id=vendor_b.id,
            label="Friday PM Other",
            pickup_start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            pickup_end_at=datetime(2026, 3, 20, 19, 0, tzinfo=UTC),
        )
        db.add_all([meal_plan, pickup_window_a, pickup_window_b])
        db.flush()

        availability = MealPlanAvailability(
            vendor_id=vendor_a.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window_a.id,
        )
        db.add(availability)
        db.commit()

        duplicate = MealPlanAvailability(
            vendor_id=vendor_a.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window_a.id,
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        mismatched = MealPlanAvailability(
            vendor_id=vendor_a.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window_b.id,
        )
        db.add(mismatched)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_vendor_domain_enum_defaults() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="defaults")
        menu_item = VendorMenuItem(
            vendor_id=vendor.id,
            slug="default-item",
            name="Default Item",
            price_cents=999,
        )
        meal_plan = MealPlan(vendor_id=vendor.id, slug="default-plan", name="Default Plan")
        pickup_window = VendorPickupWindow(
            vendor_id=vendor.id,
            label="Saturday AM",
            pickup_start_at=datetime(2026, 3, 21, 9, 0, tzinfo=UTC),
            pickup_end_at=datetime(2026, 3, 21, 11, 0, tzinfo=UTC),
        )
        db.add_all([menu_item, meal_plan, pickup_window])
        db.flush()

        availability = MealPlanAvailability(
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
        )
        db.add(availability)
        db.commit()

        db.refresh(vendor)
        db.refresh(menu_item)
        db.refresh(meal_plan)
        db.refresh(pickup_window)
        db.refresh(availability)

        assert vendor.status == VendorStatus.DRAFT
        assert menu_item.status == VendorMenuItemStatus.DRAFT
        assert meal_plan.status == MealPlanStatus.DRAFT
        assert pickup_window.status == VendorPickupWindowStatus.SCHEDULED
        assert availability.status == MealPlanAvailabilityStatus.SCHEDULED


def test_vendor_domain_check_constraints_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="checks")
        db.commit()

        bad_menu_item = VendorMenuItem(
            vendor_id=vendor.id,
            slug="bad-price",
            name="Bad Price",
            price_cents=-1,
        )
        db.add(bad_menu_item)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        bad_pickup_window = VendorPickupWindow(
            vendor_id=vendor.id,
            label="Bad Window",
            pickup_start_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            pickup_end_at=datetime(2026, 3, 22, 11, 0, tzinfo=UTC),
        )
        db.add(bad_pickup_window)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        good_meal_plan = MealPlan(vendor_id=vendor.id, slug="good-plan", name="Good Plan")
        good_pickup_window = VendorPickupWindow(
            vendor_id=vendor.id,
            label="Good Window",
            pickup_start_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            pickup_end_at=datetime(2026, 3, 22, 13, 0, tzinfo=UTC),
        )
        db.add_all([good_meal_plan, good_pickup_window])
        db.flush()

        bad_availability = MealPlanAvailability(
            vendor_id=vendor.id,
            meal_plan_id=good_meal_plan.id,
            pickup_window_id=good_pickup_window.id,
            inventory_count=-5,
        )
        db.add(bad_availability)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_existing_user_model_still_registers_with_vendor_metadata() -> None:
    assert "users" in Base.metadata.tables
    assert User.__tablename__ == "users"
