import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base


class MealPlanRecommendationStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class MealPlanRecommendation(Base):
    __tablename__ = "pt_meal_plan_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    meal_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[MealPlanRecommendationStatus] = mapped_column(
        Enum(
            MealPlanRecommendationStatus,
            name="meal_plan_recommendation_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=MealPlanRecommendationStatus.ACTIVE,
        server_default=MealPlanRecommendationStatus.ACTIVE.value,
        index=True,
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    meal_plan = relationship("MealPlan")
