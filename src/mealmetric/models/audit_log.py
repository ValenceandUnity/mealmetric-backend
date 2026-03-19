import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mealmetric.db.base import Base


class AuditEventCategory(StrEnum):
    TRAINING = "training"
    METRICS = "metrics"
    RECOMMENDATION = "recommendation"


class AuditEventAction(StrEnum):
    PT_CLIENT_ASSIGNMENT_CREATED = "pt_client_assignment_created"
    PT_CLIENT_ASSIGNMENT_STATUS_UPDATED = "pt_client_assignment_status_updated"
    METRICS_WEEKLY_ROLLUP_UPSERTED = "metrics_weekly_rollup_upserted"
    METRICS_STRENGTH_ROLLUP_UPSERTED = "metrics_strength_rollup_upserted"
    METRICS_CLIENT_SNAPSHOT_UPSERTED = "metrics_client_snapshot_upserted"
    MEAL_PLAN_RECOMMENDATION_CREATED = "meal_plan_recommendation_created"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[AuditEventCategory] = mapped_column(
        Enum(
            AuditEventCategory,
            name="audit_event_category",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        index=True,
    )
    action: Mapped[AuditEventAction] = mapped_column(
        Enum(
            AuditEventAction,
            name="audit_event_action",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
