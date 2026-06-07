"""add pt client invitations

Revision ID: b2c3d4e5f6a7
Revises: 9d4e5f6a7b8c
Create Date: 2026-06-06 20:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "9d4e5f6a7b8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

old_notification_type_enum = sa.Enum(
    "client_workout_logged",
    "pt_workout_note_added",
    "pt_assignment_created",
    name="notification_type",
    native_enum=False,
    create_constraint=True,
)

new_notification_type_enum = sa.Enum(
    "client_workout_logged",
    "pt_workout_note_added",
    "pt_assignment_created",
    "pt_client_invitation_received",
    "pt_client_invitation_accepted",
    "pt_client_invitation_declined",
    name="notification_type",
    native_enum=False,
    create_constraint=True,
)

pt_client_invitation_status_enum = sa.Enum(
    "pending",
    "accepted",
    "declined",
    "revoked",
    name="pt_client_invitation_status",
    native_enum=False,
    create_constraint=True,
)


def _validate_no_invitation_data_for_downgrade() -> None:
    bind = op.get_bind()
    invitation_count = bind.execute(sa.text("SELECT COUNT(1) FROM pt_client_invitations")).scalar_one()
    if invitation_count > 0:
        raise RuntimeError(
            "Cannot downgrade PT client invitations while invitation rows exist."
        )

    invite_notification_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(1)
            FROM notifications
            WHERE type IN (
              'pt_client_invitation_received',
              'pt_client_invitation_accepted',
              'pt_client_invitation_declined'
            )
            """
        )
    ).scalar_one()
    if invite_notification_count > 0:
        raise RuntimeError(
            "Cannot downgrade invite notification types while invite notifications exist."
        )


def upgrade() -> None:
    op.create_table(
        "pt_client_invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pt_user_id", sa.UUID(), nullable=False),
        sa.Column("client_user_id", sa.UUID(), nullable=False),
        sa.Column("client_email_snapshot", sa.String(length=255), nullable=True),
        sa.Column("status", pt_client_invitation_status_enum, server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "pt_user_id <> client_user_id",
            name="ck_pt_client_invitations_no_self_invite",
        ),
        sa.ForeignKeyConstraint(["client_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pt_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pt_client_invitations_pt_user_id"),
        "pt_client_invitations",
        ["pt_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_client_invitations_client_user_id"),
        "pt_client_invitations",
        ["client_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pt_client_invitations_status"),
        "pt_client_invitations",
        ["status"],
        unique=False,
    )

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=old_notification_type_enum,
            type_=new_notification_type_enum,
            existing_nullable=False,
        )


def downgrade() -> None:
    _validate_no_invitation_data_for_downgrade()

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=new_notification_type_enum,
            type_=old_notification_type_enum,
            existing_nullable=False,
        )

    op.drop_index(op.f("ix_pt_client_invitations_status"), table_name="pt_client_invitations")
    op.drop_index(op.f("ix_pt_client_invitations_client_user_id"), table_name="pt_client_invitations")
    op.drop_index(op.f("ix_pt_client_invitations_pt_user_id"), table_name="pt_client_invitations")
    op.drop_table("pt_client_invitations")
