import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


class VendorServiceError(Exception):
    """Base vendor-domain service error."""


class VendorConflictError(VendorServiceError):
    """Raised when a uniqueness/conflict constraint is hit."""


class VendorNotFoundError(VendorServiceError):
    """Raised when a requested vendor-domain resource does not exist."""


class VendorValidationError(VendorServiceError):
    """Raised when vendor-domain input violates business rules."""


@dataclass(frozen=True, slots=True)
class VendorMenuItemView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: VendorMenuItemStatus
    price_cents: int
    currency_code: str
    calories: int | None
    protein_grams: int | None
    carbs_grams: int | None
    fat_grams: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VendorPickupWindowView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    label: str | None
    status: VendorPickupWindowStatus
    pickup_start_at: datetime
    pickup_end_at: datetime
    order_cutoff_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MealPlanItemView:
    id: uuid.UUID
    vendor_menu_item_id: uuid.UUID
    slug: str
    name: str
    quantity: int
    position: int
    notes: str | None
    price_cents: int
    currency_code: str
    calories: int | None


@dataclass(frozen=True, slots=True)
class MealPlanAvailabilityView:
    id: uuid.UUID
    pickup_window_id: uuid.UUID
    pickup_window_label: str | None
    pickup_start_at: datetime
    pickup_end_at: datetime
    availability_status: MealPlanAvailabilityStatus
    pickup_window_status: str
    inventory_count: int | None


@dataclass(frozen=True, slots=True)
class MealPlanSummaryView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: MealPlanStatus
    total_price_cents: int
    total_calories: int
    item_count: int
    availability_count: int


@dataclass(frozen=True, slots=True)
class MealPlanListView:
    vendor_id: uuid.UUID | None
    items: tuple[MealPlanSummaryView, ...]
    count: int


@dataclass(frozen=True, slots=True)
class VendorSummaryView:
    id: uuid.UUID
    slug: str
    name: str
    status: VendorStatus
    meal_plan_count: int


@dataclass(frozen=True, slots=True)
class VendorListView:
    items: tuple[VendorSummaryView, ...]
    count: int


@dataclass(frozen=True, slots=True)
class VendorDetailView:
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: VendorStatus
    meal_plans: tuple[MealPlanSummaryView, ...]
    meal_plan_count: int


@dataclass(frozen=True, slots=True)
class MealPlanDetailView:
    id: uuid.UUID
    vendor_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: MealPlanStatus
    items: tuple[MealPlanItemView, ...]
    availability: tuple[MealPlanAvailabilityView, ...]
    total_price_cents: int
    total_calories: int
    item_count: int
    availability_count: int


