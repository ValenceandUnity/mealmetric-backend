import uuid
from datetime import UTC, date, datetime

import pytest
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
from mealmetric.services.vendor_service import VendorService


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


def test_vendor_service_empty_states_are_stable() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        service = VendorService(db)

        vendor_list = service.list_vendors()
        assert vendor_list.count == 0
        assert vendor_list.items == ()

        meal_plan_list = service.list_meal_plans()
        assert meal_plan_list.count == 0
        assert meal_plan_list.items == ()
        assert meal_plan_list.vendor_id is None

        availability = service.list_meal_plan_availability()
        assert availability == ()


def test_vendor_service_list_and_detail_are_deterministic_and_discoverable_only() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="alpha", name="Alpha Vendor")
        hidden_vendor = _create_vendor(
            db,
            slug="hidden",
            name="Hidden Vendor",
            status=VendorStatus.INACTIVE,
        )

        menu_item_a = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="salmon-box",
            price_cents=1400,
            calories=600,
        )
        menu_item_b = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="greens-box",
            price_cents=900,
            calories=300,
        )
        hidden_menu_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="hidden-box",
            price_cents=700,
            calories=200,
            status=VendorMenuItemStatus.ARCHIVED,
        )
        hidden_vendor_item = _create_menu_item(
            db,
            vendor_id=hidden_vendor.id,
            slug="hidden-vendor-item",
            price_cents=1000,
            calories=400,
        )

        visible_plan = _create_meal_plan(
            db, vendor_id=vendor.id, slug="lean-pack", name="Lean Pack"
        )
        second_plan = _create_meal_plan(
            db,
            vendor_id=vendor.id,
            slug="recovery-pack",
            name="Recovery Pack",
        )
        hidden_plan = _create_meal_plan(
            db,
            vendor_id=vendor.id,
            slug="hidden-pack",
            name="Hidden Pack",
        )
        _create_meal_plan(
            db,
            vendor_id=vendor.id,
            slug="draft-pack",
            name="Draft Pack",
            status=MealPlanStatus.DRAFT,
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
            meal_plan_id=visible_plan.id,
            vendor_menu_item_id=menu_item_b.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=visible_plan.id,
            vendor_menu_item_id=menu_item_a.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=second_plan.id,
            vendor_menu_item_id=menu_item_b.id,
            position=0,
            quantity=2,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=hidden_plan.id,
            vendor_menu_item_id=menu_item_a.id,
            position=0,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=hidden_plan.id,
            vendor_menu_item_id=hidden_menu_item.id,
            position=1,
        )
        _create_meal_plan_item(
            db,
            vendor_id=hidden_vendor.id,
            meal_plan_id=hidden_vendor_plan.id,
            vendor_menu_item_id=hidden_vendor_item.id,
            position=0,
        )

        friday_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 20, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 20, 18, 0, tzinfo=UTC),
            label="Friday Pickup",
        )
        saturday_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 21, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 21, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.OPEN,
            label="Saturday Pickup",
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
            meal_plan_id=visible_plan.id,
            pickup_window_id=friday_window.id,
            inventory_count=4,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=visible_plan.id,
            pickup_window_id=saturday_window.id,
            status=MealPlanAvailabilityStatus.SCHEDULED,
            inventory_count=None,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=second_plan.id,
            pickup_window_id=saturday_window.id,
            inventory_count=3,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=hidden_plan.id,
            pickup_window_id=friday_window.id,
            inventory_count=2,
        )
        _create_availability(
            db,
            vendor_id=hidden_vendor.id,
            meal_plan_id=hidden_vendor_plan.id,
            pickup_window_id=hidden_window.id,
            inventory_count=2,
        )
        db.commit()

        service = VendorService(db)

        vendor_list = service.list_vendors()
        assert vendor_list.count == 1
        assert [item.slug for item in vendor_list.items] == ["alpha"]
        assert vendor_list.items[0].meal_plan_count == 2

        vendor_detail = service.get_vendor_detail(vendor_id=vendor.id)
        assert vendor_detail is not None
        assert vendor_detail.meal_plan_count == 2
        assert [item.slug for item in vendor_detail.meal_plans] == ["lean-pack", "recovery-pack"]

        hidden_vendor_detail = service.get_vendor_detail(vendor_id=hidden_vendor.id)
        assert hidden_vendor_detail is None


def test_meal_plan_detail_composes_items_availability_and_totals() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="vendor", name="Vendor")
        protein = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="protein",
            price_cents=1300,
            calories=550,
        )
        veggie = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="veggie",
            price_cents=700,
            calories=250,
        )
        meal_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="plan", name="Plan")
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=protein.id,
            position=0,
            quantity=2,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=veggie.id,
            position=1,
            quantity=1,
        )
        pickup_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 22, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 22, 18, 0, tzinfo=UTC),
            label="Sunday Pickup",
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
            inventory_count=6,
        )
        db.commit()

        service = VendorService(db)
        detail = service.get_meal_plan_detail(meal_plan_id=meal_plan.id)

        assert detail is not None
        assert detail.item_count == 2
        assert detail.availability_count == 1
        assert [item.slug for item in detail.items] == ["protein", "veggie"]
        assert detail.total_price_cents == 3300
        assert detail.total_calories == 1350
        assert detail.availability[0].pickup_window_label == "Sunday Pickup"
        assert detail.availability[0].pickup_window_status == "scheduled"


