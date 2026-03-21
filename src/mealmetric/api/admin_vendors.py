from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.api.schemas.vendor import (
    AdminMealPlanAvailabilityCreateRequest,
    AdminMealPlanAvailabilityRead,
    AdminMealPlanAvailabilityUpdateRequest,
    AdminMealPlanCreateRequest,
    AdminMealPlanItemCreateRequest,
    AdminMealPlanItemRead,
    AdminMealPlanItemUpdateRequest,
    AdminMealPlanRead,
    AdminMealPlanUpdateRequest,
    AdminVendorCreateRequest,
    AdminVendorMenuItemCreateRequest,
    AdminVendorMenuItemRead,
    AdminVendorMenuItemUpdateRequest,
    AdminVendorPickupWindowCreateRequest,
    AdminVendorPickupWindowRead,
    AdminVendorPickupWindowUpdateRequest,
    AdminVendorRead,
    AdminVendorUpdateRequest,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role
from mealmetric.services.vendor_service import (
    MealPlanAvailabilityView,
    MealPlanDetailView,
    MealPlanItemView,
    MealPlanSummaryView,
    VendorConflictError,
    VendorDetailView,
    VendorMenuItemView,
    VendorNotFoundError,
    VendorPickupWindowView,
    VendorService,
    VendorValidationError,
)

router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.ADMIN))],
    tags=["admin-vendors"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    return db


def _translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VendorNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, VendorConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, VendorValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


def _run_mutation[T](db: Session, operation: Callable[[], T]) -> T:
    try:
        result = operation()
        db.commit()
        return result
    except (VendorNotFoundError, VendorConflictError, VendorValidationError) as exc:
        db.rollback()
        raise _translate_service_error(exc) from exc


def _item_to_read(item: MealPlanItemView) -> AdminMealPlanItemRead:
    return AdminMealPlanItemRead(
        id=item.id,
        vendor_menu_item_id=item.vendor_menu_item_id,
        slug=item.slug,
        name=item.name,
        quantity=item.quantity,
        position=item.position,
        notes=item.notes,
        price_cents=item.price_cents,
        currency_code=item.currency_code,
        calories=item.calories,
    )


def _availability_to_read(item: MealPlanAvailabilityView) -> AdminMealPlanAvailabilityRead:
    return AdminMealPlanAvailabilityRead(
        id=item.id,
        pickup_window_id=item.pickup_window_id,
        pickup_window_label=item.pickup_window_label,
        pickup_start_at=item.pickup_start_at,
        pickup_end_at=item.pickup_end_at,
        availability_status=item.availability_status,
        pickup_window_status=item.pickup_window_status,
        inventory_count=item.inventory_count,
    )


def _meal_plan_to_read(item: MealPlanDetailView) -> AdminMealPlanRead:
    return AdminMealPlanRead(
        id=item.id,
        vendor_id=item.vendor_id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        status=item.status,
        total_price_cents=item.total_price_cents,
        total_calories=item.total_calories,
        item_count=item.item_count,
        availability_count=item.availability_count,
        items=[_item_to_read(row) for row in item.items],
        availability=[_availability_to_read(row) for row in item.availability],
    )


def _meal_plan_summary_to_read(item: MealPlanSummaryView) -> AdminMealPlanRead:
    return AdminMealPlanRead(
        id=item.id,
        vendor_id=item.vendor_id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        status=item.status,
        total_price_cents=item.total_price_cents,
        total_calories=item.total_calories,
        item_count=item.item_count,
        availability_count=item.availability_count,
        items=[],
        availability=[],
    )


def _vendor_to_read(item: VendorDetailView) -> AdminVendorRead:
    return AdminVendorRead(
        id=item.id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        zip_code=item.zip_code,
        status=item.status,
        meal_plans=[_meal_plan_summary_to_read(plan) for plan in item.meal_plans],
        meal_plan_count=item.meal_plan_count,
    )


def _menu_item_to_read(item: VendorMenuItemView) -> AdminVendorMenuItemRead:
    return AdminVendorMenuItemRead(
        id=item.id,
        vendor_id=item.vendor_id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        status=item.status,
        price_cents=item.price_cents,
        currency_code=item.currency_code,
        calories=item.calories,
        protein_grams=item.protein_grams,
        carbs_grams=item.carbs_grams,
        fat_grams=item.fat_grams,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _pickup_window_to_read(item: VendorPickupWindowView) -> AdminVendorPickupWindowRead:
    return AdminVendorPickupWindowRead(
        id=item.id,
        vendor_id=item.vendor_id,
        label=item.label,
        status=item.status,
        pickup_start_at=item.pickup_start_at,
        pickup_end_at=item.pickup_end_at,
        order_cutoff_at=item.order_cutoff_at,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/vendors", response_model=AdminVendorRead, status_code=status.HTTP_201_CREATED)
def create_vendor(payload: AdminVendorCreateRequest, db: DBSessionDep) -> AdminVendorRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.create_vendor(
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            zip_code=payload.zip_code,
            status=payload.status,
        ),
    )
    return _vendor_to_read(result)


@router.patch("/vendors/{vendor_id}", response_model=AdminVendorRead)
def update_vendor(
    vendor_id: UUID,
    payload: AdminVendorUpdateRequest,
    db: DBSessionDep,
) -> AdminVendorRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.update_vendor(
            vendor_id=vendor_id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            zip_code=payload.zip_code,
            status=payload.status,
        ),
    )
    return _vendor_to_read(result)


@router.post("/vendors/{vendor_id}/archive", response_model=AdminVendorRead)
def archive_vendor(vendor_id: UUID, db: DBSessionDep) -> AdminVendorRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(session, lambda: service.archive_vendor(vendor_id=vendor_id))
    return _vendor_to_read(result)


@router.post(
    "/vendors/{vendor_id}/menu-items",
    response_model=AdminVendorMenuItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_menu_item(
    vendor_id: UUID,
    payload: AdminVendorMenuItemCreateRequest,
    db: DBSessionDep,
) -> AdminVendorMenuItemRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.create_vendor_menu_item(
            vendor_id=vendor_id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            price_cents=payload.price_cents,
            currency_code=payload.currency_code,
            calories=payload.calories,
            protein_grams=payload.protein_grams,
            carbs_grams=payload.carbs_grams,
            fat_grams=payload.fat_grams,
        ),
    )
    return _menu_item_to_read(result)


@router.patch(
    "/vendors/{vendor_id}/menu-items/{menu_item_id}", response_model=AdminVendorMenuItemRead
)
def update_vendor_menu_item(
    vendor_id: UUID,
    menu_item_id: UUID,
    payload: AdminVendorMenuItemUpdateRequest,
    db: DBSessionDep,
) -> AdminVendorMenuItemRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.update_vendor_menu_item(
            vendor_id=vendor_id,
            menu_item_id=menu_item_id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            price_cents=payload.price_cents,
            currency_code=payload.currency_code,
            calories=payload.calories,
            protein_grams=payload.protein_grams,
            carbs_grams=payload.carbs_grams,
            fat_grams=payload.fat_grams,
        ),
    )
    return _menu_item_to_read(result)


