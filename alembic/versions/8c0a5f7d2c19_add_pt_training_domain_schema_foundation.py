"""add pt training domain schema foundation

Revision ID: 8c0a5f7d2c19
Revises: 0f2d3a91c6b4
Create Date: 2026-03-16 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c0a5f7d2c19"
down_revision: str | Sequence[str] | None = "0f2d3a91c6b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


pt_client_link_status_enum = sa.Enum(
    "pending",
    "active",
    "paused",
    "ended",
    name="pt_client_link_status",
    native_enum=False,
    create_constraint=True,
)

training_package_status_enum = sa.Enum(
    "draft",
    "active",
    "archived",
    name="training_package_status",
    native_enum=False,
    create_constraint=True,
)

assignment_status_enum = sa.Enum(
    "assigned",
    "active",
    "completed",
    "cancelled",
    name="assignment_status",
    native_enum=False,
    create_constraint=True,
)

workout_completion_status_enum = sa.Enum(
    "completed",
    "partial",
    "skipped",
    name="workout_completion_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pt_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("certifications_text", sa.Text(), nullable=True),
        sa.Column("specialties_text", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_pt_profiles_user_id"),
    )
    op.create_index(op.f("ix_pt_profiles_user_id"), "pt_profiles", ["user_id"], unique=False)

    op.create_table(
        "pt_client_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("status", pt_client_link_status_enum, server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("pt_user_id <> client_user_id", name="ck_pt_client_links_no_self_link"),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pt_user_id",
            "client_user_id",
            name="uq_pt_client_links_pt_user_id_client_user_id",
        ),
    )
    op.create_index(op.f("ix_pt_client_links_pt_user_id"), "pt_client_links", ["pt_user_id"], unique=False)
    op.create_index(
        op.f("ix_pt_client_links_client_user_id"),
        "pt_client_links",
        ["client_user_id"],
        unique=False,
    )

    op.create_table(
        "pt_folders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pt_folders_pt_user_id"), "pt_folders", ["pt_user_id"], unique=False)

    op.create_table(
        "routines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("folder_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.String(length=64), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(["folder_id"], ["pt_folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_routines_pt_user_id"), "routines", ["pt_user_id"], unique=False)
    op.create_index(op.f("ix_routines_folder_id"), "routines", ["folder_id"], unique=False)

    op.create_table(
        "training_packages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("folder_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", training_package_status_enum, server_default="draft", nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("is_template", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(["folder_id"], ["pt_folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_training_packages_pt_user_id"),
        "training_packages",
        ["pt_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_training_packages_folder_id"),
        "training_packages",
        ["folder_id"],
        unique=False,
    )

    op.create_table(
        "training_package_routines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("training_package_id", sa.UUID(), nullable=False),
        sa.Column("routine_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("day_label", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["training_package_id"],
            ["training_packages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "training_package_id",
            "routine_id",
            name="uq_training_package_routines_training_package_id_routine_id",
        ),
        sa.UniqueConstraint(
            "training_package_id",
            "position",
            name="uq_training_package_routines_training_package_id_position",
        ),
    )
    op.create_index(
        op.f("ix_training_package_routines_training_package_id"),
        "training_package_routines",
        ["training_package_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_training_package_routines_routine_id"),
        "training_package_routines",
        ["routine_id"],
        unique=False,
    )

    op.create_table(
        "checklist_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("training_package_id", sa.UUID(), nullable=True),
        sa.Column("routine_id", sa.UUID(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "((training_package_id IS NOT NULL AND routine_id IS NULL) OR "
            "(training_package_id IS NULL AND routine_id IS NOT NULL))",
            name="ck_checklist_items_exactly_one_owner",
        ),
        sa.ForeignKeyConstraint(
            ["training_package_id"],
            ["training_packages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_checklist_items_training_package_id"),
        "checklist_items",
        ["training_package_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checklist_items_routine_id"),
        "checklist_items",
        ["routine_id"],
        unique=False,
    )

    op.create_table(
        "client_training_package_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("training_package_id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("pt_client_link_id", sa.UUID(), nullable=False),
        sa.Column("status", assignment_status_enum, server_default="assigned", nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["pt_client_link_id"],
            ["pt_client_links.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["training_package_id"],
            ["training_packages.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_client_training_package_assignments_training_package_id"),
        "client_training_package_assignments",
        ["training_package_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_training_package_assignments_pt_user_id"),
        "client_training_package_assignments",
        ["pt_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_training_package_assignments_client_user_id"),
        "client_training_package_assignments",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_training_package_assignments_pt_client_link_id"),
        "client_training_package_assignments",
        ["pt_client_link_id"],
        unique=False,
    )

    op.create_table(
        "workout_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=True),
        sa.Column("routine_id", sa.UUID(), nullable=True),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "completion_status",
            workout_completion_status_enum,
            server_default="completed",
            nullable=False,
        ),
        sa.Column("client_notes", sa.Text(), nullable=True),
        sa.Column("pt_notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["client_training_package_assignments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workout_logs_client_user_id"),
        "workout_logs",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_workout_logs_pt_user_id"), "workout_logs", ["pt_user_id"], unique=False)
    op.create_index(
        op.f("ix_workout_logs_assignment_id"),
        "workout_logs",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(op.f("ix_workout_logs_routine_id"), "workout_logs", ["routine_id"], unique=False)
    op.create_index(op.f("ix_workout_logs_performed_at"), "workout_logs", ["performed_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_workout_logs_performed_at"), table_name="workout_logs")
    op.drop_index(op.f("ix_workout_logs_routine_id"), table_name="workout_logs")
    op.drop_index(op.f("ix_workout_logs_assignment_id"), table_name="workout_logs")
    op.drop_index(op.f("ix_workout_logs_pt_user_id"), table_name="workout_logs")
    op.drop_index(op.f("ix_workout_logs_client_user_id"), table_name="workout_logs")
    op.drop_table("workout_logs")

    op.drop_index(
        op.f("ix_client_training_package_assignments_pt_client_link_id"),
        table_name="client_training_package_assignments",
    )
    op.drop_index(
        op.f("ix_client_training_package_assignments_client_user_id"),
        table_name="client_training_package_assignments",
    )
    op.drop_index(
        op.f("ix_client_training_package_assignments_pt_user_id"),
        table_name="client_training_package_assignments",
    )
    op.drop_index(
        op.f("ix_client_training_package_assignments_training_package_id"),
        table_name="client_training_package_assignments",
    )
    op.drop_table("client_training_package_assignments")

    op.drop_index(op.f("ix_checklist_items_routine_id"), table_name="checklist_items")
    op.drop_index(op.f("ix_checklist_items_training_package_id"), table_name="checklist_items")
    op.drop_table("checklist_items")

    op.drop_index(
        op.f("ix_training_package_routines_routine_id"),
        table_name="training_package_routines",
    )
    op.drop_index(
        op.f("ix_training_package_routines_training_package_id"),
        table_name="training_package_routines",
    )
    op.drop_table("training_package_routines")

    op.drop_index(op.f("ix_training_packages_folder_id"), table_name="training_packages")
    op.drop_index(op.f("ix_training_packages_pt_user_id"), table_name="training_packages")
    op.drop_table("training_packages")

    op.drop_index(op.f("ix_routines_folder_id"), table_name="routines")
    op.drop_index(op.f("ix_routines_pt_user_id"), table_name="routines")
    op.drop_table("routines")

    op.drop_index(op.f("ix_pt_folders_pt_user_id"), table_name="pt_folders")
    op.drop_table("pt_folders")

    op.drop_index(op.f("ix_pt_client_links_client_user_id"), table_name="pt_client_links")
    op.drop_index(op.f("ix_pt_client_links_pt_user_id"), table_name="pt_client_links")
    op.drop_table("pt_client_links")

    op.drop_index(op.f("ix_pt_profiles_user_id"), table_name="pt_profiles")
    op.drop_table("pt_profiles")
