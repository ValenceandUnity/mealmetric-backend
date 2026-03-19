"""add pt meal plan recommendations

Revision ID: 4a7c9e1d2b3f
Revises: 1c2d4e6f8a9b
Create Date: 2026-03-16 21:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a7c9e1d2b3f"
down_revision: str | Sequence[str] | None = "1c2d4e6f8a9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

meal_plan_recommendation_status_enum = sa.Enum(
    "active",
    "withdrawn",
    name="meal_plan_recommendation_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pt_meal_plan_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("meal_plan_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            meal_plan_recommendation_status_enum,
            server_default="active",
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["meal_plan_id"], ["meal_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pt_meal_plan_recommendations_pt_user_id"),
        "pt_meal_plan_recommendations",
        ["pt_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_meal_plan_recommendations_client_user_id"),
        "pt_meal_plan_recommendations",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_meal_plan_recommendations_meal_plan_id"),
        "pt_meal_plan_recommendations",
        ["meal_plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_meal_plan_recommendations_status"),
        "pt_meal_plan_recommendations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_meal_plan_recommendations_recommended_at"),
        "pt_meal_plan_recommendations",
        ["recommended_at"],
        unique=False,
    )
    op.create_index(
        "ix_pt_meal_plan_recommendations_pt_client_order",
        "pt_meal_plan_recommendations",
        ["pt_user_id", "client_user_id", "recommended_at"],
        unique=False,
    )
    op.create_index(
        "ix_pt_meal_plan_recommendations_client_order",
        "pt_meal_plan_recommendations",
        ["client_user_id", "recommended_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_pt_meal_plan_recommendations_client_order",
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_index(
        "ix_pt_meal_plan_recommendations_pt_client_order",
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_index(
        op.f("ix_pt_meal_plan_recommendations_recommended_at"),
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_index(
        op.f("ix_pt_meal_plan_recommendations_status"),
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_index(
        op.f("ix_pt_meal_plan_recommendations_meal_plan_id"),
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_index(
        op.f("ix_pt_meal_plan_recommendations_client_user_id"),
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_index(
        op.f("ix_pt_meal_plan_recommendations_pt_user_id"),
        table_name="pt_meal_plan_recommendations",
    )
    op.drop_table("pt_meal_plan_recommendations")