@router.post(
    "/vendors/{vendor_id}/menu-items/{menu_item_id}/archive", response_model=AdminVendorMenuItemRead
)
def archive_vendor_menu_item(
    vendor_id: UUID,
    menu_item_id: UUID,
    db: DBSessionDep,
) -> AdminVendorMenuItemRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.archive_vendor_menu_item(vendor_id=vendor_id, menu_item_id=menu_item_id),
    )
    return _menu_item_to_read(result)


@router.post(
    "/vendors/{vendor_id}/meal-plans",
    response_model=AdminMealPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meal_plan(
    vendor_id: UUID,
    payload: AdminMealPlanCreateRequest,
    db: DBSessionDep,
) -> AdminMealPlanRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.create_meal_plan(
            vendor_id=vendor_id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            status=payload.status,
        ),
    )
    return _meal_plan_to_read(result)


@router.patch("/vendors/{vendor_id}/meal-plans/{meal_plan_id}", response_model=AdminMealPlanRead)
def update_meal_plan(
    vendor_id: UUID,
    meal_plan_id: UUID,
    payload: AdminMealPlanUpdateRequest,
    db: DBSessionDep,
) -> AdminMealPlanRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.update_meal_plan(
            vendor_id=vendor_id,
            meal_plan_id=meal_plan_id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            status=payload.status,
        ),
    )
    return _meal_plan_to_read(result)


@router.post(
    "/vendors/{vendor_id}/meal-plans/{meal_plan_id}/archive", response_model=AdminMealPlanRead
)
def archive_meal_plan(
    vendor_id: UUID,
    meal_plan_id: UUID,
    db: DBSessionDep,
) -> AdminMealPlanRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.archive_meal_plan(vendor_id=vendor_id, meal_plan_id=meal_plan_id),
    )
    return _meal_plan_to_read(result)


@router.post(
    "/meal-plans/{meal_plan_id}/items",
    response_model=AdminMealPlanItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meal_plan_item(
    meal_plan_id: UUID,
    payload: AdminMealPlanItemCreateRequest,
    db: DBSessionDep,
) -> AdminMealPlanItemRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.create_meal_plan_item(
            meal_plan_id=meal_plan_id,
            vendor_menu_item_id=payload.vendor_menu_item_id,
            quantity=payload.quantity,
            position=payload.position,
            notes=payload.notes,
        ),
    )
    return _item_to_read(result)


