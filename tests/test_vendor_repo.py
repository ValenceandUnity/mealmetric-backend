import uuid
from datetime import UTC, date, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
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
from mealmetric.repos import vendor_repo


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _create_vendor(
    db: Session,
    *,
    slug: str,
    name: str,
    status: VendorStatus = VendorStatus.ACTIVE,
) -> Vendor:
    vendor = Vendor(slug=slug, name=name, status=status)
    db.add(vendor)
    db.flush()
    return vendor


def _create_menu_item(
    db: Session,
    *,
    vendor_id: uuid.UUID,
    slug: str,
    price_cents: int,
    calories: int,
    status: VendorMenuItemStatus = VendorMenuItemStatus.ACTIVE,
) -> VendorMenuItem:
    menu_item = VendorMenuItem(
        vendor_id=vendor_id,
        slug=slug,
        name=slug.replace("-", " ").title(),
        price_cents=price_cents,
        calories=calories,
        status=status,
    )
    db.add(menu_item)
    db.flush()
    return menu_item


def _create_meal_plan(
    db: Session,
    *,
    vendor_id: uuid.UUID,
    slug: str,
    name: str,
    status: MealPlanStatus = MealPlanStatus.PUBLISHED,
) -> MealPlan:
    meal_plan = MealPlan(vendor_id=vendor_id, slug=slug, name=name, status=status)
    db.add(meal_plan)
    db.flush()
    return meal_plan


def _create_meal_plan_item(
    db: Session,
    *,
    vendor_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    vendor_menu_item_id: uuid.UUID,
    position: int,
    quantity: int = 1,
) -> MealPlanItem:
    item = MealPlanItem(
        vendor_id=vendor_id,
        meal_plan_id=meal_plan_id,
        vendor_menu_item_id=vendor_menu_item_id,
        quantity=quantity,
        position=position,
    )
    db.add(item)
    db.flush()
    return item


def _create_pickup_window(
    db: Session,
    *,
    vendor_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    status: VendorPickupWindowStatus = VendorPickupWindowStatus.SCHEDULED,
    label: str = "Window",
) -> VendorPickupWindow:
    pickup_window = VendorPickupWindow(
        vendor_id=vendor_id,
        label=label,
        pickup_start_at=start_at,
        pickup_end_at=end_at,
        status=status,
    )
    db.add(pickup_window)
    db.flush()
    return pickup_window


def _create_availability(
    db: Session,
    *,
    vendor_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    pickup_window_id: uuid.UUID,
    status: MealPlanAvailabilityStatus = MealPlanAvailabilityStatus.AVAILABLE,
    inventory_count: int | None = None,
) -> MealPlanAvailability:
    availability = MealPlanAvailability(
        vendor_id=vendor_id,
        meal_plan_id=meal_plan_id,
        pickup_window_id=pickup_window_id,
        status=status,
        inventory_count=inventory_count,
    )
    db.add(availability)
    db.flush()
    return availability


def test_list_vendors_defaults_to_discoverable_only_with_deterministic_ordering() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        _create_vendor(db, slug="archived", name="Archived Vendor", status=VendorStatus.ARCHIVED)
        _create_vendor(db, slug="beta", name="Beta Vendor")
        _create_vendor(db, slug="alpha", name="Alpha Vendor")
        db.commit()

        vendors = vendor_repo.list_vendors(db)

        assert [vendor.slug for vendor in vendors] == ["alpha", "beta"]


def test_get_vendor_by_id_respects_discoverable_flag() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        hidden_vendor = _create_vendor(
            db,
            slug="hidden",
            name="Hidden Vendor",
            status=VendorStatus.INACTIVE,
        )
        db.commit()

        assert vendor_repo.get_vendor_by_id(db, vendor_id=hidden_vendor.id) is None
        assert (
            vendor_repo.get_vendor_by_id(
                db,
                vendor_id=hidden_vendor.id,
                discoverable_only=False,
            )
            is not None
        )


