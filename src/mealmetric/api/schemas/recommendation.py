import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mealmetric.models.recommendation import MealPlanRecommendationStatus
from mealmetric.models.vendor import MealPlanStatus


class MealPlanRecommendationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meal_plan_id: uuid.UUID
    rationale: str | None = Field(default=None, max_length=4000)
    recommended_at: datetime | None = None
    expires_at: datetime | None = None


class RecommendationMealPlanSummaryRead(BaseModel):
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


class RecommendationPtAttributionRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None


class MealPlanRecommendationRead(BaseModel):
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
    pt: RecommendationPtAttributionRead
    meal_plan: RecommendationMealPlanSummaryRead
    meal_plan_is_currently_discoverable: bool
    meal_plan_is_currently_available: bool


class MealPlanRecommendationListResponse(BaseModel):
    items: list[MealPlanRecommendationRead]
    count: int
