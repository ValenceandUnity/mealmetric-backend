import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from mealmetric.models.vendor import (
    MealPlanAvailabilityStatus,
    MealPlanStatus,
    VendorMenuItemStatus,
    VendorPickupWindowStatus,
    VendorStatus,
)


class AdminVendorCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    zip_code: str | None = Field(default=None, max_length=16)
    status: VendorStatus = VendorStatus.DRAFT


class AdminVendorUpdateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    zip_code: str | None = Field(default=None, max_length=16)
    status: VendorStatus


class AdminVendorMenuItemCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: VendorMenuItemStatus = VendorMenuItemStatus.DRAFT
    price_cents: int = Field(ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    calories: int | None = Field(default=None, ge=0)
    protein_grams: int | None = Field(default=None, ge=0)
    carbs_grams: int | None = Field(default=None, ge=0)
    fat_grams: int | None = Field(default=None, ge=0)


class AdminVendorMenuItemUpdateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: VendorMenuItemStatus
    price_cents: int = Field(ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    calories: int | None = Field(default=None, ge=0)
    protein_grams: int | None = Field(default=None, ge=0)
    carbs_grams: int | None = Field(default=None, ge=0)
    fat_grams: int | None = Field(default=None, ge=0)


class AdminMealPlanCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: MealPlanStatus = MealPlanStatus.DRAFT


class AdminMealPlanUpdateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: MealPlanStatus


class AdminMealPlanItemCreateRequest(BaseModel):
    vendor_menu_item_id: uuid.UUID
    quantity: int = Field(ge=1)
    position: int = Field(ge=0)
    notes: str | None = None


class AdminMealPlanItemUpdateRequest(BaseModel):
    vendor_menu_item_id: uuid.UUID
    quantity: int = Field(ge=1)
    position: int = Field(ge=0)
    notes: str | None = None


class AdminVendorPickupWindowCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    status: VendorPickupWindowStatus = VendorPickupWindowStatus.SCHEDULED
    pickup_start_at: datetime
    pickup_end_at: datetime
    order_cutoff_at: datetime | None = None
    notes: str | None = None


class AdminVendorPickupWindowUpdateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    status: VendorPickupWindowStatus
    pickup_start_at: datetime
    pickup_end_at: datetime
    order_cutoff_at: datetime | None = None
    notes: str | None = None


class AdminMealPlanAvailabilityCreateRequest(BaseModel):
    pickup_window_id: uuid.UUID
    status: MealPlanAvailabilityStatus = MealPlanAvailabilityStatus.SCHEDULED
    inventory_count: int | None = Field(default=None, ge=0)


class AdminMealPlanAvailabilityUpdateRequest(BaseModel):
    pickup_window_id: uuid.UUID
    status: MealPlanAvailabilityStatus
    inventory_count: int | None = Field(default=None, ge=0)


class MealPlanItemRead(BaseModel):
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


class MealPlanAvailabilityRead(BaseModel):
    id: uuid.UUID
    pickup_window_id: uuid.UUID
    pickup_window_label: str | None
    pickup_start_at: datetime
    pickup_end_at: datetime
    availability_status: MealPlanAvailabilityStatus
    pickup_window_status: str
    inventory_count: int | None


class MealPlanSummaryRead(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str
    vendor_zip_code: str | None
    slug: str
    name: str
    description: str | None
    status: MealPlanStatus
    total_price_cents: int
    total_calories: int
    item_count: int
    availability_count: int


class MealPlanRead(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str
    vendor_zip_code: str | None
    slug: str
    name: str
    description: str | None
    status: MealPlanStatus
    total_price_cents: int
    total_calories: int
    item_count: int
    availability_count: int
    items: list[MealPlanItemRead]
    availability: list[MealPlanAvailabilityRead]


class MealPlanListResponse(BaseModel):
    items: list[MealPlanSummaryRead]
    count: int


class MealPlanAvailabilityListResponse(BaseModel):
    items: list[MealPlanAvailabilityRead]
    count: int


class VendorSummaryRead(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: VendorStatus
    meal_plan_count: int


class VendorRead(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    zip_code: str | None
    status: VendorStatus
    meal_plans: list[MealPlanSummaryRead]
    meal_plan_count: int


class VendorListResponse(BaseModel):
    items: list[VendorSummaryRead]
    count: int


class AdminMealPlanItemRead(BaseModel):
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


class AdminMealPlanAvailabilityRead(BaseModel):
    id: uuid.UUID
    pickup_window_id: uuid.UUID
    pickup_window_label: str | None
    pickup_start_at: datetime
    pickup_end_at: datetime
    availability_status: MealPlanAvailabilityStatus
    pickup_window_status: str
    inventory_count: int | None


class AdminMealPlanRead(BaseModel):
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
    items: list[AdminMealPlanItemRead]
    availability: list[AdminMealPlanAvailabilityRead]


class AdminVendorSummaryRead(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: VendorStatus
    meal_plan_count: int


class AdminVendorRead(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    zip_code: str | None
    status: VendorStatus
    meal_plans: list[AdminMealPlanRead]
    meal_plan_count: int


class VendorPortalIdentityRead(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    zip_code: str | None
    status: VendorStatus
    meal_plan_count: int


class VendorPortalMeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    vendor_ids: list[uuid.UUID]
    default_vendor: VendorPortalIdentityRead | None
    vendors: list[VendorPortalIdentityRead]


class VendorMetricsResponse(BaseModel):
    vendor_id: uuid.UUID
    vendor_name: str
    zip_code: str | None
    total_meal_plans: int
    published_meal_plans: int
    draft_meal_plans: int
    total_availability_entries: int
    open_pickup_windows: int


class AdminVendorMenuItemRead(BaseModel):
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


class AdminVendorPickupWindowRead(BaseModel):
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
