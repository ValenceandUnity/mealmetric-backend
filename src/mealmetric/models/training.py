import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
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


class PtClientLinkStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class TrainingPackageStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkoutCompletionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class PtProfile(Base):
    __tablename__ = "pt_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    certifications_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialties_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User")


class PtClientLink(Base):
    __tablename__ = "pt_client_links"
    __table_args__ = (
        UniqueConstraint(
            "pt_user_id",
            "client_user_id",
            name="uq_pt_client_links_pt_user_id_client_user_id",
        ),
        UniqueConstraint(
            "id",
            "pt_user_id",
            "client_user_id",
            name="uq_pt_client_links_id_pt_user_id_client_user_id",
        ),
        CheckConstraint("pt_user_id <> client_user_id", name="ck_pt_client_links_no_self_link"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[PtClientLinkStatus] = mapped_column(
        Enum(
            PtClientLinkStatus,
            name="pt_client_link_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=PtClientLinkStatus.PENDING,
        server_default=PtClientLinkStatus.PENDING.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    assignments: Mapped[list["ClientTrainingPackageAssignment"]] = relationship(
        "ClientTrainingPackageAssignment",
        back_populates="pt_client_link",
    )


class PtFolder(Base):
    __tablename__ = "pt_folders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    routines: Mapped[list["Routine"]] = relationship("Routine", back_populates="folder")
    training_packages: Mapped[list["TrainingPackage"]] = relationship(
        "TrainingPackage", back_populates="folder"
    )


class Routine(Base):
    __tablename__ = "routines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pt_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    folder: Mapped["PtFolder | None"] = relationship("PtFolder", back_populates="routines")
    package_links: Mapped[list["TrainingPackageRoutine"]] = relationship(
        "TrainingPackageRoutine",
        back_populates="routine",
        cascade="all, delete-orphan",
    )
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        "ChecklistItem",
        back_populates="routine",
        cascade="all, delete-orphan",
    )
    workout_logs: Mapped[list["WorkoutLog"]] = relationship("WorkoutLog", back_populates="routine")


class TrainingPackage(Base):
    __tablename__ = "training_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pt_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TrainingPackageStatus] = mapped_column(
        Enum(
            TrainingPackageStatus,
            name="training_package_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=TrainingPackageStatus.DRAFT,
        server_default=TrainingPackageStatus.DRAFT.value,
    )
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_template: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    folder: Mapped["PtFolder | None"] = relationship("PtFolder", back_populates="training_packages")
    routines: Mapped[list["TrainingPackageRoutine"]] = relationship(
        "TrainingPackageRoutine",
        back_populates="training_package",
        cascade="all, delete-orphan",
    )
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        "ChecklistItem",
        back_populates="training_package",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[list["ClientTrainingPackageAssignment"]] = relationship(
        "ClientTrainingPackageAssignment",
        back_populates="training_package",
    )


class TrainingPackageRoutine(Base):
    __tablename__ = "training_package_routines"
    __table_args__ = (
        UniqueConstraint(
            "training_package_id",
            "routine_id",
            name="uq_training_package_routines_training_package_id_routine_id",
        ),
        UniqueConstraint(
            "training_package_id",
            "position",
            name="uq_training_package_routines_training_package_id_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    training_package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    day_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    training_package: Mapped["TrainingPackage"] = relationship(
        "TrainingPackage", back_populates="routines"
    )
    routine: Mapped["Routine"] = relationship("Routine", back_populates="package_links")


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    __table_args__ = (
        CheckConstraint(
            "((training_package_id IS NOT NULL AND routine_id IS NULL) OR "
            "(training_package_id IS NULL AND routine_id IS NOT NULL))",
            name="ck_checklist_items_exactly_one_owner",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    training_package_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_packages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routines.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    training_package: Mapped["TrainingPackage | None"] = relationship(
        "TrainingPackage", back_populates="checklist_items"
    )
    routine: Mapped["Routine | None"] = relationship("Routine", back_populates="checklist_items")


class ClientTrainingPackageAssignment(Base):
    __tablename__ = "client_training_package_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pt_client_link_id", "pt_user_id", "client_user_id"],
            ["pt_client_links.id", "pt_client_links.pt_user_id", "pt_client_links.client_user_id"],
            ondelete="RESTRICT",
            name="fk_client_training_package_assignments_link_triplet",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    training_package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pt_client_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(
            AssignmentStatus,
            name="assignment_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=AssignmentStatus.ASSIGNED,
        server_default=AssignmentStatus.ASSIGNED.value,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    training_package: Mapped["TrainingPackage"] = relationship(
        "TrainingPackage", back_populates="assignments"
    )
    pt_client_link: Mapped["PtClientLink"] = relationship(
        "PtClientLink", back_populates="assignments"
    )
    workout_logs: Mapped[list["WorkoutLog"]] = relationship(
        "WorkoutLog", back_populates="assignment"
    )


class WorkoutLog(Base):
    __tablename__ = "workout_logs"
    __table_args__ = (
        CheckConstraint(
            "assignment_id IS NOT NULL OR routine_id IS NOT NULL",
            name="ck_workout_logs_assignment_or_routine_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pt_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_training_package_assignments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        index=True,
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_status: Mapped[WorkoutCompletionStatus] = mapped_column(
        Enum(
            WorkoutCompletionStatus,
            name="workout_completion_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=WorkoutCompletionStatus.COMPLETED,
        server_default=WorkoutCompletionStatus.COMPLETED.value,
    )
    client_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pt_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    assignment: Mapped["ClientTrainingPackageAssignment | None"] = relationship(
        "ClientTrainingPackageAssignment", back_populates="workout_logs"
    )
    routine: Mapped["Routine | None"] = relationship("Routine", back_populates="workout_logs")
