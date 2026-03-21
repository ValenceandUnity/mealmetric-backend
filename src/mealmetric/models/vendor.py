import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base


class VendorStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class VendorMenuItemStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class MealPlanStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"


class VendorPickupWindowStatus(StrEnum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class MealPlanAvailabilityStatus(StrEnum):
    SCHEDULED = "scheduled"
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_vendors_slug"),
        UniqueConstraint("id", "slug", name="uq_vendors_id_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    status: Mapped[VendorStatus] = mapped_column(
        Enum(
            VendorStatus,
            name="vendor_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=VendorStatus.DRAFT,
        server_default=VendorStatus.DRAFT.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    menu_items: Mapped[list["VendorMenuItem"]] = relationship(
        "VendorMenuItem", back_populates="vendor"
    )
    meal_plans: Mapped[list["MealPlan"]] = relationship("MealPlan", back_populates="vendor")
    pickup_windows: Mapped[list["VendorPickupWindow"]] = relationship(
        "VendorPickupWindow", back_populates="vendor"
    )


class VendorMenuItem(Base):
    __tablename__ = "vendor_menu_items"
    __table_args__ = (
        UniqueConstraint("vendor_id", "slug", name="uq_vendor_menu_items_vendor_id_slug"),
        UniqueConstraint("id", "vendor_id", name="uq_vendor_menu_items_id_vendor_id"),
        CheckConstraint("price_cents >= 0", name="ck_vendor_menu_items_price_cents_non_negative"),
        CheckConstraint(
            "calories IS NULL OR calories >= 0",
            name="ck_vendor_menu_items_calories_non_negative",
        ),
        CheckConstraint(
            "protein_grams IS NULL OR protein_grams >= 0",
            name="ck_vendor_menu_items_protein_grams_non_negative",
        ),
        CheckConstraint(
            "carbs_grams IS NULL OR carbs_grams >= 0",
            name="ck_vendor_menu_items_carbs_grams_non_negative",
        ),
        CheckConstraint(
            "fat_grams IS NULL OR fat_grams >= 0",
            name="ck_vendor_menu_items_fat_grams_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VendorMenuItemStatus] = mapped_column(
        Enum(
            VendorMenuItemStatus,
            name="vendor_menu_item_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=VendorMenuItemStatus.DRAFT,
        server_default=VendorMenuItemStatus.DRAFT.value,
        index=True,
    )
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    carbs_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fat_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="menu_items")
    meal_plan_items: Mapped[list["MealPlanItem"]] = relationship(
        "MealPlanItem",
        back_populates="vendor_menu_item",
        overlaps="items,meal_plan",
    )


class MealPlan(Base):
    __tablename__ = "meal_plans"
    __table_args__ = (
        UniqueConstraint("vendor_id", "slug", name="uq_meal_plans_vendor_id_slug"),
        UniqueConstraint("id", "vendor_id", name="uq_meal_plans_id_vendor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MealPlanStatus] = mapped_column(
        Enum(
            MealPlanStatus,
            name="meal_plan_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=MealPlanStatus.DRAFT,
        server_default=MealPlanStatus.DRAFT.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="meal_plans")
    items: Mapped[list["MealPlanItem"]] = relationship(
        "MealPlanItem",
        back_populates="meal_plan",
        overlaps="meal_plan_items,vendor_menu_item",
    )
    availability_entries: Mapped[list["MealPlanAvailability"]] = relationship(
        "MealPlanAvailability",
        back_populates="meal_plan",
        overlaps="availability_entries,pickup_window",
    )


class VendorPickupWindow(Base):
    __tablename__ = "vendor_pickup_windows"
    __table_args__ = (
        UniqueConstraint("id", "vendor_id", name="uq_vendor_pickup_windows_id_vendor_id"),
        CheckConstraint(
            "pickup_end_at > pickup_start_at",
            name="ck_vendor_pickup_windows_pickup_window_ordered",
        ),
        CheckConstraint(
            "order_cutoff_at IS NULL OR order_cutoff_at <= pickup_start_at",
            name="ck_vendor_pickup_windows_order_cutoff_before_pickup_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[VendorPickupWindowStatus] = mapped_column(
        Enum(
            VendorPickupWindowStatus,
            name="vendor_pickup_window_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=VendorPickupWindowStatus.SCHEDULED,
        server_default=VendorPickupWindowStatus.SCHEDULED.value,
        index=True,
    )
    pickup_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    pickup_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    order_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="pickup_windows")
    availability_entries: Mapped[list["MealPlanAvailability"]] = relationship(
        "MealPlanAvailability",
        back_populates="pickup_window",
        overlaps="availability_entries,meal_plan",
    )


class MealPlanItem(Base):
    __tablename__ = "meal_plan_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meal_plan_id", "vendor_id"],
            ["meal_plans.id", "meal_plans.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_items_meal_plan_vendor_pair",
        ),
        ForeignKeyConstraint(
            ["vendor_menu_item_id", "vendor_id"],
            ["vendor_menu_items.id", "vendor_menu_items.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_items_menu_item_vendor_pair",
        ),
        UniqueConstraint(
            "meal_plan_id",
            "position",
            name="uq_meal_plan_items_meal_plan_id_position",
        ),
        UniqueConstraint(
            "meal_plan_id",
            "vendor_menu_item_id",
            name="uq_meal_plan_items_meal_plan_id_vendor_menu_item_id",
        ),
        CheckConstraint("quantity > 0", name="ck_meal_plan_items_quantity_positive"),
        CheckConstraint("position >= 0", name="ck_meal_plan_items_position_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    meal_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    vendor_menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    meal_plan: Mapped["MealPlan"] = relationship(
        "MealPlan",
        back_populates="items",
        overlaps="meal_plan_items,vendor_menu_item",
    )
    vendor_menu_item: Mapped["VendorMenuItem"] = relationship(
        "VendorMenuItem",
        back_populates="meal_plan_items",
        overlaps="items,meal_plan",
    )


class MealPlanAvailability(Base):
    __tablename__ = "meal_plan_availability"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meal_plan_id", "vendor_id"],
            ["meal_plans.id", "meal_plans.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_availability_meal_plan_vendor_pair",
        ),
        ForeignKeyConstraint(
            ["pickup_window_id", "vendor_id"],
            ["vendor_pickup_windows.id", "vendor_pickup_windows.vendor_id"],
            ondelete="RESTRICT",
            name="fk_meal_plan_availability_pickup_window_vendor_pair",
        ),
        UniqueConstraint(
            "meal_plan_id",
            "pickup_window_id",
            name="uq_meal_plan_availability_meal_plan_id_pickup_window_id",
        ),
        CheckConstraint(
            "inventory_count IS NULL OR inventory_count >= 0",
            name="ck_meal_plan_availability_inventory_count_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    meal_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    pickup_window_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[MealPlanAvailabilityStatus] = mapped_column(
        Enum(
            MealPlanAvailabilityStatus,
            name="meal_plan_availability_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=MealPlanAvailabilityStatus.SCHEDULED,
        server_default=MealPlanAvailabilityStatus.SCHEDULED.value,
        index=True,
    )
    inventory_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    meal_plan: Mapped["MealPlan"] = relationship(
        "MealPlan",
        back_populates="availability_entries",
        overlaps="availability_entries,pickup_window",
    )
    pickup_window: Mapped["VendorPickupWindow"] = relationship(
        "VendorPickupWindow",
        back_populates="availability_entries",
        overlaps="availability_entries,meal_plan",
    )