def test_list_meal_plans_filters_to_discoverable_catalog_and_orders_deterministically() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="vendor", name="Vendor")
        hidden_vendor = _create_vendor(
            db,
            slug="hidden-vendor",
            name="Hidden Vendor",
            status=VendorStatus.INACTIVE,
        )

        active_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="active-item",
            price_cents=1200,
            calories=500,
        )
        second_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="second-item",
            price_cents=800,
            calories=300,
        )
        hidden_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="hidden-item",
            price_cents=999,
            calories=250,
            status=VendorMenuItemStatus.ARCHIVED,
        )
        hidden_vendor_item = _create_menu_item(
            db,
            vendor_id=hidden_vendor.id,
            slug="vendor-hidden-item",
            price_cents=1000,
            calories=400,
        )

        breakfast = _create_meal_plan(db, vendor_id=vendor.id, slug="breakfast", name="Breakfast")
        dinner = _create_meal_plan(db, vendor_id=vendor.id, slug="dinner", name="Dinner")
        draft_plan = _create_meal_plan(
            db,
            vendor_id=vendor.id,
            slug="draft",
            name="Draft",
            status=MealPlanStatus.DRAFT,
        )
        partial_hidden = _create_meal_plan(
            db,
            vendor_id=vendor.id,
            slug="partial-hidden",
            name="Partial Hidden",
        )
        hidden_vendor_plan = _create_meal_plan(
            db,
            vendor_id=hidden_vendor.id,
            slug="hidden-vendor-plan",
            name="Hidden Vendor Plan",
        )

        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=breakfast.id,
            vendor_menu_item_id=active_item.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=breakfast.id,
            vendor_menu_item_id=second_item.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=dinner.id,
            vendor_menu_item_id=second_item.id,
            position=0,
            quantity=2,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=partial_hidden.id,
            vendor_menu_item_id=active_item.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=partial_hidden.id,
            vendor_menu_item_id=hidden_item.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=hidden_vendor.id,
            meal_plan_id=hidden_vendor_plan.id,
            vendor_menu_item_id=hidden_vendor_item.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=draft_plan.id,
            vendor_menu_item_id=active_item.id,
            position=0,
        )

        breakfast_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
            label="Friday PM",
        )
        dinner_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 21, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 21, 18, 0, tzinfo=UTC),
            label="Saturday PM",
        )
        hidden_window = _create_pickup_window(
            db,
            vendor_id=hidden_vendor.id,
            start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
            label="Hidden Window",
        )

        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=breakfast.id,
            pickup_window_id=breakfast_window.id,
            status=MealPlanAvailabilityStatus.AVAILABLE,
            inventory_count=5,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=dinner.id,
            pickup_window_id=dinner_window.id,
            status=MealPlanAvailabilityStatus.SCHEDULED,
            inventory_count=None,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=partial_hidden.id,
            pickup_window_id=breakfast_window.id,
            status=MealPlanAvailabilityStatus.AVAILABLE,
            inventory_count=5,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=draft_plan.id,
            pickup_window_id=breakfast_window.id,
            status=MealPlanAvailabilityStatus.AVAILABLE,
            inventory_count=5,
        )
        _create_availability(
            db,
            vendor_id=hidden_vendor.id,
            meal_plan_id=hidden_vendor_plan.id,
            pickup_window_id=hidden_window.id,
            status=MealPlanAvailabilityStatus.AVAILABLE,
            inventory_count=5,
        )
        db.commit()

        meal_plans = vendor_repo.list_meal_plans(db)
        assert [meal_plan.slug for meal_plan in meal_plans] == ["breakfast", "dinner"]

        filtered = vendor_repo.list_meal_plans(
            db,
            vendor_id=vendor.id,
            calorie_min=700,
            calorie_max=900,
            price_min_cents=1800,
            price_max_cents=2500,
            available_on=date(2026, 3, 20),
        )
        assert [meal_plan.slug for meal_plan in filtered] == ["breakfast"]

        saturday_only = vendor_repo.list_meal_plans(
            db,
            vendor_id=vendor.id,
            pickup_window_id=dinner_window.id,
        )
        assert [meal_plan.slug for meal_plan in saturday_only] == ["dinner"]


