from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.api.schemas.admin_payments import (
    AdminOrderItemRead,
    AdminOrderListResponse,
    AdminOrderRead,
)
from mealmetric.db.session import get_db
from mealmetric.models.order import OrderFulfillmentStatus, OrderPaymentStatus
from mealmetric.models.user import Role
from mealmetric.services.order_service import OrderService, OrderWithItems

router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.ADMIN))],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


def _to_admin_order_read(order_with_items: OrderWithItems) -> AdminOrderRead:
    order = order_with_items.order
    items = [
        AdminOrderItemRead(
            id=item.id,
            item_type=item.item_type,
            external_price_id=item.external_price_id,
            description=item.description,
            quantity=item.quantity,
            unit_amount_cents=item.unit_amount_cents,
            subtotal_amount_cents=item.subtotal_amount_cents,
            tax_amount_cents=item.tax_amount_cents,
            total_amount_cents=item.total_amount_cents,
            created_at=item.created_at,
        )
        for item in order_with_items.items
    ]
    return AdminOrderRead(
        id=order.id,
        payment_session_id=order.payment_session_id,
        client_user_id=order.client_user_id,
        order_payment_status=order.order_payment_status,
        fulfillment_status=order.fulfillment_status,
        currency=order.currency,
        subtotal_amount_cents=order.subtotal_amount_cents,
        tax_amount_cents=order.tax_amount_cents,
        total_amount_cents=order.total_amount_cents,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items,
    )


@router.get("/orders", response_model=AdminOrderListResponse)
def list_orders(
    db: DBSessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    payment_session_id: UUID | None = None,
    user_id: UUID | None = None,
    order_payment_status: OrderPaymentStatus | None = None,
    fulfillment_status: OrderFulfillmentStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminOrderListResponse:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    service = OrderService(db)
    orders = service.list_orders_for_admin(
        limit=limit,
        offset=offset,
        payment_session_id=payment_session_id,
        user_id=user_id,
        order_payment_status=order_payment_status,
        fulfillment_status=fulfillment_status,
        created_from=created_from,
        created_to=created_to,
    )
    items = [_to_admin_order_read(order) for order in orders]
    return AdminOrderListResponse(items=items, count=len(items))


@router.get("/orders/{order_id}", response_model=AdminOrderRead)
def get_order(order_id: UUID, db: DBSessionDep) -> AdminOrderRead:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    service = OrderService(db)
    order = service.get_order_by_id(order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order_not_found")

    return _to_admin_order_read(order)


@router.get("/payment-sessions/{payment_session_id}/order", response_model=AdminOrderRead)
def get_order_by_payment_session(payment_session_id: UUID, db: DBSessionDep) -> AdminOrderRead:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )

    service = OrderService(db)
    order = service.get_order_by_payment_session_id(payment_session_id=payment_session_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order_not_found")

    return _to_admin_order_read(order)
