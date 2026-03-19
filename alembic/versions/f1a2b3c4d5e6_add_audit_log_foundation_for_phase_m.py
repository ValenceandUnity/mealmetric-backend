"""add audit log foundation for phase m

Revision ID: f1a2b3c4d5e6
Revises: c7e9a21b4d5f
Create Date: 2026-03-17 08:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "c7e9a21b4d5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

audit_event_category_enum = sa.Enum(
    "training",
    "metrics",
    "recommendation",
    name="audit_event_category",
    native_enum=False,
    create_constraint=True,
)

audit_event_action_enum = sa.Enum(
    "pt_client_assignment_created",
    "pt_client_assignment_status_updated",
    "metrics_weekly_rollup_upserted",
    "metrics_strength_rollup_upserted",
    "metrics_client_snapshot_upserted",
    "meal_plan_recommendation_created",
    name="audit_event_action",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("category", audit_event_category_enum, nullable=False),
        sa.Column("action", audit_event_action_enum, nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("target_entity_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity_id", sa.String(length=255), nullable=False),
        sa.Column("related_entity_type", sa.String(length=64), nullable=True),
        sa.Column("related_entity_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_category"), "audit_logs", ["category"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_related_entity_id"), "audit_logs", ["related_entity_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_related_entity_type"), "audit_logs", ["related_entity_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_request_id"), "audit_logs", ["request_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_target_entity_id"), "audit_logs", ["target_entity_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_target_entity_type"), "audit_logs", ["target_entity_type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_audit_logs_target_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_target_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_request_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_related_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_related_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_category"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")