def test_get_meal_plan_by_id_does_not_leak_non_discoverable_plan() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="vendor", name="Vendor")
        menu_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="item",
            price_cents=1200,
            calories=500,
            status=VendorMenuItemStatus.ARCHIVED,
        )
        meal_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="plan", name="Plan")
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item.id,
            position=0,
        )
        pickup_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
        )
        db.commit()

        assert vendor_repo.get_meal_plan_by_id(db, meal_plan_id=meal_plan.id) is None
        assert (
            vendor_repo.get_meal_plan_by_id(
                db,
                meal_plan_id=meal_plan.id,
                discoverable_only=False,
            )
            is not None
        )


def test_list_meal_plan_items_returns_deterministic_positions_and_hides_hidden_items() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="vendor", name="Vendor")
        active_a = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="a",
            price_cents=1000,
            calories=400,
        )
        active_b = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="b",
            price_cents=1100,
            calories=500,
        )
        hidden = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="hidden",
            price_cents=900,
            calories=300,
            status=VendorMenuItemStatus.INACTIVE,
        )
        safe_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="safe", name="Safe")
        hidden_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="hidden-plan", name="Hidden")
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=safe_plan.id,
            vendor_menu_item_id=active_b.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=safe_plan.id,
            vendor_menu_item_id=active_a.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=hidden_plan.id,
            vendor_menu_item_id=active_a.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=hidden_plan.id,
            vendor_menu_item_id=hidden.id,
            position=1,
        )
        pickup_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=safe_plan.id,
            pickup_window_id=pickup_window.id,
            inventory_count=3,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=hidden_plan.id,
            pickup_window_id=pickup_window.id,
            inventory_count=3,
        )
        db.commit()

        safe_items = vendor_repo.list_meal_plan_items(db, meal_plan_id=safe_plan.id)
        assert [item.position for item in safe_items] == [0, 1]
        assert [item.vendor_menu_item_id for item in safe_items] == [active_a.id, active_b.id]

        hidden_items = vendor_repo.list_meal_plan_items(db, meal_plan_id=hidden_plan.id)
        assert hidden_items == []


def test_pickup_window_and_availability_helpers_exclude_unavailable_rows_predictably() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="vendor", name="Vendor")
        menu_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="item",
            price_cents=1200,
            calories=500,
        )
        meal_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="plan", name="Plan")
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item.id,
            position=0,
        )

        discoverable_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 24, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 24, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.OPEN,
            label="Open Window",
        )
        closed_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 25, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 25, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.CLOSED,
            label="Closed Window",
        )
        sold_out_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 26, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 26, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.SCHEDULED,
            label="Sold Out Window",
        )

        visible_availability = _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=discoverable_window.id,
            status=MealPlanAvailabilityStatus.AVAILABLE,
            inventory_count=4,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=closed_window.id,
            status=MealPlanAvailabilityStatus.AVAILABLE,
            inventory_count=4,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=sold_out_window.id,
            status=MealPlanAvailabilityStatus.SOLD_OUT,
            inventory_count=0,
        )
        db.commit()

        pickup_windows = vendor_repo.list_vendor_pickup_windows(
            db,
            meal_plan_id=meal_plan.id,
        )
        assert [window.id for window in pickup_windows] == [discoverable_window.id]

        filtered_windows = vendor_repo.list_vendor_pickup_windows(
            db,
            vendor_id=vendor.id,
            available_on=date(2026, 3, 24),
        )
        assert [window.id for window in filtered_windows] == [discoverable_window.id]

        availability_rows = vendor_repo.list_meal_plan_availability(
            db,
            meal_plan_id=meal_plan.id,
        )
        assert [row.id for row in availability_rows] == [visible_availability.id]

        day_filtered = vendor_repo.list_meal_plan_availability(
            db,
            vendor_id=vendor.id,
            available_on=date(2026, 3, 24),
        )
        assert [row.id for row in day_filtered] == [visible_availability.id]
