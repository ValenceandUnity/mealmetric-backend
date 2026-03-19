import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

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

_DISCOVERABLE_VENDOR_STATUS = VendorStatus.ACTIVE
_DISCOVERABLE_MEAL_PLAN_STATUS = MealPlanStatus.PUBLISHED
_DISCOVERABLE_MENU_ITEM_STATUS = VendorMenuItemStatus.ACTIVE
_DISCOVERABLE_PICKUP_WINDOW_STATUSES = (
    VendorPickupWindowStatus.SCHEDULED,
    VendorPickupWindowStatus.OPEN,
)
_DISCOVERABLE_AVAILABILITY_STATUSES = (
    MealPlanAvailabilityStatus.SCHEDULED,
    MealPlanAvailabilityStatus.AVAILABLE,
)


def _meal_plan_totals_subquery(*, discoverable_only: bool) -> Subquery:
    stmt = (
        select(
            MealPlanItem.meal_plan_id.label("meal_plan_id"),
            func.coalesce(
                func.sum(VendorMenuItem.price_cents * MealPlanItem.quantity),
                0,
            ).label("total_price_cents"),
            func.coalesce(
                func.sum(func.coalesce(VendorMenuItem.calories, 0) * MealPlanItem.quantity),
                0,
            ).label("total_calories"),
        )
        .join(VendorMenuItem, VendorMenuItem.id == MealPlanItem.vendor_menu_item_id)
        .group_by(MealPlanItem.meal_plan_id)
    )
    if discoverable_only:
        stmt = stmt.where(VendorMenuItem.status == _DISCOVERABLE_MENU_ITEM_STATUS)
    return stmt.subquery()


def _meal_plan_has_any_items() -> ColumnElement[bool]:
    return exists(
        select(1).select_from(MealPlanItem).where(MealPlanItem.meal_plan_id == MealPlan.id)
    )


def _meal_plan_has_hidden_items() -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(MealPlanItem)
        .join(VendorMenuItem, VendorMenuItem.id == MealPlanItem.vendor_menu_item_id)
        .where(
            MealPlanItem.meal_plan_id == MealPlan.id,
            VendorMenuItem.status != _DISCOVERABLE_MENU_ITEM_STATUS,
        )
    )


def _discoverable_availability_exists(
    *,
    available_on: date | None = None,
    pickup_window_id: uuid.UUID | None = None,
) -> ColumnElement[bool]:
    stmt = (
        select(1)
        .select_from(MealPlanAvailability)
        .join(VendorPickupWindow, VendorPickupWindow.id == MealPlanAvailability.pickup_window_id)
        .where(
            MealPlanAvailability.meal_plan_id == MealPlan.id,
            MealPlanAvailability.status.in_(_DISCOVERABLE_AVAILABILITY_STATUSES),
            VendorPickupWindow.status.in_(_DISCOVERABLE_PICKUP_WINDOW_STATUSES),
            or_(
                MealPlanAvailability.inventory_count.is_(None),
                MealPlanAvailability.inventory_count > 0,
            ),
        )
    )
    if available_on is not None:
        stmt = stmt.where(func.date(VendorPickupWindow.pickup_start_at) == available_on)
    if pickup_window_id is not None:
        stmt = stmt.where(VendorPickupWindow.id == pickup_window_id)
    return exists(stmt)


def _apply_meal_plan_discoverable_filters(
    stmt: Select[tuple[MealPlan]],
    *,
    available_on: date | None = None,
    pickup_window_id: uuid.UUID | None = None,
) -> Select[tuple[MealPlan]]:
    return stmt.where(
        Vendor.status == _DISCOVERABLE_VENDOR_STATUS,
        MealPlan.status == _DISCOVERABLE_MEAL_PLAN_STATUS,
        _meal_plan_has_any_items(),
        ~_meal_plan_has_hidden_items(),
        _discoverable_availability_exists(
            available_on=available_on,
            pickup_window_id=pickup_window_id,
        ),
    )


def create_vendor(
    session: Session,
    *,
    slug: str,
    name: str,
    description: str | None,
    status: VendorStatus,
) -> Vendor:
    vendor = Vendor(slug=slug, name=name, description=description, status=status)
    session.add(vendor)
    session.flush()
    return vendor


