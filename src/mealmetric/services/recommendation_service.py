import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory
from mealmetric.models.recommendation import (
    MealPlanRecommendation,
    MealPlanRecommendationStatus,
)
from mealmetric.models.training import PtClientLinkStatus
from mealmetric.models.user import Role
from mealmetric.models.vendor import (
    MealPlan,
    MealPlanAvailabilityStatus,
    MealPlanStatus,
    VendorMenuItemStatus,
    VendorPickupWindowStatus,
    VendorStatus,
)
from mealmetric.repos import (
    audit_log_repo,
    recommendation_repo,
    training_repo,
    user_repo,
    vendor_repo,
)

_AVAILABLE_PICKUP_WINDOW_STATUSES = frozenset(
    {
        VendorPickupWindowStatus.SCHEDULED,
        VendorPickupWindowStatus.OPEN,
    }
)
_AVAILABLE_AVAILABILITY_STATUSES = frozenset(
    {
        MealPlanAvailabilityStatus.SCHEDULED,
        MealPlanAvailabilityStatus.AVAILABLE,
    }
)


class RecommendationServiceError(Exception):
    """Base recommendation-domain service error."""


class RecommendationConflictError(RecommendationServiceError):
    """Raised when a uniqueness/conflict condition is hit."""


class RecommendationNotFoundError(RecommendationServiceError):
    """Raised when a required resource does not exist."""


class RecommendationPermissionError(RecommendationServiceError):
    """Raised when the caller is outside the allowed scope."""


class RecommendationValidationError(RecommendationServiceError):
    """Raised when request data violates recommendation rules."""


@dataclass(frozen=True, slots=True)
class RecommendationMealPlanSummaryView:
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
class RecommendationPtAttributionView:
    id: uuid.UUID
    email: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class MealPlanRecommendationView:
    id: uuid.UUID
    pt_user_id: uuid.UUID
    client_user_id: uuid.UUID
    meal_plan_id: uuid.UUID
    status: MealPlanRecommendationStatus
    rationale: str | None
    recommended_at: datetime
    expires_at: datetime | None
    is_expired: bool
    created_at: datetime
    updated_at: datetime
    pt: RecommendationPtAttributionView
    meal_plan: RecommendationMealPlanSummaryView
    meal_plan_is_currently_discoverable: bool
    meal_plan_is_currently_available: bool


@dataclass(frozen=True, slots=True)
class MealPlanRecommendationListView:
    items: tuple[MealPlanRecommendationView, ...]
    count: int


class MealPlanRecommendationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_recommendation(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
        rationale: str | None,
        recommended_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> MealPlanRecommendationView:
        self._require_active_link(pt_user_id=pt_user_id, client_user_id=client_user_id)
        meal_plan = vendor_repo.get_meal_plan_by_id_for_update(
            self._session,
            meal_plan_id=meal_plan_id,
        )
        if meal_plan is None:
            raise RecommendationNotFoundError("meal_plan_not_found")

        recommendation_timestamp = recommended_at or datetime.now(UTC)
        self._validate_recommendation_times(
            recommended_at=recommendation_timestamp,
            expires_at=expires_at,
        )

        try:
            recommendation = recommendation_repo.create_recommendation(
                self._session,
                pt_user_id=pt_user_id,
                client_user_id=client_user_id,
                meal_plan_id=meal_plan.id,
                status=MealPlanRecommendationStatus.ACTIVE,
                rationale=rationale,
                recommended_at=recommendation_timestamp,
                expires_at=expires_at,
            )
        except IntegrityError as exc:
            raise RecommendationConflictError("meal_plan_recommendation_conflict") from exc

        audit_log_repo.append_event(
            self._session,
            category=AuditEventCategory.RECOMMENDATION,
            action=AuditEventAction.MEAL_PLAN_RECOMMENDATION_CREATED,
            actor_user_id=pt_user_id,
            actor_role=Role.PT,
            target_entity_type="meal_plan_recommendation",
            target_entity_id=recommendation.id,
            related_entity_type="meal_plan",
            related_entity_id=meal_plan.id,
            metadata={
                "pt_user_id": pt_user_id,
                "client_user_id": client_user_id,
                "meal_plan_id": meal_plan.id,
                "status": recommendation.status,
                "recommended_at": recommendation.recommended_at,
                "expires_at": recommendation.expires_at,
                "rationale": rationale,
            },
            message="PT created a meal plan recommendation",
        )

        return self._require_recommendation_view(recommendation.id)

    def list_recommendations_for_pt_client(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
    ) -> MealPlanRecommendationListView:
        self._require_active_link(pt_user_id=pt_user_id, client_user_id=client_user_id)
        recommendations = recommendation_repo.list_recommendations_for_pt_client(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        return self._to_list_view(recommendations)

    def list_recommendations_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
    ) -> MealPlanRecommendationListView:
        recommendations = recommendation_repo.list_recommendations_for_client(
            self._session,
            client_user_id=client_user_id,
        )
        return self._to_list_view(recommendations)

    def get_recommendation(
        self,
        *,
        recommendation_id: uuid.UUID,
    ) -> MealPlanRecommendationView:
        return self._require_recommendation_view(recommendation_id)

    def _require_active_link(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
    ) -> None:
        link = training_repo.get_pt_client_link_by_pair(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        if link is None or link.status != PtClientLinkStatus.ACTIVE:
            raise RecommendationPermissionError("pt_client_link_not_active")

    def _require_recommendation_view(
        self, recommendation_id: uuid.UUID
    ) -> MealPlanRecommendationView:
        recommendation = recommendation_repo.get_recommendation_by_id(
            self._session,
            recommendation_id=recommendation_id,
        )
        if recommendation is None:
            raise RecommendationNotFoundError("meal_plan_recommendation_not_found")
        return self._to_view(recommendation)

    def _to_list_view(
        self,
        recommendations: list[MealPlanRecommendation],
    ) -> MealPlanRecommendationListView:
        items = tuple(self._to_view(recommendation) for recommendation in recommendations)
        return MealPlanRecommendationListView(items=items, count=len(items))

    def _to_view(self, recommendation: MealPlanRecommendation) -> MealPlanRecommendationView:
        meal_plan = recommendation.meal_plan
        summary = self._build_meal_plan_summary(meal_plan)
        currently_available = self._meal_plan_is_currently_available(meal_plan)
        currently_discoverable = self._meal_plan_is_currently_discoverable(
            meal_plan,
            currently_available=currently_available,
        )
        return MealPlanRecommendationView(
            id=recommendation.id,
            pt_user_id=recommendation.pt_user_id,
            client_user_id=recommendation.client_user_id,
            meal_plan_id=recommendation.meal_plan_id,
            status=recommendation.status,
            rationale=recommendation.rationale,
            recommended_at=recommendation.recommended_at,
            expires_at=recommendation.expires_at,
            is_expired=self._is_expired(recommendation.expires_at),
            created_at=recommendation.created_at,
            updated_at=recommendation.updated_at,
            pt=self._build_pt_attribution(recommendation.pt_user_id),
            meal_plan=summary,
            meal_plan_is_currently_discoverable=currently_discoverable,
            meal_plan_is_currently_available=currently_available,
        )

    def _build_pt_attribution(
        self,
        pt_user_id: uuid.UUID,
    ) -> RecommendationPtAttributionView:
        user = user_repo.get_by_id(self._session, pt_user_id)
        if user is None:
            raise RecommendationNotFoundError("recommendation_pt_user_not_found")
        profile = training_repo.get_pt_profile_by_user_id(self._session, pt_user_id)
        return RecommendationPtAttributionView(
            id=user.id,
            email=user.email,
            display_name=profile.display_name if profile is not None else None,
        )

    def _build_meal_plan_summary(self, meal_plan: MealPlan) -> RecommendationMealPlanSummaryView:
        ordered_items = sorted(
            meal_plan.items,
            key=lambda item: (item.position, str(item.id)),
        )
        ordered_availability = sorted(
            meal_plan.availability_entries,
            key=lambda row: (row.pickup_window.pickup_start_at, str(row.id)),
        )
        total_price_cents = sum(
            item.vendor_menu_item.price_cents * item.quantity for item in ordered_items
        )
        total_calories = sum(
            (item.vendor_menu_item.calories or 0) * item.quantity for item in ordered_items
        )
        return RecommendationMealPlanSummaryView(
            id=meal_plan.id,
            vendor_id=meal_plan.vendor_id,
            slug=meal_plan.slug,
            name=meal_plan.name,
            description=meal_plan.description,
            status=meal_plan.status,
            total_price_cents=total_price_cents,
            total_calories=total_calories,
            item_count=len(ordered_items),
            availability_count=len(ordered_availability),
        )

    def _meal_plan_is_currently_available(self, meal_plan: MealPlan) -> bool:
        return any(
            availability.status in _AVAILABLE_AVAILABILITY_STATUSES
            and availability.pickup_window.status in _AVAILABLE_PICKUP_WINDOW_STATUSES
            and (availability.inventory_count is None or availability.inventory_count > 0)
            for availability in meal_plan.availability_entries
        )

    def _meal_plan_is_currently_discoverable(
        self,
        meal_plan: MealPlan,
        *,
        currently_available: bool,
    ) -> bool:
        vendor = meal_plan.vendor
        if vendor.status != VendorStatus.ACTIVE:
            return False
        if meal_plan.status != MealPlanStatus.PUBLISHED:
            return False
        if not meal_plan.items:
            return False
        if any(
            item.vendor_menu_item.status != VendorMenuItemStatus.ACTIVE for item in meal_plan.items
        ):
            return False
        return currently_available

    def _validate_recommendation_times(
        self,
        *,
        recommended_at: datetime,
        expires_at: datetime | None,
    ) -> None:
        if expires_at is not None and expires_at <= recommended_at:
            raise RecommendationValidationError("recommendation_expiry_invalid")

    @staticmethod
    def _is_expired(expires_at: datetime | None) -> bool:
        if expires_at is None:
            return False
        normalized_expires_at = (
            expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
        )
        return normalized_expires_at <= datetime.now(UTC)