@router.patch(
    "/meal-plans/{meal_plan_id}/items/{meal_plan_item_id}", response_model=AdminMealPlanItemRead
)
def update_meal_plan_item(
    meal_plan_id: UUID,
    meal_plan_item_id: UUID,
    payload: AdminMealPlanItemUpdateRequest,
    db: DBSessionDep,
) -> AdminMealPlanItemRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.update_meal_plan_item(
            meal_plan_id=meal_plan_id,
            meal_plan_item_id=meal_plan_item_id,
            vendor_menu_item_id=payload.vendor_menu_item_id,
            quantity=payload.quantity,
            position=payload.position,
            notes=payload.notes,
        ),
    )
    return _item_to_read(result)


@router.delete(
    "/meal-plans/{meal_plan_id}/items/{meal_plan_item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_meal_plan_item(
    meal_plan_id: UUID,
    meal_plan_item_id: UUID,
    db: DBSessionDep,
) -> Response:
    session = _require_db(db)
    service = VendorService(session)
    _run_mutation(
        session,
        lambda: service.delete_meal_plan_item(
            meal_plan_id=meal_plan_id,
            meal_plan_item_id=meal_plan_item_id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/vendors/{vendor_id}/pickup-windows",
    response_model=AdminVendorPickupWindowRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_pickup_window(
    vendor_id: UUID,
    payload: AdminVendorPickupWindowCreateRequest,
    db: DBSessionDep,
) -> AdminVendorPickupWindowRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.create_vendor_pickup_window(
            vendor_id=vendor_id,
            label=payload.label,
            status=payload.status,
            pickup_start_at=payload.pickup_start_at,
            pickup_end_at=payload.pickup_end_at,
            order_cutoff_at=payload.order_cutoff_at,
            notes=payload.notes,
        ),
    )
    return _pickup_window_to_read(result)


@router.patch(
    "/vendors/{vendor_id}/pickup-windows/{pickup_window_id}",
    response_model=AdminVendorPickupWindowRead,
)
def update_vendor_pickup_window(
    vendor_id: UUID,
    pickup_window_id: UUID,
    payload: AdminVendorPickupWindowUpdateRequest,
    db: DBSessionDep,
) -> AdminVendorPickupWindowRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.update_vendor_pickup_window(
            vendor_id=vendor_id,
            pickup_window_id=pickup_window_id,
            label=payload.label,
            status=payload.status,
            pickup_start_at=payload.pickup_start_at,
            pickup_end_at=payload.pickup_end_at,
            order_cutoff_at=payload.order_cutoff_at,
            notes=payload.notes,
        ),
    )
    return _pickup_window_to_read(result)


@router.post(
    "/vendors/{vendor_id}/pickup-windows/{pickup_window_id}/cancel",
    response_model=AdminVendorPickupWindowRead,
)
def cancel_vendor_pickup_window(
    vendor_id: UUID,
    pickup_window_id: UUID,
    db: DBSessionDep,
) -> AdminVendorPickupWindowRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.cancel_vendor_pickup_window(
            vendor_id=vendor_id,
            pickup_window_id=pickup_window_id,
        ),
    )
    return _pickup_window_to_read(result)


@router.post(
    "/meal-plans/{meal_plan_id}/availability",
    response_model=AdminMealPlanAvailabilityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meal_plan_availability(
    meal_plan_id: UUID,
    payload: AdminMealPlanAvailabilityCreateRequest,
    db: DBSessionDep,
) -> AdminMealPlanAvailabilityRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.create_meal_plan_availability(
            meal_plan_id=meal_plan_id,
            pickup_window_id=payload.pickup_window_id,
            status=payload.status,
            inventory_count=payload.inventory_count,
        ),
    )
    return _availability_to_read(result)


@router.patch(
    "/meal-plans/{meal_plan_id}/availability/{availability_id}",
    response_model=AdminMealPlanAvailabilityRead,
)
def update_meal_plan_availability(
    meal_plan_id: UUID,
    availability_id: UUID,
    payload: AdminMealPlanAvailabilityUpdateRequest,
    db: DBSessionDep,
) -> AdminMealPlanAvailabilityRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.update_meal_plan_availability(
            meal_plan_id=meal_plan_id,
            availability_id=availability_id,
            pickup_window_id=payload.pickup_window_id,
            status=payload.status,
            inventory_count=payload.inventory_count,
        ),
    )
    return _availability_to_read(result)


@router.post(
    "/meal-plans/{meal_plan_id}/availability/{availability_id}/cancel",
    response_model=AdminMealPlanAvailabilityRead,
)
def cancel_meal_plan_availability(
    meal_plan_id: UUID,
    availability_id: UUID,
    db: DBSessionDep,
) -> AdminMealPlanAvailabilityRead:
    session = _require_db(db)
    service = VendorService(session)
    result = _run_mutation(
        session,
        lambda: service.cancel_meal_plan_availability(
            meal_plan_id=meal_plan_id,
            availability_id=availability_id,
        ),
    )
    return _availability_to_read(result)
