import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base

if TYPE_CHECKING:
    from mealmetric.models.user import User


class MetricRecordSource(StrEnum):
    MANUAL = "manual"
    BFF_IMPORT = "bff_import"
    DEVICE = "device"
    BACKFILL = "backfill"


class DeficitTargetStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CalorieIntakeRecord(Base):
    __tablename__ = "calorie_intake_records"
    __table_args__ = (
        UniqueConstraint(
            "client_user_id",
            "ingestion_key",
            name="uq_calorie_intake_records_client_user_id_ingestion_key",
        ),
        CheckConstraint("calories >= 0", name="ck_calorie_intake_records_calories_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    calories: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[MetricRecordSource] = mapped_column(
        Enum(
            MetricRecordSource,
            name="metric_record_source",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=MetricRecordSource.MANUAL,
        server_default=MetricRecordSource.MANUAL.value,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ingestion_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")


class ActivityExpenditureRecord(Base):
    __tablename__ = "activity_expenditure_records"
    __table_args__ = (
        UniqueConstraint(
            "client_user_id",
            "ingestion_key",
            name="uq_activity_expenditure_records_client_user_id_ingestion_key",
        ),
        CheckConstraint(
            "expenditure_calories >= 0",
            name="ck_activity_expenditure_records_expenditure_calories_non_negative",
        ),
        CheckConstraint(
            "activity_minutes IS NULL OR activity_minutes >= 0",
            name="ck_activity_expenditure_records_activity_minutes_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expenditure_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[MetricRecordSource] = mapped_column(
        Enum(
            MetricRecordSource,
            name="metric_record_source",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=MetricRecordSource.MANUAL,
        server_default=MetricRecordSource.MANUAL.value,
    )
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ingestion_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")


class DeficitTarget(Base):
    __tablename__ = "deficit_targets"
    __table_args__ = (
        UniqueConstraint(
            "client_user_id",
            "effective_from_date",
            name="uq_deficit_targets_client_user_id_effective_from_date",
        ),
        CheckConstraint(
            "target_daily_deficit_calories >= 0",
            name="ck_deficit_targets_target_daily_deficit_non_negative",
        ),
        CheckConstraint(
            "effective_to_date IS NULL OR effective_to_date >= effective_from_date",
            name="ck_deficit_targets_effective_window_ordered",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_daily_deficit_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DeficitTargetStatus] = mapped_column(
        Enum(
            DeficitTargetStatus,
            name="deficit_target_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=DeficitTargetStatus.ACTIVE,
        server_default=DeficitTargetStatus.ACTIVE.value,
        index=True,
    )
    effective_from_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")


class WeeklyMetricRollup(Base):
    __tablename__ = "weekly_metric_rollups"
    __table_args__ = (
        UniqueConstraint(
            "client_user_id",
            "week_start_date",
            name="uq_weekly_metric_rollups_client_user_id_week_start_date",
        ),
        CheckConstraint(
            "week_start_day = 1", name="ck_weekly_metric_rollups_week_start_day_monday"
        ),
        CheckConstraint(
            "business_timezone = 'America/New_York'",
            name="ck_weekly_metric_rollups_business_timezone",
        ),
        CheckConstraint(
            "total_intake_calories >= 0",
            name="ck_weekly_metric_rollups_total_intake_non_negative",
        ),
        CheckConstraint(
            "total_expenditure_calories >= 0",
            name="ck_weekly_metric_rollups_total_expenditure_non_negative",
        ),
        CheckConstraint(
            "target_deficit_calories IS NULL OR target_deficit_calories >= 0",
            name="ck_weekly_metric_rollups_target_deficit_non_negative",
        ),
        CheckConstraint(
            "deficit_progress_percent IS NULL OR "
            "(deficit_progress_percent >= 0 AND deficit_progress_percent <= 100)",
            name="ck_weekly_metric_rollups_deficit_progress_bounds",
        ),
        CheckConstraint(
            "source_window_end >= source_window_start",
            name="ck_weekly_metric_rollups_source_window_ordered",
        ),
        CheckConstraint("version >= 1", name="ck_weekly_metric_rollups_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_start_day: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    business_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/New_York", server_default="America/New_York"
    )
    total_intake_calories: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_expenditure_calories: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    net_calorie_balance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    target_deficit_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deficit_progress_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")


class StrengthMetricRollup(Base):
    __tablename__ = "strength_metric_rollups"
    __table_args__ = (
        UniqueConstraint(
            "client_user_id",
            "week_start_date",
            name="uq_strength_metric_rollups_client_user_id_week_start_date",
        ),
        CheckConstraint(
            "week_start_day = 1",
            name="ck_strength_metric_rollups_week_start_day_monday",
        ),
        CheckConstraint(
            "business_timezone = 'America/New_York'",
            name="ck_strength_metric_rollups_business_timezone",
        ),
        CheckConstraint(
            "total_workouts >= 0",
            name="ck_strength_metric_rollups_total_workouts_non_negative",
        ),
        CheckConstraint(
            "completed_workouts >= 0",
            name="ck_strength_metric_rollups_completed_workouts_non_negative",
        ),
        CheckConstraint(
            "training_minutes >= 0",
            name="ck_strength_metric_rollups_training_minutes_non_negative",
        ),
        CheckConstraint(
            "completed_workouts <= total_workouts",
            name="ck_strength_metric_rollups_completed_le_total",
        ),
        CheckConstraint(
            "volume_score IS NULL OR volume_score >= 0",
            name="ck_strength_metric_rollups_volume_score_non_negative",
        ),
        CheckConstraint(
            "source_window_end >= source_window_start",
            name="ck_strength_metric_rollups_source_window_ordered",
        ),
        CheckConstraint("version >= 1", name="ck_strength_metric_rollups_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_start_day: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    business_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/New_York", server_default="America/New_York"
    )
    total_workouts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    completed_workouts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    training_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    volume_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")


class ClientMetricSnapshot(Base):
    __tablename__ = "client_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("client_user_id", name="uq_client_metric_snapshots_client_user_id"),
        CheckConstraint(
            "business_timezone = 'America/New_York'",
            name="ck_client_metric_snapshots_business_timezone",
        ),
        CheckConstraint(
            "week_start_day = 1",
            name="ck_client_metric_snapshots_week_start_day_monday",
        ),
        CheckConstraint(
            "current_intake_ceiling_calories IS NULL OR current_intake_ceiling_calories >= 0",
            name="ck_client_metric_snapshots_intake_ceiling_non_negative",
        ),
        CheckConstraint(
            "current_expenditure_floor_calories IS NULL OR current_expenditure_floor_calories >= 0",
            name="ck_client_metric_snapshots_expenditure_floor_non_negative",
        ),
        CheckConstraint(
            "current_target_deficit_calories IS NULL OR current_target_deficit_calories >= 0",
            name="ck_client_metric_snapshots_target_deficit_non_negative",
        ),
        CheckConstraint(
            "current_week_intake_calories IS NULL OR current_week_intake_calories >= 0",
            name="ck_client_metric_snapshots_week_intake_non_negative",
        ),
        CheckConstraint(
            "current_week_expenditure_calories IS NULL OR current_week_expenditure_calories >= 0",
            name="ck_client_metric_snapshots_week_expenditure_non_negative",
        ),
        CheckConstraint(
            "current_deficit_progress_percent IS NULL OR "
            "(current_deficit_progress_percent >= 0 AND current_deficit_progress_percent <= 100)",
            name="ck_client_metric_snapshots_deficit_progress_bounds",
        ),
        CheckConstraint(
            "source_window_end >= source_window_start",
            name="ck_client_metric_snapshots_source_window_ordered",
        ),
        CheckConstraint("version >= 1", name="ck_client_metric_snapshots_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    business_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/New_York", server_default="America/New_York"
    )
    week_start_day: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    latest_week_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_intake_ceiling_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_expenditure_floor_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_target_deficit_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_week_intake_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_week_expenditure_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_week_net_balance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_deficit_progress_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    snapshot_generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rollup_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    client_user: Mapped["User"] = relationship("User")