def save_vendor(session: Session, vendor: Vendor) -> Vendor:
    session.add(vendor)
    session.flush()
    return vendor


def list_vendors(
    session: Session,
    *,
    discoverable_only: bool = True,
) -> list[Vendor]:
    stmt: Select[tuple[Vendor]] = select(Vendor)
    if discoverable_only:
        stmt = stmt.where(Vendor.status == _DISCOVERABLE_VENDOR_STATUS)
    stmt = stmt.order_by(Vendor.name.asc(), Vendor.slug.asc(), Vendor.id.asc())
    return list(session.scalars(stmt))


def get_vendor_by_id(
    session: Session,
    *,
    vendor_id: uuid.UUID,
    discoverable_only: bool = True,
) -> Vendor | None:
    stmt: Select[tuple[Vendor]] = select(Vendor).where(Vendor.id == vendor_id)
    if discoverable_only:
        stmt = stmt.where(Vendor.status == _DISCOVERABLE_VENDOR_STATUS)
    return session.scalar(stmt)


def create_vendor_menu_item(
    session: Session,
    *,
    vendor_id: uuid.UUID,
    slug: str,
    name: str,
    description: str | None,
    status: VendorMenuItemStatus,
    price_cents: int,
    currency_code: str,
    calories: int | None,
    protein_grams: int | None,
    carbs_grams: int | None,
    fat_grams: int | None,
) -> VendorMenuItem:
    menu_item = VendorMenuItem(
        vendor_id=vendor_id,
        slug=slug,
        name=name,
        description=description,
        status=status,
        price_cents=price_cents,
        currency_code=currency_code,
        calories=calories,
        protein_grams=protein_grams,
        carbs_grams=carbs_grams,
        fat_grams=fat_grams,
    )
    session.add(menu_item)
    session.flush()
    return menu_item


def get_vendor_menu_item_by_id(
    session: Session,
    *,
    menu_item_id: uuid.UUID,
) -> VendorMenuItem | None:
    stmt: Select[tuple[VendorMenuItem]] = select(VendorMenuItem).where(
        VendorMenuItem.id == menu_item_id
    )
    return session.scalar(stmt)


def save_vendor_menu_item(session: Session, menu_item: VendorMenuItem) -> VendorMenuItem:
    session.add(menu_item)
    session.flush()
    return menu_item


def create_meal_plan(
    session: Session,
    *,
    vendor_id: uuid.UUID,
    slug: str,
    name: str,
    description: str | None,
    status: MealPlanStatus,
) -> MealPlan:
    meal_plan = MealPlan(
        vendor_id=vendor_id,
        slug=slug,
        name=name,
        description=description,
        status=status,
    )
    session.add(meal_plan)
    session.flush()
    return meal_plan


def get_meal_plan_by_id(
    session: Session,
    *,
    meal_plan_id: uuid.UUID,
    discoverable_only: bool = True,
) -> MealPlan | None:
    stmt: Select[tuple[MealPlan]] = (
        select(MealPlan)
        .join(Vendor, Vendor.id == MealPlan.vendor_id)
        .where(MealPlan.id == meal_plan_id)
    )
    if discoverable_only:
        stmt = _apply_meal_plan_discoverable_filters(stmt)
    return session.scalar(stmt)


def get_meal_plan_by_id_for_update(
    session: Session,
    *,
    meal_plan_id: uuid.UUID,
) -> MealPlan | None:
    stmt: Select[tuple[MealPlan]] = select(MealPlan).where(MealPlan.id == meal_plan_id)
    return session.scalar(stmt)


def save_meal_plan(session: Session, meal_plan: MealPlan) -> MealPlan:
    session.add(meal_plan)
    session.flush()
    return meal_plan


def create_meal_plan_item(
    session: Session,
    *,
    vendor_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    vendor_menu_item_id: uuid.UUID,
    quantity: int,
    position: int,
    notes: str | None,
) -> MealPlanItem:
    meal_plan_item = MealPlanItem(
        vendor_id=vendor_id,
        meal_plan_id=meal_plan_id,
        vendor_menu_item_id=vendor_menu_item_id,
        quantity=quantity,
        position=position,
        notes=notes,
    )
    session.add(meal_plan_item)
    session.flush()
    return meal_plan_item


