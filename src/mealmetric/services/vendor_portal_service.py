import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mealmetric.models.user import User
from mealmetric.models.vendor import MealPlanStatus
from mealmetric.repos import vendor_membership_repo, vendor_repo
from mealmetric.services.vendor_service import MealPlanListView, VendorDetailView, VendorService


class VendorPortalError(Exception):
    """Base vendor portal service error."""


class VendorPortalAccessError(VendorPortalError):
    """Raised when a vendor user cannot access a vendor resource."""


@dataclass(frozen=True, slots=True)
class VendorPortalMeView:
    user_id: uuid.UUID
    email: str
    vendor_ids: tuple[uuid.UUID, ...]
    default_vendor: VendorDetailView | None
    vendors: tuple[VendorDetailView, ...]


@dataclass(frozen=True, slots=True)
class VendorMetricsView:
    vendor_id: uuid.UUID
    vendor_name: str
    zip_code: str | None
    total_meal_plans: int
    published_meal_plans: int
    draft_meal_plans: int
    total_availability_entries: int
    open_pickup_windows: int


class VendorPortalService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._vendor_service = VendorService(session)

    def get_me(self, *, current_user: User) -> VendorPortalMeView:
        vendor_ids = tuple(
            vendor_membership_repo.list_vendor_ids_for_user(self._session, user_id=current_user.id)
        )
        vendors = tuple(
            view
            for vendor_id in vendor_ids
            if (
                view := self._vendor_service.get_vendor_detail(
                    vendor_id=vendor_id,
                    discoverable_only=False,
                )
            )
            is not None
        )
        return VendorPortalMeView(
            user_id=current_user.id,
            email=current_user.email,
            vendor_ids=vendor_ids,
            default_vendor=vendors[0] if vendors else None,
            vendors=vendors,
        )

    def list_meal_plans(
        self,
        *,
        current_user: User,
        vendor_id: uuid.UUID | None = None,
    ) -> MealPlanListView:
        resolved_vendor_id = self._resolve_vendor_id(current_user=current_user, vendor_id=vendor_id)
        return self._vendor_service.list_meal_plans(
            vendor_id=resolved_vendor_id,
            discoverable_only=False,
        )

    def get_metrics(
        self,
        *,
        current_user: User,
        vendor_id: uuid.UUID | None = None,
    ) -> VendorMetricsView:
        resolved_vendor_id = self._resolve_vendor_id(current_user=current_user, vendor_id=vendor_id)
        vendor = self._vendor_service.get_vendor_detail(
            vendor_id=resolved_vendor_id,
            discoverable_only=False,
        )
        if vendor is None:
            raise VendorPortalAccessError("vendor_not_found")

        meal_plans = self._vendor_service.list_meal_plans(
            vendor_id=resolved_vendor_id,
            discoverable_only=False,
        )
        availability = self._vendor_service.list_meal_plan_availability(
            vendor_id=resolved_vendor_id,
            discoverable_only=False,
        )
        pickup_windows = vendor_repo.list_vendor_pickup_windows(
            self._session,
            vendor_id=resolved_vendor_id,
            discoverable_only=False,
        )
        return VendorMetricsView(
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            zip_code=vendor.zip_code,
            total_meal_plans=meal_plans.count,
            published_meal_plans=sum(
                1 for item in meal_plans.items if item.status == MealPlanStatus.PUBLISHED
            ),
            draft_meal_plans=sum(
                1 for item in meal_plans.items if item.status == MealPlanStatus.DRAFT
            ),
            total_availability_entries=len(availability),
            open_pickup_windows=sum(
                1 for window in pickup_windows if window.status.value in {"scheduled", "open"}
            ),
        )

    def _resolve_vendor_id(
        self,
        *,
        current_user: User,
        vendor_id: uuid.UUID | None,
    ) -> uuid.UUID:
        vendor_ids = vendor_membership_repo.list_vendor_ids_for_user(
            self._session, user_id=current_user.id
        )
        if not vendor_ids:
            raise VendorPortalAccessError("vendor_membership_not_found")
        if vendor_id is None:
            return vendor_ids[0]
        if vendor_id not in vendor_ids:
            raise VendorPortalAccessError("vendor_forbidden")
        return vendor_id