class VendorService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_vendors(self, *, discoverable_only: bool = True) -> VendorListView:
        vendors = vendor_repo.list_vendors(self._session, discoverable_only=discoverable_only)
        meal_plans = vendor_repo.list_meal_plans(
            self._session,
            discoverable_only=discoverable_only,
        )
        meal_plan_counts: dict[uuid.UUID, int] = defaultdict(int)
        for meal_plan in meal_plans:
            meal_plan_counts[meal_plan.vendor_id] += 1

        items = tuple(
            VendorSummaryView(
                id=vendor.id,
                slug=vendor.slug,
                name=vendor.name,
                status=vendor.status,
                meal_plan_count=meal_plan_counts.get(vendor.id, 0),
            )
            for vendor in vendors
        )
        return VendorListView(items=items, count=len(items))

    def get_vendor_detail(
        self,
        *,
        vendor_id: uuid.UUID,
        discoverable_only: bool = True,
    ) -> VendorDetailView | None:
        vendor = vendor_repo.get_vendor_by_id(
            self._session,
            vendor_id=vendor_id,
            discoverable_only=discoverable_only,
        )
        if vendor is None:
            return None

        meal_plan_list = self.list_meal_plans(
            vendor_id=vendor.id,
            discoverable_only=discoverable_only,
        )
        return VendorDetailView(
            id=vendor.id,
            slug=vendor.slug,
            name=vendor.name,
            description=vendor.description,
            status=vendor.status,
            meal_plans=meal_plan_list.items,
            meal_plan_count=meal_plan_list.count,
        )

    def create_vendor(
        self,
        *,
        slug: str,
        name: str,
        description: str | None,
        status: VendorStatus,
    ) -> VendorDetailView:
        try:
            vendor = vendor_repo.create_vendor(
                self._session,
                slug=slug,
                name=name,
                description=description,
                status=status,
            )
        except IntegrityError as exc:
            raise VendorConflictError("vendor_already_exists") from exc
        return self._require_vendor_detail(vendor.id, discoverable_only=False)

    def update_vendor(
        self,
        *,
        vendor_id: uuid.UUID,
        slug: str,
        name: str,
        description: str | None,
        status: VendorStatus,
    ) -> VendorDetailView:
        vendor = self._require_vendor(vendor_id=vendor_id)
        vendor.slug = slug
        vendor.name = name
        vendor.description = description
        vendor.status = status
        try:
            vendor_repo.save_vendor(self._session, vendor)
        except IntegrityError as exc:
            raise VendorConflictError("vendor_already_exists") from exc
        return self._require_vendor_detail(vendor.id, discoverable_only=False)

    def archive_vendor(self, *, vendor_id: uuid.UUID) -> VendorDetailView:
        vendor = self._require_vendor(vendor_id=vendor_id)
        vendor.status = VendorStatus.ARCHIVED
        vendor_repo.save_vendor(self._session, vendor)
        return self._require_vendor_detail(vendor.id, discoverable_only=False)

    def create_vendor_menu_item(
        self,
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
    ) -> VendorMenuItemView:
        self._require_vendor(vendor_id=vendor_id)
        try:
            menu_item = vendor_repo.create_vendor_menu_item(
                self._session,
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
        except IntegrityError as exc:
            raise VendorConflictError("vendor_menu_item_already_exists") from exc
        return self._to_vendor_menu_item_view(menu_item.id)

    def update_vendor_menu_item(
        self,
        *,
        vendor_id: uuid.UUID,
        menu_item_id: uuid.UUID,
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
    ) -> VendorMenuItemView:
        self._require_vendor(vendor_id=vendor_id)
        menu_item = self._require_vendor_menu_item(menu_item_id=menu_item_id)
        if menu_item.vendor_id != vendor_id:
            raise VendorValidationError("vendor_menu_item_vendor_mismatch")
        menu_item.slug = slug
        menu_item.name = name
        menu_item.description = description
        menu_item.status = status
        menu_item.price_cents = price_cents
        menu_item.currency_code = currency_code
        menu_item.calories = calories
        menu_item.protein_grams = protein_grams
        menu_item.carbs_grams = carbs_grams
        menu_item.fat_grams = fat_grams
        try:
            vendor_repo.save_vendor_menu_item(self._session, menu_item)
        except IntegrityError as exc:
            raise VendorConflictError("vendor_menu_item_already_exists") from exc
        return self._to_vendor_menu_item_view(menu_item.id)

    def archive_vendor_menu_item(
        self,
        *,
        vendor_id: uuid.UUID,
        menu_item_id: uuid.UUID,
    ) -> VendorMenuItemView:
        self._require_vendor(vendor_id=vendor_id)
        menu_item = self._require_vendor_menu_item(menu_item_id=menu_item_id)
        if menu_item.vendor_id != vendor_id:
            raise VendorValidationError("vendor_menu_item_vendor_mismatch")
        menu_item.status = VendorMenuItemStatus.ARCHIVED
        vendor_repo.save_vendor_menu_item(self._session, menu_item)
        return self._to_vendor_menu_item_view(menu_item.id)

    def create_meal_plan(
        self,
        *,
        vendor_id: uuid.UUID,
        slug: str,
        name: str,
        description: str | None,
        status: MealPlanStatus,
    ) -> MealPlanDetailView:
        self._require_vendor(vendor_id=vendor_id)
        try:
            meal_plan = vendor_repo.create_meal_plan(
                self._session,
                vendor_id=vendor_id,
                slug=slug,
                name=name,
                description=description,
                status=status,
            )
        except IntegrityError as exc:
            raise VendorConflictError("meal_plan_already_exists") from exc
        return self._require_meal_plan_detail(meal_plan.id, discoverable_only=False)

    def update_meal_plan(
        self,
        *,
        vendor_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
        slug: str,
        name: str,
        description: str | None,
        status: MealPlanStatus,
    ) -> MealPlanDetailView:
        self._require_vendor(vendor_id=vendor_id)
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        if meal_plan.vendor_id != vendor_id:
            raise VendorValidationError("meal_plan_vendor_mismatch")
        meal_plan.slug = slug
        meal_plan.name = name
        meal_plan.description = description
        meal_plan.status = status
        try:
            vendor_repo.save_meal_plan(self._session, meal_plan)
        except IntegrityError as exc:
            raise VendorConflictError("meal_plan_already_exists") from exc
        return self._require_meal_plan_detail(meal_plan.id, discoverable_only=False)

    def archive_meal_plan(
        self,
        *,
        vendor_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
    ) -> MealPlanDetailView:
        self._require_vendor(vendor_id=vendor_id)
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        if meal_plan.vendor_id != vendor_id:
            raise VendorValidationError("meal_plan_vendor_mismatch")
        meal_plan.status = MealPlanStatus.ARCHIVED
        vendor_repo.save_meal_plan(self._session, meal_plan)
        return self._require_meal_plan_detail(meal_plan.id, discoverable_only=False)

    def create_meal_plan_item(
        self,
        *,
        meal_plan_id: uuid.UUID,
        vendor_menu_item_id: uuid.UUID,
        quantity: int,
        position: int,
        notes: str | None,
    ) -> MealPlanItemView:
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        menu_item = self._require_vendor_menu_item(menu_item_id=vendor_menu_item_id)
        if meal_plan.vendor_id != menu_item.vendor_id:
            raise VendorValidationError("meal_plan_item_vendor_mismatch")
        try:
            meal_plan_item = vendor_repo.create_meal_plan_item(
                self._session,
                vendor_id=meal_plan.vendor_id,
                meal_plan_id=meal_plan.id,
                vendor_menu_item_id=menu_item.id,
                quantity=quantity,
                position=position,
                notes=notes,
            )
        except IntegrityError as exc:
            raise VendorConflictError("meal_plan_item_conflict") from exc
        return self._to_meal_plan_item_view(meal_plan_item.id, discoverable_only=False)

    def update_meal_plan_item(
        self,
        *,
        meal_plan_id: uuid.UUID,
        meal_plan_item_id: uuid.UUID,
        vendor_menu_item_id: uuid.UUID,
        quantity: int,
        position: int,
        notes: str | None,
    ) -> MealPlanItemView:
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        meal_plan_item = self._require_meal_plan_item(meal_plan_item_id=meal_plan_item_id)
        menu_item = self._require_vendor_menu_item(menu_item_id=vendor_menu_item_id)
        if meal_plan_item.meal_plan_id != meal_plan.id:
            raise VendorValidationError("meal_plan_item_parent_mismatch")
        if meal_plan.vendor_id != menu_item.vendor_id:
            raise VendorValidationError("meal_plan_item_vendor_mismatch")
        meal_plan_item.vendor_id = meal_plan.vendor_id
        meal_plan_item.vendor_menu_item_id = menu_item.id
        meal_plan_item.quantity = quantity
        meal_plan_item.position = position
        meal_plan_item.notes = notes
        try:
            vendor_repo.save_meal_plan_item(self._session, meal_plan_item)
        except IntegrityError as exc:
            raise VendorConflictError("meal_plan_item_conflict") from exc
        return self._to_meal_plan_item_view(meal_plan_item.id, discoverable_only=False)

    def delete_meal_plan_item(
        self,
        *,
        meal_plan_id: uuid.UUID,
        meal_plan_item_id: uuid.UUID,
    ) -> None:
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        meal_plan_item = self._require_meal_plan_item(meal_plan_item_id=meal_plan_item_id)
        if meal_plan_item.meal_plan_id != meal_plan.id:
            raise VendorValidationError("meal_plan_item_parent_mismatch")
        vendor_repo.delete_meal_plan_item(self._session, meal_plan_item)

    def create_vendor_pickup_window(
        self,
        *,
        vendor_id: uuid.UUID,
        label: str | None,
        status: VendorPickupWindowStatus,
        pickup_start_at: datetime,
        pickup_end_at: datetime,
        order_cutoff_at: datetime | None,
        notes: str | None,
    ) -> VendorPickupWindowView:
        self._require_vendor(vendor_id=vendor_id)
        self._validate_pickup_window_fields(
            pickup_start_at=pickup_start_at,
            pickup_end_at=pickup_end_at,
            order_cutoff_at=order_cutoff_at,
        )
        pickup_window = vendor_repo.create_vendor_pickup_window(
            self._session,
            vendor_id=vendor_id,
            label=label,
            status=status,
            pickup_start_at=pickup_start_at,
            pickup_end_at=pickup_end_at,
            order_cutoff_at=order_cutoff_at,
            notes=notes,
        )
        return self._to_vendor_pickup_window_view(pickup_window.id)

    def update_vendor_pickup_window(
        self,
        *,
        vendor_id: uuid.UUID,
        pickup_window_id: uuid.UUID,
        label: str | None,
        status: VendorPickupWindowStatus,
        pickup_start_at: datetime,
        pickup_end_at: datetime,
        order_cutoff_at: datetime | None,
        notes: str | None,
    ) -> VendorPickupWindowView:
        self._require_vendor(vendor_id=vendor_id)
        pickup_window = self._require_vendor_pickup_window(pickup_window_id=pickup_window_id)
        if pickup_window.vendor_id != vendor_id:
            raise VendorValidationError("vendor_pickup_window_vendor_mismatch")
        self._validate_pickup_window_fields(
            pickup_start_at=pickup_start_at,
            pickup_end_at=pickup_end_at,
            order_cutoff_at=order_cutoff_at,
        )
        pickup_window.label = label
        pickup_window.status = status
        pickup_window.pickup_start_at = pickup_start_at
        pickup_window.pickup_end_at = pickup_end_at
        pickup_window.order_cutoff_at = order_cutoff_at
        pickup_window.notes = notes
        vendor_repo.save_vendor_pickup_window(self._session, pickup_window)
        return self._to_vendor_pickup_window_view(pickup_window.id)

    def cancel_vendor_pickup_window(
        self,
        *,
        vendor_id: uuid.UUID,
        pickup_window_id: uuid.UUID,
    ) -> VendorPickupWindowView:
        self._require_vendor(vendor_id=vendor_id)
        pickup_window = self._require_vendor_pickup_window(pickup_window_id=pickup_window_id)
        if pickup_window.vendor_id != vendor_id:
            raise VendorValidationError("vendor_pickup_window_vendor_mismatch")
        pickup_window.status = VendorPickupWindowStatus.CANCELLED
        vendor_repo.save_vendor_pickup_window(self._session, pickup_window)
        return self._to_vendor_pickup_window_view(pickup_window.id)

    def create_meal_plan_availability(
        self,
        *,
        meal_plan_id: uuid.UUID,
        pickup_window_id: uuid.UUID,
        status: MealPlanAvailabilityStatus,
        inventory_count: int | None,
    ) -> MealPlanAvailabilityView:
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        pickup_window = self._require_vendor_pickup_window(pickup_window_id=pickup_window_id)
        if meal_plan.vendor_id != pickup_window.vendor_id:
            raise VendorValidationError("meal_plan_availability_vendor_mismatch")
        try:
            availability = vendor_repo.create_meal_plan_availability(
                self._session,
                vendor_id=meal_plan.vendor_id,
                meal_plan_id=meal_plan.id,
                pickup_window_id=pickup_window.id,
                status=status,
                inventory_count=inventory_count,
            )
        except IntegrityError as exc:
            raise VendorConflictError("meal_plan_availability_conflict") from exc
        return self._to_meal_plan_availability_view(availability.id, discoverable_only=False)

    def update_meal_plan_availability(
        self,
        *,
        meal_plan_id: uuid.UUID,
        availability_id: uuid.UUID,
        pickup_window_id: uuid.UUID,
        status: MealPlanAvailabilityStatus,
        inventory_count: int | None,
    ) -> MealPlanAvailabilityView:
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        availability = self._require_meal_plan_availability(availability_id=availability_id)
        pickup_window = self._require_vendor_pickup_window(pickup_window_id=pickup_window_id)
        if availability.meal_plan_id != meal_plan.id:
            raise VendorValidationError("meal_plan_availability_parent_mismatch")
        if meal_plan.vendor_id != pickup_window.vendor_id:
            raise VendorValidationError("meal_plan_availability_vendor_mismatch")
        availability.vendor_id = meal_plan.vendor_id
        availability.pickup_window_id = pickup_window.id
        availability.status = status
        availability.inventory_count = inventory_count
        try:
            vendor_repo.save_meal_plan_availability(self._session, availability)
        except IntegrityError as exc:
            raise VendorConflictError("meal_plan_availability_conflict") from exc
        return self._to_meal_plan_availability_view(availability.id, discoverable_only=False)

    def cancel_meal_plan_availability(
        self,
        *,
        meal_plan_id: uuid.UUID,
        availability_id: uuid.UUID,
    ) -> MealPlanAvailabilityView:
        meal_plan = self._require_meal_plan_for_update(meal_plan_id=meal_plan_id)
        availability = self._require_meal_plan_availability(availability_id=availability_id)
        if availability.meal_plan_id != meal_plan.id:
            raise VendorValidationError("meal_plan_availability_parent_mismatch")
        availability.status = MealPlanAvailabilityStatus.CANCELLED
        vendor_repo.save_meal_plan_availability(self._session, availability)
        return self._to_meal_plan_availability_view(availability.id, discoverable_only=False)

    def list_meal_plans(
        self,
        *,
        vendor_id: uuid.UUID | None = None,
        discoverable_only: bool = True,
        calorie_min: int | None = None,
        calorie_max: int | None = None,
        price_min_cents: int | None = None,
        price_max_cents: int | None = None,
        available_on: date | None = None,
        pickup_window_id: uuid.UUID | None = None,
    ) -> MealPlanListView:
        meal_plans = vendor_repo.list_meal_plans(
            self._session,
            vendor_id=vendor_id,
            discoverable_only=discoverable_only,
            calorie_min=calorie_min,
            calorie_max=calorie_max,
            price_min_cents=price_min_cents,
            price_max_cents=price_max_cents,
            available_on=available_on,
            pickup_window_id=pickup_window_id,
        )
        items = self._build_meal_plan_summary_views(
            meal_plans,
            discoverable_only=discoverable_only,
        )
        return MealPlanListView(vendor_id=vendor_id, items=items, count=len(items))

    def get_meal_plan_detail(
        self,
        *,
        meal_plan_id: uuid.UUID,
        discoverable_only: bool = True,
    ) -> MealPlanDetailView | None:
        meal_plan = vendor_repo.get_meal_plan_by_id(
            self._session,
            meal_plan_id=meal_plan_id,
            discoverable_only=discoverable_only,
        )
        if meal_plan is None:
            return None

        item_views = self.list_meal_plan_items(
            meal_plan_id=meal_plan.id,
            discoverable_only=discoverable_only,
        )
        availability_views = self.list_meal_plan_availability(
            meal_plan_id=meal_plan.id,
            discoverable_only=discoverable_only,
        )
        return self._build_meal_plan_detail_view(
            meal_plan,
            item_views=item_views,
            availability_views=availability_views,
        )

    def list_meal_plan_items(
        self,
        *,
        meal_plan_id: uuid.UUID,
        discoverable_only: bool = True,
    ) -> tuple[MealPlanItemView, ...]:
        items = vendor_repo.list_meal_plan_items(
            self._session,
            meal_plan_id=meal_plan_id,
            discoverable_only=discoverable_only,
        )
        return tuple(self._item_view_from_model(item) for item in items)

    def list_meal_plan_availability(
        self,
        *,
        vendor_id: uuid.UUID | None = None,
        meal_plan_id: uuid.UUID | None = None,
        pickup_window_id: uuid.UUID | None = None,
        discoverable_only: bool = True,
        available_on: date | None = None,
    ) -> tuple[MealPlanAvailabilityView, ...]:
        availability_rows = vendor_repo.list_meal_plan_availability(
            self._session,
            vendor_id=vendor_id,
            meal_plan_id=meal_plan_id,
            pickup_window_id=pickup_window_id,
            discoverable_only=discoverable_only,
            available_on=available_on,
        )
        return tuple(self._availability_view_from_model(row) for row in availability_rows)

    def _require_vendor(self, *, vendor_id: uuid.UUID) -> Vendor:
        vendor = vendor_repo.get_vendor_by_id(
            self._session,
            vendor_id=vendor_id,
            discoverable_only=False,
        )
        if vendor is None:
            raise VendorNotFoundError("vendor_not_found")
        return vendor

    def _require_vendor_menu_item(self, *, menu_item_id: uuid.UUID) -> VendorMenuItem:
        menu_item = vendor_repo.get_vendor_menu_item_by_id(
            self._session,
            menu_item_id=menu_item_id,
        )
        if menu_item is None:
            raise VendorNotFoundError("vendor_menu_item_not_found")
        return menu_item

    def _require_meal_plan_for_update(self, *, meal_plan_id: uuid.UUID) -> MealPlan:
        meal_plan = vendor_repo.get_meal_plan_by_id_for_update(
            self._session,
            meal_plan_id=meal_plan_id,
        )
        if meal_plan is None:
            raise VendorNotFoundError("meal_plan_not_found")
        return meal_plan

    def _require_meal_plan_item(self, *, meal_plan_item_id: uuid.UUID) -> MealPlanItem:
        meal_plan_item = vendor_repo.get_meal_plan_item_by_id(
            self._session,
            meal_plan_item_id=meal_plan_item_id,
        )
        if meal_plan_item is None:
            raise VendorNotFoundError("meal_plan_item_not_found")
        return meal_plan_item

    def _require_vendor_pickup_window(self, *, pickup_window_id: uuid.UUID) -> VendorPickupWindow:
        pickup_window = vendor_repo.get_vendor_pickup_window_by_id(
            self._session,
            pickup_window_id=pickup_window_id,
        )
        if pickup_window is None:
            raise VendorNotFoundError("vendor_pickup_window_not_found")
        return pickup_window

    def _require_meal_plan_availability(
        self, *, availability_id: uuid.UUID
    ) -> MealPlanAvailability:
        availability = vendor_repo.get_meal_plan_availability_by_id(
            self._session,
            availability_id=availability_id,
        )
        if availability is None:
            raise VendorNotFoundError("meal_plan_availability_not_found")
        return availability

    def _require_vendor_detail(
        self,
        vendor_id: uuid.UUID,
        *,
        discoverable_only: bool,
    ) -> VendorDetailView:
        detail = self.get_vendor_detail(vendor_id=vendor_id, discoverable_only=discoverable_only)
        if detail is None:
            raise VendorNotFoundError("vendor_not_found")
        return detail

    def _require_meal_plan_detail(
        self,
        meal_plan_id: uuid.UUID,
        *,
        discoverable_only: bool,
    ) -> MealPlanDetailView:
        detail = self.get_meal_plan_detail(
            meal_plan_id=meal_plan_id,
            discoverable_only=discoverable_only,
        )
        if detail is None:
            raise VendorNotFoundError("meal_plan_not_found")
        return detail

    def _validate_pickup_window_fields(
        self,
        *,
        pickup_start_at: datetime,
        pickup_end_at: datetime,
        order_cutoff_at: datetime | None,
    ) -> None:
        if pickup_end_at <= pickup_start_at:
            raise VendorValidationError("vendor_pickup_window_time_order_invalid")
        if order_cutoff_at is not None and order_cutoff_at > pickup_start_at:
            raise VendorValidationError("vendor_pickup_window_cutoff_invalid")

    def _build_meal_plan_summary_views(
        self,
        meal_plans: list[MealPlan],
        *,
        discoverable_only: bool,
    ) -> tuple[MealPlanSummaryView, ...]:
        if not meal_plans:
            return ()

        meal_plan_ids = [meal_plan.id for meal_plan in meal_plans]
        item_views_by_plan = self._item_views_by_meal_plan(
            meal_plan_ids,
            discoverable_only=discoverable_only,
        )
        availability_views_by_plan = self._availability_views_by_meal_plan(
            meal_plan_ids,
            discoverable_only=discoverable_only,
        )
        return tuple(
            self._build_meal_plan_summary_view(
                meal_plan,
                item_views=item_views_by_plan.get(meal_plan.id, ()),
                availability_views=availability_views_by_plan.get(meal_plan.id, ()),
            )
            for meal_plan in meal_plans
        )

    def _item_views_by_meal_plan(
        self,
        meal_plan_ids: list[uuid.UUID],
        *,
        discoverable_only: bool,
    ) -> dict[uuid.UUID, tuple[MealPlanItemView, ...]]:
        grouped: dict[uuid.UUID, list[MealPlanItemView]] = defaultdict(list)
        items = vendor_repo.list_meal_plan_items_for_meal_plans(
            self._session,
            meal_plan_ids=meal_plan_ids,
            discoverable_only=discoverable_only,
        )
        for item in items:
            grouped[item.meal_plan_id].append(self._item_view_from_model(item))
        return {meal_plan_id: tuple(rows) for meal_plan_id, rows in grouped.items()}

    def _availability_views_by_meal_plan(
        self,
        meal_plan_ids: list[uuid.UUID],
        *,
        discoverable_only: bool,
    ) -> dict[uuid.UUID, tuple[MealPlanAvailabilityView, ...]]:
        grouped: dict[uuid.UUID, list[MealPlanAvailabilityView]] = defaultdict(list)
        availability_rows = vendor_repo.list_meal_plan_availability_for_meal_plans(
            self._session,
            meal_plan_ids=meal_plan_ids,
            discoverable_only=discoverable_only,
        )
        for row in availability_rows:
            grouped[row.meal_plan_id].append(self._availability_view_from_model(row))
        return {meal_plan_id: tuple(rows) for meal_plan_id, rows in grouped.items()}

    def _build_meal_plan_summary_view(
        self,
        meal_plan: MealPlan,
        *,
        item_views: tuple[MealPlanItemView, ...],
        availability_views: tuple[MealPlanAvailabilityView, ...],
    ) -> MealPlanSummaryView:
        total_price_cents = sum(item.price_cents * item.quantity for item in item_views)
        total_calories = sum((item.calories or 0) * item.quantity for item in item_views)
        return MealPlanSummaryView(
            id=meal_plan.id,
            vendor_id=meal_plan.vendor_id,
            slug=meal_plan.slug,
            name=meal_plan.name,
            description=meal_plan.description,
            status=meal_plan.status,
            total_price_cents=total_price_cents,
            total_calories=total_calories,
            item_count=len(item_views),
            availability_count=len(availability_views),
        )

    def _build_meal_plan_detail_view(
        self,
        meal_plan: MealPlan,
        *,
        item_views: tuple[MealPlanItemView, ...],
        availability_views: tuple[MealPlanAvailabilityView, ...],
    ) -> MealPlanDetailView:
        summary = self._build_meal_plan_summary_view(
            meal_plan,
            item_views=item_views,
            availability_views=availability_views,
        )
        return MealPlanDetailView(
            id=summary.id,
            vendor_id=summary.vendor_id,
            slug=summary.slug,
            name=summary.name,
            description=summary.description,
            status=summary.status,
            items=item_views,
            availability=availability_views,
            total_price_cents=summary.total_price_cents,
            total_calories=summary.total_calories,
            item_count=summary.item_count,
            availability_count=summary.availability_count,
        )

    def _to_vendor_menu_item_view(self, menu_item_id: uuid.UUID) -> VendorMenuItemView:
        menu_item = self._require_vendor_menu_item(menu_item_id=menu_item_id)
        return VendorMenuItemView(
            id=menu_item.id,
            vendor_id=menu_item.vendor_id,
            slug=menu_item.slug,
            name=menu_item.name,
            description=menu_item.description,
            status=menu_item.status,
            price_cents=menu_item.price_cents,
            currency_code=menu_item.currency_code,
            calories=menu_item.calories,
            protein_grams=menu_item.protein_grams,
            carbs_grams=menu_item.carbs_grams,
            fat_grams=menu_item.fat_grams,
            created_at=menu_item.created_at,
            updated_at=menu_item.updated_at,
        )

    def _to_vendor_pickup_window_view(self, pickup_window_id: uuid.UUID) -> VendorPickupWindowView:
        pickup_window = self._require_vendor_pickup_window(pickup_window_id=pickup_window_id)
        return VendorPickupWindowView(
            id=pickup_window.id,
            vendor_id=pickup_window.vendor_id,
            label=pickup_window.label,
            status=pickup_window.status,
            pickup_start_at=pickup_window.pickup_start_at,
            pickup_end_at=pickup_window.pickup_end_at,
            order_cutoff_at=pickup_window.order_cutoff_at,
            notes=pickup_window.notes,
            created_at=pickup_window.created_at,
            updated_at=pickup_window.updated_at,
        )

    def _to_meal_plan_item_view(
        self,
        meal_plan_item_id: uuid.UUID,
        *,
        discoverable_only: bool,
    ) -> MealPlanItemView:
        meal_plan_item = self._require_meal_plan_item(meal_plan_item_id=meal_plan_item_id)
        items = self.list_meal_plan_items(
            meal_plan_id=meal_plan_item.meal_plan_id,
            discoverable_only=discoverable_only,
        )
        for item in items:
            if item.id == meal_plan_item_id:
                return item
        raise VendorNotFoundError("meal_plan_item_not_found")

    def _to_meal_plan_availability_view(
        self,
        availability_id: uuid.UUID,
        *,
        discoverable_only: bool,
    ) -> MealPlanAvailabilityView:
        availability = self._require_meal_plan_availability(availability_id=availability_id)
        items = self.list_meal_plan_availability(
            meal_plan_id=availability.meal_plan_id,
            discoverable_only=discoverable_only,
        )
        for item in items:
            if item.id == availability_id:
                return item
        raise VendorNotFoundError("meal_plan_availability_not_found")

    def _item_view_from_model(self, item: MealPlanItem) -> MealPlanItemView:
        return MealPlanItemView(
            id=item.id,
            vendor_menu_item_id=item.vendor_menu_item.id,
            slug=item.vendor_menu_item.slug,
            name=item.vendor_menu_item.name,
            quantity=item.quantity,
            position=item.position,
            notes=item.notes,
            price_cents=item.vendor_menu_item.price_cents,
            currency_code=item.vendor_menu_item.currency_code,
            calories=item.vendor_menu_item.calories,
        )

    def _availability_view_from_model(
        self,
        availability: MealPlanAvailability,
    ) -> MealPlanAvailabilityView:
        return MealPlanAvailabilityView(
            id=availability.id,
            pickup_window_id=availability.pickup_window.id,
            pickup_window_label=availability.pickup_window.label,
            pickup_start_at=availability.pickup_window.pickup_start_at,
            pickup_end_at=availability.pickup_window.pickup_end_at,
            availability_status=availability.status,
            pickup_window_status=availability.pickup_window.status.value,
            inventory_count=availability.inventory_count,
        )