def get_meal_plan_item_by_id(
    session: Session,
    *,
    meal_plan_item_id: uuid.UUID,
) -> MealPlanItem | None:
    stmt: Select[tuple[MealPlanItem]] = select(MealPlanItem).where(
        MealPlanItem.id == meal_plan_item_id
    )
    return session.scalar(stmt)


def save_meal_plan_item(session: Session, meal_plan_item: MealPlanItem) -> MealPlanItem:
    session.add(meal_plan_item)
    session.flush()
    return meal_plan_item


def delete_meal_plan_item(session: Session, meal_plan_item: MealPlanItem) -> None:
    session.delete(meal_plan_item)
    session.flush()


def create_vendor_pickup_window(
    session: Session,
    *,
    vendor_id: uuid.UUID,
    label: str | None,
    status: VendorPickupWindowStatus,
    pickup_start_at: datetime,
    pickup_end_at: datetime,
    order_cutoff_at: datetime | None,
    notes: str | None,
) -> VendorPickupWindow:
    pickup_window = VendorPickupWindow(
        vendor_id=vendor_id,
        label=label,
        status=status,
        pickup_start_at=pickup_start_at,
        pickup_end_at=pickup_end_at,
        order_cutoff_at=order_cutoff_at,
        notes=notes,
    )
    session.add(pickup_window)
    session.flush()
    return pickup_window


def get_vendor_pickup_window_by_id(
    session: Session,
    *,
    pickup_window_id: uuid.UUID,
) -> VendorPickupWindow | None:
    stmt: Select[tuple[VendorPickupWindow]] = select(VendorPickupWindow).where(
        VendorPickupWindow.id == pickup_window_id
    )
    return session.scalar(stmt)


def save_vendor_pickup_window(
    session: Session,
    pickup_window: VendorPickupWindow,
) -> VendorPickupWindow:
    session.add(pickup_window)
    session.flush()
    return pickup_window


def create_meal_plan_availability(
    session: Session,
    *,
    vendor_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    pickup_window_id: uuid.UUID,
    status: MealPlanAvailabilityStatus,
    inventory_count: int | None,
) -> MealPlanAvailability:
    availability = MealPlanAvailability(
        vendor_id=vendor_id,
        meal_plan_id=meal_plan_id,
        pickup_window_id=pickup_window_id,
        status=status,
        inventory_count=inventory_count,
    )
    session.add(availability)
    session.flush()
    return availability


def get_meal_plan_availability_by_id(
    session: Session,
    *,
    availability_id: uuid.UUID,
) -> MealPlanAvailability | None:
    stmt: Select[tuple[MealPlanAvailability]] = select(MealPlanAvailability).where(
        MealPlanAvailability.id == availability_id
    )
    return session.scalar(stmt)


def save_meal_plan_availability(
    session: Session,
    availability: MealPlanAvailability,
) -> MealPlanAvailability:
    session.add(availability)
    session.flush()
    return availability


def list_meal_plans(
    session: Session,
    *,
    vendor_id: uuid.UUID | None = None,
    discoverable_only: bool = True,
    calorie_min: int | None = None,
    calorie_max: int | None = None,
    price_min_cents: int | None = None,
    price_max_cents: int | None = None,
    available_on: date | None = None,
    pickup_window_id: uuid.UUID | None = None,
) -> list[MealPlan]:
    totals = _meal_plan_totals_subquery(discoverable_only=discoverable_only)
    stmt: Select[tuple[MealPlan]] = (
        select(MealPlan)
        .join(Vendor, Vendor.id == MealPlan.vendor_id)
        .outerjoin(totals, totals.c.meal_plan_id == MealPlan.id)
    )

    if vendor_id is not None:
        stmt = stmt.where(MealPlan.vendor_id == vendor_id)
    if discoverable_only:
        stmt = _apply_meal_plan_discoverable_filters(
            stmt,
            available_on=available_on,
            pickup_window_id=pickup_window_id,
        )
    if calorie_min is not None:
        stmt = stmt.where(func.coalesce(totals.c.total_calories, 0) >= calorie_min)
    if calorie_max is not None:
        stmt = stmt.where(func.coalesce(totals.c.total_calories, 0) <= calorie_max)
    if price_min_cents is not None:
        stmt = stmt.where(func.coalesce(totals.c.total_price_cents, 0) >= price_min_cents)
    if price_max_cents is not None:
        stmt = stmt.where(func.coalesce(totals.c.total_price_cents, 0) <= price_max_cents)

    stmt = stmt.order_by(MealPlan.name.asc(), MealPlan.slug.asc(), MealPlan.id.asc())
    return list(session.scalars(stmt))


