"""add payment lifecycle tables

Revision ID: e5a3d01b1f9a
Revises: ddc99c5e5a6c
Create Date: 2026-03-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e5a3d01b1f9a"
down_revision: Union[str, Sequence[str], None] = "ddc99c5e5a6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


payment_status_enum = sa.Enum(
    "checkout_session_created",
    "checkout_session_completed",
    "payment_intent_succeeded",
    "payment_intent_failed",
    name="payment_status",
    native_enum=False,
)

webhook_processing_status_enum = sa.Enum(
    "received",
    "processing",
    "processed",
    "failed",
    "ignored",
    name="webhook_processing_status",
    native_enum=False,
)

payment_transition_source_enum = sa.Enum(
    "checkout_api",
    "stripe_webhook",
    "system",
    name="payment_transition_source",
    native_enum=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "payment_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column(
            "payment_status",
            payment_status_enum,
            server_default="checkout_session_created",
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stripe_checkout_session_id",
            name="uq_payment_sessions_stripe_checkout_session_id",
        ),
        sa.UniqueConstraint(
            "stripe_payment_intent_id",
            name="uq_payment_sessions_stripe_payment_intent_id",
        ),
    )
    op.create_index(op.f("ix_payment_sessions_user_id"), "payment_sessions", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_payment_sessions_payment_status"),
        "payment_sessions",
        ["payment_status"],
        unique=False,
    )

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column(
            "processing_status",
            webhook_processing_status_enum,
            server_default="received",
            nullable=False,
        ),
        sa.Column("payment_session_id", sa.UUID(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_session_id"], ["payment_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_webhook_events_stripe_event_id"),
    )
    op.create_index(
        op.f("ix_stripe_webhook_events_event_type"),
        "stripe_webhook_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stripe_webhook_events_processing_status"),
        "stripe_webhook_events",
        ["processing_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stripe_webhook_events_payment_session_id"),
        "stripe_webhook_events",
        ["payment_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stripe_webhook_events_request_id"),
        "stripe_webhook_events",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stripe_webhook_events_received_at"),
        "stripe_webhook_events",
        ["received_at"],
        unique=False,
    )

    op.create_table(
        "payment_audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_session_id", sa.UUID(), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=True),
        sa.Column("from_payment_status", payment_status_enum, nullable=True),
        sa.Column("to_payment_status", payment_status_enum, nullable=False),
        sa.Column(
            "transition_source",
            payment_transition_source_enum,
            server_default="system",
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_session_id"], ["payment_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_audit_log_payment_session_id"),
        "payment_audit_log",
        ["payment_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_audit_log_stripe_event_id"),
        "payment_audit_log",
        ["stripe_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_audit_log_from_payment_status"),
        "payment_audit_log",
        ["from_payment_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_audit_log_to_payment_status"),
        "payment_audit_log",
        ["to_payment_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_audit_log_transition_source"),
        "payment_audit_log",
        ["transition_source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_audit_log_created_at"),
        "payment_audit_log",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_payment_audit_log_created_at"), table_name="payment_audit_log")
    op.drop_index(op.f("ix_payment_audit_log_transition_source"), table_name="payment_audit_log")
    op.drop_index(op.f("ix_payment_audit_log_to_payment_status"), table_name="payment_audit_log")
    op.drop_index(op.f("ix_payment_audit_log_from_payment_status"), table_name="payment_audit_log")
    op.drop_index(op.f("ix_payment_audit_log_stripe_event_id"), table_name="payment_audit_log")
    op.drop_index(op.f("ix_payment_audit_log_payment_session_id"), table_name="payment_audit_log")
    op.drop_table("payment_audit_log")

    op.drop_index(op.f("ix_stripe_webhook_events_received_at"), table_name="stripe_webhook_events")
    op.drop_index(op.f("ix_stripe_webhook_events_request_id"), table_name="stripe_webhook_events")
    op.drop_index(op.f("ix_stripe_webhook_events_payment_session_id"), table_name="stripe_webhook_events")
    op.drop_index(op.f("ix_stripe_webhook_events_processing_status"), table_name="stripe_webhook_events")
    op.drop_index(op.f("ix_stripe_webhook_events_event_type"), table_name="stripe_webhook_events")
    op.drop_table("stripe_webhook_events")

    op.drop_index(op.f("ix_payment_sessions_payment_status"), table_name="payment_sessions")
    op.drop_index(op.f("ix_payment_sessions_user_id"), table_name="payment_sessions")
    op.drop_table("payment_sessions")
