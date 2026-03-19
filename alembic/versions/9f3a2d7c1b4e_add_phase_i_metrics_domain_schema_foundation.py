"""add phase i metrics domain schema foundation

Revision ID: 9f3a2d7c1b4e
Revises: d2f9c7a4b1e3
Create Date: 2026-03-16 23:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f3a2d7c1b4e"
down_revision: str | Sequence[str] | None = "d2f9c7a4b1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

metric_record_source_enum = sa.Enum(
    "manual",
    "bff_import",
    "device",
    "backfill",
    name="metric_record_source",
    native_enum=False,
    create_constraint=True,
)

deficit_target_status_enum = sa.Enum(
    "active",
    "inactive",
    name="deficit_target_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "calorie_intake_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("calories", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            metric_record_source_enum,
            server_default="manual",
            nullable=False,
        ),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("ingestion_key", sa.String(length=128), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("calories >= 0", name="ck_calorie_intake_records_calories_non_negative"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_user_id",
            "ingestion_key",
            name="uq_calorie_intake_records_client_user_id_ingestion_key",
        ),
    )
    op.create_index(
        op.f("ix_calorie_intake_records_client_user_id"),
        "calorie_intake_records",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_calorie_intake_records_recorded_at"),
        "calorie_intake_records",
        ["recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_calorie_intake_records_business_date"),
        "calorie_intake_records",
        ["business_date"],
        unique=False,
    )

    op.create_table(
        "activity_expenditure_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("expenditure_calories", sa.Integer(), nullable=False),
        sa.Column("activity_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            metric_record_source_enum,
            server_default="manual",
            nullable=False,
        ),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("ingestion_key", sa.String(length=128), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expenditure_calories >= 0",
            name="ck_activity_exp_records_expend_cal_nonneg",
        ),
        sa.CheckConstraint(
            "activity_minutes IS NULL OR activity_minutes >= 0",
            name="ck_activity_expenditure_records_activity_minutes_non_negative",
        ),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_user_id",
            "ingestion_key",
            name="uq_activity_expenditure_records_client_user_id_ingestion_key",
        ),
    )
    op.create_index(
        op.f("ix_activity_expenditure_records_client_user_id"),
        "activity_expenditure_records",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_expenditure_records_recorded_at"),
        "activity_expenditure_records",
        ["recorded_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_expenditure_records_business_date"),
        "activity_expenditure_records",
        ["business_date"],
        unique=False,
    )

    op.create_table(
        "deficit_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("target_daily_deficit_calories", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            deficit_target_status_enum,
            server_default="active",
            nullable=False,
        ),
        sa.Column("effective_from_date", sa.Date(), nullable=False),
        sa.Column("effective_to_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_daily_deficit_calories >= 0",
            name="ck_deficit_targets_target_daily_deficit_non_negative",
        ),
        sa.CheckConstraint(
            "effective_to_date IS NULL OR effective_to_date >= effective_from_date",
            name="ck_deficit_targets_effective_window_ordered",
        ),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_user_id",
            "effective_from_date",
            name="uq_deficit_targets_client_user_id_effective_from_date",
        ),
    )
    op.create_index(
        op.f("ix_deficit_targets_client_user_id"),
        "deficit_targets",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deficit_targets_status"),
        "deficit_targets",
        ["status"],
        unique=False,
    )

    op.create_table(
        "weekly_metric_rollups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_start_day", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "business_timezone",
            sa.String(length=64),
            server_default="America/New_York",
            nullable=False,
        ),
        sa.Column("total_intake_calories", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_expenditure_calories", sa.Integer(), server_default="0", nullable=False),
        sa.Column("net_calorie_balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("target_deficit_calories", sa.Integer(), nullable=True),
        sa.Column("deficit_progress_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("source_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "week_start_day = 1",
            name="ck_weekly_metric_rollups_week_start_day_monday",
        ),
        sa.CheckConstraint(
            "business_timezone = 'America/New_York'",
            name="ck_weekly_metric_rollups_business_timezone",
        ),
        sa.CheckConstraint(
            "total_intake_calories >= 0",
            name="ck_weekly_metric_rollups_total_intake_non_negative",
        ),
        sa.CheckConstraint(
            "total_expenditure_calories >= 0",
            name="ck_weekly_metric_rollups_total_expenditure_non_negative",
        ),
        sa.CheckConstraint(
            "target_deficit_calories IS NULL OR target_deficit_calories >= 0",
            name="ck_weekly_metric_rollups_target_deficit_non_negative",
        ),
        sa.CheckConstraint(
            "deficit_progress_percent IS NULL OR "
            "(deficit_progress_percent >= 0 AND deficit_progress_percent <= 100)",
            name="ck_weekly_metric_rollups_deficit_progress_bounds",
        ),
        sa.CheckConstraint(
            "source_window_end >= source_window_start",
            name="ck_weekly_metric_rollups_source_window_ordered",
        ),
        sa.CheckConstraint("version >= 1", name="ck_weekly_metric_rollups_version_positive"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_user_id",
            "week_start_date",
            name="uq_weekly_metric_rollups_client_user_id_week_start_date",
        ),
    )
    op.create_index(
        op.f("ix_weekly_metric_rollups_client_user_id"),
        "weekly_metric_rollups",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_weekly_metric_rollups_week_start_date"),
        "weekly_metric_rollups",
        ["week_start_date"],
        unique=False,
    )

    op.create_table(
        "strength_metric_rollups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_start_day", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "business_timezone",
            sa.String(length=64),
            server_default="America/New_York",
            nullable=False,
        ),
        sa.Column("total_workouts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_workouts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("training_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("volume_score", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("source_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "week_start_day = 1",
            name="ck_strength_metric_rollups_week_start_day_monday",
        ),
        sa.CheckConstraint(
            "business_timezone = 'America/New_York'",
            name="ck_strength_metric_rollups_business_timezone",
        ),
        sa.CheckConstraint(
            "total_workouts >= 0",
            name="ck_strength_metric_rollups_total_workouts_non_negative",
        ),
        sa.CheckConstraint(
            "completed_workouts >= 0",
            name="ck_strength_metric_rollups_completed_workouts_non_negative",
        ),
        sa.CheckConstraint(
            "training_minutes >= 0",
            name="ck_strength_metric_rollups_training_minutes_non_negative",
        ),
        sa.CheckConstraint(
            "completed_workouts <= total_workouts",
            name="ck_strength_metric_rollups_completed_le_total",
        ),
        sa.CheckConstraint(
            "volume_score IS NULL OR volume_score >= 0",
            name="ck_strength_metric_rollups_volume_score_non_negative",
        ),
        sa.CheckConstraint(
            "source_window_end >= source_window_start",
            name="ck_strength_metric_rollups_source_window_ordered",
        ),
        sa.CheckConstraint("version >= 1", name="ck_strength_metric_rollups_version_positive"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_user_id",
            "week_start_date",
            name="uq_strength_metric_rollups_client_user_id_week_start_date",
        ),
    )
    op.create_index(
        op.f("ix_strength_metric_rollups_client_user_id"),
        "strength_metric_rollups",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_strength_metric_rollups_week_start_date"),
        "strength_metric_rollups",
        ["week_start_date"],
        unique=False,
    )

    op.create_table(
        "client_metric_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "business_timezone",
            sa.String(length=64),
            server_default="America/New_York",
            nullable=False,
        ),
        sa.Column("week_start_day", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("latest_week_start_date", sa.Date(), nullable=True),
        sa.Column("current_intake_ceiling_calories", sa.Integer(), nullable=True),
        sa.Column("current_expenditure_floor_calories", sa.Integer(), nullable=True),
        sa.Column("current_target_deficit_calories", sa.Integer(), nullable=True),
        sa.Column("current_week_intake_calories", sa.Integer(), nullable=True),
        sa.Column("current_week_expenditure_calories", sa.Integer(), nullable=True),
        sa.Column("current_week_net_balance", sa.Integer(), nullable=True),
        sa.Column("current_deficit_progress_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "snapshot_generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("source_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rollup_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "business_timezone = 'America/New_York'",
            name="ck_client_metric_snapshots_business_timezone",
        ),
        sa.CheckConstraint(
            "week_start_day = 1",
            name="ck_client_metric_snapshots_week_start_day_monday",
        ),
        sa.CheckConstraint(
            "current_intake_ceiling_calories IS NULL OR current_intake_ceiling_calories >= 0",
            name="ck_client_metric_snapshots_intake_ceiling_non_negative",
        ),
        sa.CheckConstraint(
            "current_expenditure_floor_calories IS NULL OR "
            "current_expenditure_floor_calories >= 0",
            name="ck_client_metric_snapshots_expenditure_floor_non_negative",
        ),
        sa.CheckConstraint(
            "current_target_deficit_calories IS NULL OR current_target_deficit_calories >= 0",
            name="ck_client_metric_snapshots_target_deficit_non_negative",
        ),
        sa.CheckConstraint(
            "current_week_intake_calories IS NULL OR current_week_intake_calories >= 0",
            name="ck_client_metric_snapshots_week_intake_non_negative",
        ),
        sa.CheckConstraint(
            "current_week_expenditure_calories IS NULL OR current_week_expenditure_calories >= 0",
            name="ck_client_metric_snapshots_week_expenditure_non_negative",
        ),
        sa.CheckConstraint(
            "current_deficit_progress_percent IS NULL OR "
            "(current_deficit_progress_percent >= 0 AND current_deficit_progress_percent <= 100)",
            name="ck_client_metric_snapshots_deficit_progress_bounds",
        ),
        sa.CheckConstraint(
            "source_window_end >= source_window_start",
            name="ck_client_metric_snapshots_source_window_ordered",
        ),
        sa.CheckConstraint("version >= 1", name="ck_client_metric_snapshots_version_positive"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_user_id", name="uq_client_metric_snapshots_client_user_id"),
    )
    op.create_index(
        op.f("ix_client_metric_snapshots_client_user_id"),
        "client_metric_snapshots",
        ["client_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_client_metric_snapshots_client_user_id"), table_name="client_metric_snapshots"
    )
    op.drop_table("client_metric_snapshots")

    op.drop_index(
        op.f("ix_strength_metric_rollups_week_start_date"), table_name="strength_metric_rollups"
    )
    op.drop_index(
        op.f("ix_strength_metric_rollups_client_user_id"), table_name="strength_metric_rollups"
    )
    op.drop_table("strength_metric_rollups")

    op.drop_index(
        op.f("ix_weekly_metric_rollups_week_start_date"), table_name="weekly_metric_rollups"
    )
    op.drop_index(
        op.f("ix_weekly_metric_rollups_client_user_id"), table_name="weekly_metric_rollups"
    )
    op.drop_table("weekly_metric_rollups")

    op.drop_index(op.f("ix_deficit_targets_status"), table_name="deficit_targets")
    op.drop_index(op.f("ix_deficit_targets_client_user_id"), table_name="deficit_targets")
    op.drop_table("deficit_targets")

    op.drop_index(
        op.f("ix_activity_expenditure_records_business_date"),
        table_name="activity_expenditure_records",
    )
    op.drop_index(
        op.f("ix_activity_expenditure_records_recorded_at"),
        table_name="activity_expenditure_records",
    )
    op.drop_index(
        op.f("ix_activity_expenditure_records_client_user_id"),
        table_name="activity_expenditure_records",
    )
    op.drop_table("activity_expenditure_records")

    op.drop_index(
        op.f("ix_calorie_intake_records_business_date"), table_name="calorie_intake_records"
    )
    op.drop_index(
        op.f("ix_calorie_intake_records_recorded_at"), table_name="calorie_intake_records"
    )
    op.drop_index(
        op.f("ix_calorie_intake_records_client_user_id"), table_name="calorie_intake_records"
    )
    op.drop_table("calorie_intake_records")