def list_meal_plan_items(
    session: Session,
    *,
    meal_plan_id: uuid.UUID,
    discoverable_only: bool = True,
) -> list[MealPlanItem]:
    stmt: Select[tuple[MealPlanItem]] = (
        select(MealPlanItem)
        .join(MealPlan, MealPlan.id == MealPlanItem.meal_plan_id)
        .join(Vendor, Vendor.id == MealPlan.vendor_id)
        .join(VendorMenuItem, VendorMenuItem.id == MealPlanItem.vendor_menu_item_id)
        .where(MealPlanItem.meal_plan_id == meal_plan_id)
    )
    if discoverable_only:
        stmt = stmt.where(
            Vendor.status == _DISCOVERABLE_VENDOR_STATUS,
            MealPlan.status == _DISCOVERABLE_MEAL_PLAN_STATUS,
            VendorMenuItem.status == _DISCOVERABLE_MENU_ITEM_STATUS,
            ~_meal_plan_has_hidden_items(),
            _discoverable_availability_exists(),
        )
    stmt = stmt.order_by(MealPlanItem.position.asc(), MealPlanItem.id.asc())
    return list(session.scalars(stmt))


def list_meal_plan_items_for_meal_plans(
    session: Session,
    *,
    meal_plan_ids: Sequence[uuid.UUID],
    discoverable_only: bool = True,
) -> list[MealPlanItem]:
    if not meal_plan_ids:
        return []

    stmt: Select[tuple[MealPlanItem]] = (
        select(MealPlanItem)
        .join(MealPlan, MealPlan.id == MealPlanItem.meal_plan_id)
        .join(Vendor, Vendor.id == MealPlan.vendor_id)
        .join(VendorMenuItem, VendorMenuItem.id == MealPlanItem.vendor_menu_item_id)
        .where(MealPlanItem.meal_plan_id.in_(meal_plan_ids))
    )
    if discoverable_only:
        stmt = stmt.where(
            Vendor.status == _DISCOVERABLE_VENDOR_STATUS,
            MealPlan.status == _DISCOVERABLE_MEAL_PLAN_STATUS,
            VendorMenuItem.status == _DISCOVERABLE_MENU_ITEM_STATUS,
            ~_meal_plan_has_hidden_items(),
            _discoverable_availability_exists(),
        )
    stmt = stmt.order_by(
        MealPlanItem.meal_plan_id.asc(),
        MealPlanItem.position.asc(),
        MealPlanItem.id.asc(),
    )
    return list(session.scalars(stmt))


def list_vendor_pickup_windows(
    session: Session,
    *,
    vendor_id: uuid.UUID | None = None,
    meal_plan_id: uuid.UUID | None = None,
    discoverable_only: bool = True,
    available_on: date | None = None,
) -> list[VendorPickupWindow]:
    stmt: Select[tuple[VendorPickupWindow]] = select(VendorPickupWindow).join(
        Vendor, Vendor.id == VendorPickupWindow.vendor_id
    )
    if vendor_id is not None:
        stmt = stmt.where(VendorPickupWindow.vendor_id == vendor_id)
    if meal_plan_id is not None:
        stmt = (
            stmt.join(
                MealPlanAvailability,
                MealPlanAvailability.pickup_window_id == VendorPickupWindow.id,
            )
            .join(MealPlan, MealPlan.id == MealPlanAvailability.meal_plan_id)
            .where(MealPlan.id == meal_plan_id)
        )
    if discoverable_only:
        stmt = stmt.where(
            Vendor.status == _DISCOVERABLE_VENDOR_STATUS,
            VendorPickupWindow.status.in_(_DISCOVERABLE_PICKUP_WINDOW_STATUSES),
        )
        if meal_plan_id is not None:
            stmt = stmt.where(
                MealPlan.status == _DISCOVERABLE_MEAL_PLAN_STATUS,
                MealPlanAvailability.status.in_(_DISCOVERABLE_AVAILABILITY_STATUSES),
                or_(
                    MealPlanAvailability.inventory_count.is_(None),
                    MealPlanAvailability.inventory_count > 0,
                ),
                _meal_plan_has_any_items(),
                ~_meal_plan_has_hidden_items(),
            )
    if available_on is not None:
        stmt = stmt.where(func.date(VendorPickupWindow.pickup_start_at) == available_on)

    stmt = stmt.distinct().order_by(
        VendorPickupWindow.pickup_start_at.asc(), VendorPickupWindow.id.asc()
    )
    return list(session.scalars(stmt))


