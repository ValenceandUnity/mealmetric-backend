import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from mealmetric.api.schemas.vendor import MealPlanSummaryRead


class BookmarkFolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class BookmarkItemCreateRequest(BaseModel):
    meal_plan_id: uuid.UUID
    note: str | None = None


class BookmarkItemRead(BaseModel):
    id: uuid.UUID
    meal_plan_id: uuid.UUID
    note: str | None
    created_at: datetime
    meal_plan: MealPlanSummaryRead


class BookmarkFolderRead(BaseModel):
    id: uuid.UUID
    client_user_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    items: list[BookmarkItemRead]


class BookmarkFolderListResponse(BaseModel):
    items: list[BookmarkFolderRead]
    count: int