def test_service_list_meal_plans_empty_and_filtered_states_are_stable() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="vendor", name="Vendor")
        menu_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="item",
            price_cents=1000,
            calories=450,
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
            start_at=datetime(2026, 3, 24, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 24, 18, 0, tzinfo=UTC),
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
            inventory_count=2,
        )
        db.commit()

        service = VendorService(db)

        empty = service.list_meal_plans(calorie_min=9999)
        assert empty.count == 0
        assert empty.items == ()

        filtered = service.list_meal_plans(
            vendor_id=vendor.id,
            calorie_min=400,
            calorie_max=500,
            price_min_cents=900,
            price_max_cents=1200,
            available_on=date(2026, 3, 24),
            pickup_window_id=pickup_window.id,
        )
        assert filtered.count == 1
        assert filtered.items[0].slug == "plan"
        assert filtered.items[0].total_price_cents == 1000
        assert filtered.items[0].total_calories == 450


def test_internal_non_discoverable_read_path_is_explicit_and_scoped() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(
            db,
            slug="internal",
            name="Internal Vendor",
            status=VendorStatus.INACTIVE,
        )
        menu_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="internal-item",
            price_cents=800,
            calories=300,
            status=VendorMenuItemStatus.ARCHIVED,
        )
        meal_plan = _create_meal_plan(
            db,
            vendor_id=vendor.id,
            slug="internal-plan",
            name="Internal Plan",
            status=MealPlanStatus.DRAFT,
        )
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
            start_at=datetime(2026, 3, 25, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 25, 18, 0, tzinfo=UTC),
            status=VendorPickupWindowStatus.CLOSED,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
            status=MealPlanAvailabilityStatus.SOLD_OUT,
            inventory_count=0,
        )
        db.commit()

        service = VendorService(db)

        assert service.get_vendor_detail(vendor_id=vendor.id) is None
        assert service.get_meal_plan_detail(meal_plan_id=meal_plan.id) is None

        internal_vendor = service.get_vendor_detail(vendor_id=vendor.id, discoverable_only=False)
        internal_plan = service.get_meal_plan_detail(
            meal_plan_id=meal_plan.id,
            discoverable_only=False,
        )

        assert internal_vendor is not None
        assert internal_vendor.status == VendorStatus.INACTIVE
        assert internal_vendor.meal_plan_count == 1

        assert internal_plan is not None
        assert internal_plan.status == MealPlanStatus.DRAFT
        assert internal_plan.item_count == 1
        assert internal_plan.availability_count == 1
        assert (
            internal_plan.availability[0].availability_status == MealPlanAvailabilityStatus.SOLD_OUT
        )


def test_list_vendors_does_not_delegate_to_recursive_meal_plan_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="alpha", name="Alpha Vendor")
        menu_item = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="item",
            price_cents=1200,
            calories=500,
        )
        meal_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="plan", name="Plan")
        pickup_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 26, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 26, 18, 0, tzinfo=UTC),
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item.id,
            position=0,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
            inventory_count=5,
        )
        db.commit()

        service = VendorService(db)

        def _fail_list_meal_plans(*args: object, **kwargs: object) -> object:
            raise AssertionError("list_vendors should not call service.list_meal_plans")

        monkeypatch.setattr(service, "list_meal_plans", _fail_list_meal_plans)

        vendor_list = service.list_vendors()
        assert vendor_list.count == 1
        assert vendor_list.items[0].meal_plan_count == 1


def test_list_meal_plans_does_not_delegate_to_detail_recomposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        vendor = _create_vendor(db, slug="alpha", name="Alpha Vendor")
        menu_item_a = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="a",
            price_cents=1000,
            calories=400,
        )
        menu_item_b = _create_menu_item(
            db,
            vendor_id=vendor.id,
            slug="b",
            price_cents=700,
            calories=250,
        )
        meal_plan = _create_meal_plan(db, vendor_id=vendor.id, slug="plan", name="Plan")
        pickup_window = _create_pickup_window(
            db,
            vendor_id=vendor.id,
            start_at=datetime(2026, 3, 27, 17, 0, tzinfo=UTC),
            end_at=datetime(2026, 3, 27, 18, 0, tzinfo=UTC),
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item_a.id,
            position=0,
            quantity=2,
        )
        _create_meal_plan_item(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            vendor_menu_item_id=menu_item_b.id,
            position=1,
            quantity=1,
        )
        _create_availability(
            db,
            vendor_id=vendor.id,
            meal_plan_id=meal_plan.id,
            pickup_window_id=pickup_window.id,
            inventory_count=3,
        )
        db.commit()

        service = VendorService(db)

        def _fail_get_detail(*args: object, **kwargs: object) -> object:
            raise AssertionError("list_meal_plans should not call get_meal_plan_detail")

        monkeypatch.setattr(service, "get_meal_plan_detail", _fail_get_detail)

        meal_plan_list = service.list_meal_plans(vendor_id=vendor.id)
        assert meal_plan_list.count == 1
        assert meal_plan_list.items[0].total_price_cents == 2700
        assert meal_plan_list.items[0].total_calories == 1050
        assert meal_plan_list.items[0].item_count == 2
        assert meal_plan_list.items[0].availability_count == 1
