import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealmetric.db.base import Base

if TYPE_CHECKING:
    from mealmetric.models.role import Role as NormalizedRole
    from mealmetric.models.user_role import UserRole


class Role(StrEnum):
    CLIENT = "client"
    PT = "pt"
    VENDOR = "vendor"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", native_enum=False),
        nullable=False,
        default=Role.CLIENT,
        server_default=Role.CLIENT.value,
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="user")
    normalized_roles: Mapped[list["NormalizedRole"]] = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        viewonly=True,
    )