def list_meal_plan_availability(
    session: Session,
    *,
    vendor_id: uuid.UUID | None = None,
    meal_plan_id: uuid.UUID | None = None,
    pickup_window_id: uuid.UUID | None = None,
    discoverable_only: bool = True,
    available_on: date | None = None,
) -> list[MealPlanAvailability]:
    stmt: Select[tuple[MealPlanAvailability]] = (
        select(MealPlanAvailability)
        .join(MealPlan, MealPlan.id == MealPlanAvailability.meal_plan_id)
        .join(Vendor, Vendor.id == MealPlan.vendor_id)
        .join(VendorPickupWindow, VendorPickupWindow.id == MealPlanAvailability.pickup_window_id)
    )

    if vendor_id is not None:
        stmt = stmt.where(MealPlanAvailability.vendor_id == vendor_id)
    if meal_plan_id is not None:
        stmt = stmt.where(MealPlanAvailability.meal_plan_id == meal_plan_id)
    if pickup_window_id is not None:
        stmt = stmt.where(MealPlanAvailability.pickup_window_id == pickup_window_id)
    if available_on is not None:
        stmt = stmt.where(func.date(VendorPickupWindow.pickup_start_at) == available_on)
    if discoverable_only:
        stmt = stmt.where(
            Vendor.status == _DISCOVERABLE_VENDOR_STATUS,
            MealPlan.status == _DISCOVERABLE_MEAL_PLAN_STATUS,
            MealPlanAvailability.status.in_(_DISCOVERABLE_AVAILABILITY_STATUSES),
            VendorPickupWindow.status.in_(_DISCOVERABLE_PICKUP_WINDOW_STATUSES),
            or_(
                MealPlanAvailability.inventory_count.is_(None),
                MealPlanAvailability.inventory_count > 0,
            ),
            _meal_plan_has_any_items(),
            ~_meal_plan_has_hidden_items(),
        )

    stmt = stmt.order_by(VendorPickupWindow.pickup_start_at.asc(), MealPlanAvailability.id.asc())
    return list(session.scalars(stmt))


def list_meal_plan_availability_for_meal_plans(
    session: Session,
    *,
    meal_plan_ids: Sequence[uuid.UUID],
    discoverable_only: bool = True,
) -> list[MealPlanAvailability]:
    if not meal_plan_ids:
        return []

    stmt: Select[tuple[MealPlanAvailability]] = (
        select(MealPlanAvailability)
        .join(MealPlan, MealPlan.id == MealPlanAvailability.meal_plan_id)
        .join(Vendor, Vendor.id == MealPlan.vendor_id)
        .join(VendorPickupWindow, VendorPickupWindow.id == MealPlanAvailability.pickup_window_id)
        .where(MealPlanAvailability.meal_plan_id.in_(meal_plan_ids))
    )
    if discoverable_only:
        stmt = stmt.where(
            Vendor.status == _DISCOVERABLE_VENDOR_STATUS,
            MealPlan.status == _DISCOVERABLE_MEAL_PLAN_STATUS,
            MealPlanAvailability.status.in_(_DISCOVERABLE_AVAILABILITY_STATUSES),
            VendorPickupWindow.status.in_(_DISCOVERABLE_PICKUP_WINDOW_STATUSES),
            or_(
                MealPlanAvailability.inventory_count.is_(None),
                MealPlanAvailability.inventory_count > 0,
            ),
            _meal_plan_has_any_items(),
            ~_meal_plan_has_hidden_items(),
        )
    stmt = stmt.order_by(
        MealPlanAvailability.meal_plan_id.asc(),
        VendorPickupWindow.pickup_start_at.asc(),
        MealPlanAvailability.id.asc(),
    )
    return list(session.scalars(stmt))
