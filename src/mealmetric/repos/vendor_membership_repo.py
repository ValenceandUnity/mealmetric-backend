import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from mealmetric.models.vendor_membership import VendorUserMembership


def list_vendor_ids_for_user(session: Session, *, user_id: uuid.UUID) -> list[uuid.UUID]:
    stmt: Select[tuple[uuid.UUID]] = (
        select(VendorUserMembership.vendor_id)
        .where(VendorUserMembership.user_id == user_id)
        .order_by(VendorUserMembership.vendor_id.asc())
    )
    return list(session.scalars(stmt))
