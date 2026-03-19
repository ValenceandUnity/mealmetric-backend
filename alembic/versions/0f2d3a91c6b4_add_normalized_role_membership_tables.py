"""add normalized role membership tables

Revision ID: 0f2d3a91c6b4
Revises: b91f4f3b2c8d
Create Date: 2026-03-15 23:40:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0f2d3a91c6b4"
down_revision: str | Sequence[str] | None = "b91f4f3b2c8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_ROLES: tuple[str, ...] = ("client", "pt", "vendor", "admin")
USERS_ROLE_CHECK_NAME = "ck_users_role_compatibility"


def _ensure_users_role_compatibility_constraint() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_checks = inspector.get_check_constraints("users")

    check_sql = "role IN ('client', 'pt', 'vendor', 'admin')"

    if bind.dialect.name == "postgresql":
        column_row = bind.execute(
            sa.text(
                """
                SELECT udt_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'users'
                  AND column_name = 'role'
                """
            )
        ).first()
        if column_row is not None:
            udt_name = str(column_row[0])
            if udt_name not in {"varchar", "text", "bpchar"}:
                op.execute(
                    sa.text(
                        f"""
                        DO $$
                        BEGIN
                            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = '{udt_name}')
                               AND NOT EXISTS (
                                   SELECT 1
                                   FROM pg_enum e
                                   JOIN pg_type t ON t.oid = e.enumtypid
                                   WHERE t.typname = '{udt_name}'
                                     AND e.enumlabel = 'pt'
                               )
                            THEN
                                EXECUTE 'ALTER TYPE "{udt_name}" ADD VALUE ''pt''';
                            END IF;
                        END
                        $$;
                        """
                    )
                )
                return

    stale_role_checks = [
        constraint["name"]
        for constraint in existing_checks
        if constraint.get("name")
        and "role" in str(constraint.get("sqltext", "")).lower()
        and " in " in str(constraint.get("sqltext", "")).lower()
        and constraint["name"] != USERS_ROLE_CHECK_NAME
    ]
    with op.batch_alter_table("users") as batch_op:
        for check_name in stale_role_checks:
            batch_op.drop_constraint(check_name, type_="check")
        if USERS_ROLE_CHECK_NAME not in {constraint.get("name") for constraint in existing_checks}:
            batch_op.create_check_constraint(USERS_ROLE_CHECK_NAME, check_sql)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=True)

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )
    op.create_index(op.f("ix_user_roles_user_id"), "user_roles", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_roles_role_id"), "user_roles", ["role_id"], unique=False)
    _ensure_users_role_compatibility_constraint()

    bind = op.get_bind()
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String(length=32)),
    )

    existing_role_names = set(bind.execute(sa.text("SELECT name FROM roles")).scalars())
    role_rows = [
        {"id": uuid.uuid4(), "name": role_name}
        for role_name in CANONICAL_ROLES
        if role_name not in existing_role_names
    ]
    if role_rows:
        op.bulk_insert(roles_table, role_rows)

    op.execute(
        sa.text(
            """
            INSERT INTO user_roles (user_id, role_id)
            SELECT users.id, roles.id
            FROM users
            INNER JOIN roles ON roles.name = users.role
            LEFT JOIN user_roles
                ON user_roles.user_id = users.id
               AND user_roles.role_id = roles.id
            WHERE user_roles.user_id IS NULL
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_checks = {
        constraint.get("name") for constraint in inspector.get_check_constraints("users")
    }
    if USERS_ROLE_CHECK_NAME in existing_checks:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_constraint(USERS_ROLE_CHECK_NAME, type_="check")
    op.drop_index(op.f("ix_user_roles_role_id"), table_name="user_roles")
    op.drop_index(op.f("ix_user_roles_user_id"), table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
