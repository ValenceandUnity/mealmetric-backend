import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory
from mealmetric.models.training import (
    AssignmentStatus,
    ChecklistItem,
    ClientTrainingPackageAssignment,
    PtClientLink,
    PtClientLinkStatus,
    PtFolder,
    PtProfile,
    Routine,
    TrainingPackage,
    TrainingPackageRoutine,
    TrainingPackageStatus,
    WorkoutCompletionStatus,
    WorkoutLog,
)
from mealmetric.models.user import Role
from mealmetric.repos import audit_log_repo, training_repo, user_repo
from mealmetric.services.metrics_service import MetricsService, OverviewMetricsView

_AUDIT_LOGGER = logging.getLogger("mealmetric.training.audit")


class TrainingServiceError(Exception):
    """Base training-domain service error."""


class TrainingConflictError(TrainingServiceError):
    """Raised when a unique/conflict condition is hit."""


class TrainingNotFoundError(TrainingServiceError):
    """Raised when an expected training resource does not exist."""


class TrainingPermissionError(TrainingServiceError):
    """Raised when a PT tries to operate out of ownership scope."""


class TrainingValidationError(TrainingServiceError):
    """Raised when request data violates training domain rules."""


@dataclass(frozen=True, slots=True)
class PackageRoutineInput:
    routine_id: uuid.UUID
    position: int
    day_label: str | None = None


@dataclass(frozen=True, slots=True)
class ChecklistItemInput:
    label: str
    details: str | None = None
    position: int = 0
    is_required: bool = True


@dataclass(frozen=True, slots=True)
class PTClientProfileView:
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PTClientDetailView:
    client: PTClientProfileView
    current_assignments: tuple[ClientTrainingPackageAssignment, ...]
    metrics_snapshot: OverviewMetricsView


class PtProfileService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_user_id(self, user_id: uuid.UUID) -> PtProfile | None:
        return training_repo.get_pt_profile_by_user_id(self._session, user_id)

    def create_profile(
        self,
        *,
        user_id: uuid.UUID,
        display_name: str | None = None,
        bio: str | None = None,
        certifications_text: str | None = None,
        specialties_text: str | None = None,
        is_active: bool = True,
    ) -> PtProfile:
        existing = training_repo.get_pt_profile_by_user_id(self._session, user_id)
        if existing is not None:
            raise TrainingConflictError("pt_profile_already_exists")
        try:
            return training_repo.create_pt_profile(
                self._session,
                user_id=user_id,
                display_name=display_name,
                bio=bio,
                certifications_text=certifications_text,
                specialties_text=specialties_text,
                is_active=is_active,
            )
        except IntegrityError as exc:
            raise TrainingConflictError("pt_profile_already_exists") from exc

    def update_profile(
        self,
        *,
        user_id: uuid.UUID,
        display_name: str | None,
        bio: str | None,
        certifications_text: str | None,
        specialties_text: str | None,
        is_active: bool,
    ) -> PtProfile:
        profile = training_repo.get_pt_profile_by_user_id(self._session, user_id)
        if profile is None:
            raise TrainingNotFoundError("pt_profile_not_found")
        profile.display_name = display_name
        profile.bio = bio
        profile.certifications_text = certifications_text
        profile.specialties_text = specialties_text
        profile.is_active = is_active
        return training_repo.save_pt_profile(self._session, profile)


class PtClientLinkService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_link(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        status: PtClientLinkStatus = PtClientLinkStatus.PENDING,
        notes: str | None = None,
    ) -> PtClientLink:
        existing = training_repo.get_pt_client_link_by_pair(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        if existing is not None:
            raise TrainingConflictError("pt_client_link_already_exists")
        try:
            return training_repo.create_pt_client_link(
                self._session,
                pt_user_id=pt_user_id,
                client_user_id=client_user_id,
                status=status,
                notes=notes,
            )
        except IntegrityError as exc:
            raise TrainingConflictError("pt_client_link_already_exists") from exc

    def list_for_pt(self, pt_user_id: uuid.UUID) -> list[PtClientLink]:
        return training_repo.list_pt_client_links_for_pt(self._session, pt_user_id)

    def list_for_client(self, client_user_id: uuid.UUID) -> list[PtClientLink]:
        return training_repo.list_pt_client_links_for_client(self._session, client_user_id)

    def update_status(
        self,
        *,
        pt_user_id: uuid.UUID,
        link_id: uuid.UUID,
        status: PtClientLinkStatus,
    ) -> PtClientLink:
        link = training_repo.get_pt_client_link_for_pt(
            self._session,
            link_id=link_id,
            pt_user_id=pt_user_id,
        )
        if link is None:
            raise TrainingNotFoundError("pt_client_link_not_found")
        link.status = status
        return training_repo.save_pt_client_link(self._session, link)

    def get_client_detail(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        as_of_date: date | None = None,
    ) -> PTClientDetailView:
        link = training_repo.get_pt_client_link_by_pair(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        if link is None or link.status != PtClientLinkStatus.ACTIVE:
            raise TrainingPermissionError("pt_client_link_not_active")

        client_user = user_repo.get_by_id(self._session, client_user_id)
        if client_user is None:
            raise TrainingNotFoundError("client_not_found")
        if client_user.role != Role.CLIENT:
            raise TrainingValidationError("client_role_required")

        assignments = training_repo.list_assignments_for_pt_client(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        metrics_snapshot = MetricsService(self._session).get_pt_client_overview(
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
            as_of_date=as_of_date,
        )
        return PTClientDetailView(
            client=PTClientProfileView(
                id=client_user.id,
                email=client_user.email,
                role=client_user.role.value,
                created_at=client_user.created_at,
            ),
            current_assignments=tuple(assignments),
            metrics_snapshot=metrics_snapshot,
        )


class PtFolderService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_folder(
        self,
        *,
        pt_user_id: uuid.UUID,
        name: str,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PtFolder:
        return training_repo.create_pt_folder(
            self._session,
            pt_user_id=pt_user_id,
            name=name,
            description=description,
            sort_order=sort_order,
        )

    def list_folders(self, pt_user_id: uuid.UUID) -> list[PtFolder]:
        return training_repo.list_pt_folders_for_pt(self._session, pt_user_id)

    def update_folder(
        self,
        *,
        pt_user_id: uuid.UUID,
        folder_id: uuid.UUID,
        name: str,
        description: str | None,
        sort_order: int,
    ) -> PtFolder:
        folder = training_repo.get_pt_folder_for_pt(
            self._session,
            folder_id=folder_id,
            pt_user_id=pt_user_id,
        )
        if folder is None:
            raise TrainingNotFoundError("pt_folder_not_found")
        folder.name = name
        folder.description = description
        folder.sort_order = sort_order
        return training_repo.save_pt_folder(self._session, folder)

    def delete_folder(self, *, pt_user_id: uuid.UUID, folder_id: uuid.UUID) -> None:
        folder = training_repo.get_pt_folder_for_pt(
            self._session,
            folder_id=folder_id,
            pt_user_id=pt_user_id,
        )
        if folder is None:
            raise TrainingNotFoundError("pt_folder_not_found")
        training_repo.delete_pt_folder(self._session, folder)


class RoutineService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_routine(
        self,
        *,
        pt_user_id: uuid.UUID,
        title: str,
        folder_id: uuid.UUID | None = None,
        description: str | None = None,
        difficulty: str | None = None,
        estimated_minutes: int | None = None,
    ) -> Routine:
        if folder_id is not None:
            folder = training_repo.get_pt_folder_for_pt(
                self._session,
                folder_id=folder_id,
                pt_user_id=pt_user_id,
            )
            if folder is None:
                raise TrainingPermissionError("routine_folder_not_owned")
        return training_repo.create_routine(
            self._session,
            pt_user_id=pt_user_id,
            folder_id=folder_id,
            title=title,
            description=description,
            difficulty=difficulty,
            estimated_minutes=estimated_minutes,
        )

    def list_routines(self, pt_user_id: uuid.UUID) -> list[Routine]:
        return training_repo.list_routines_for_pt(self._session, pt_user_id)

    def get_routine(self, *, pt_user_id: uuid.UUID, routine_id: uuid.UUID) -> Routine:
        routine = training_repo.get_routine_for_pt(
            self._session,
            routine_id=routine_id,
            pt_user_id=pt_user_id,
        )
        if routine is None:
            raise TrainingNotFoundError("routine_not_found")
        return routine

    def update_routine(
        self,
        *,
        pt_user_id: uuid.UUID,
        routine_id: uuid.UUID,
        title: str,
        folder_id: uuid.UUID | None,
        description: str | None,
        difficulty: str | None,
        estimated_minutes: int | None,
    ) -> Routine:
        routine = self.get_routine(pt_user_id=pt_user_id, routine_id=routine_id)
        if folder_id is not None:
            folder = training_repo.get_pt_folder_for_pt(
                self._session,
                folder_id=folder_id,
                pt_user_id=pt_user_id,
            )
            if folder is None:
                raise TrainingPermissionError("routine_folder_not_owned")
        routine.title = title
        routine.folder_id = folder_id
        routine.description = description
        routine.difficulty = difficulty
        routine.estimated_minutes = estimated_minutes
        return training_repo.save_routine(self._session, routine)

    def archive_routine(self, *, pt_user_id: uuid.UUID, routine_id: uuid.UUID) -> Routine:
        routine = self.get_routine(pt_user_id=pt_user_id, routine_id=routine_id)
        routine.is_archived = True
        return training_repo.save_routine(self._session, routine)


class TrainingPackageService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_training_package(
        self,
        *,
        pt_user_id: uuid.UUID,
        title: str,
        folder_id: uuid.UUID | None = None,
        description: str | None = None,
        status: TrainingPackageStatus = TrainingPackageStatus.DRAFT,
        duration_days: int | None = None,
        is_template: bool = True,
    ) -> TrainingPackage:
        if folder_id is not None:
            folder = training_repo.get_pt_folder_for_pt(
                self._session,
                folder_id=folder_id,
                pt_user_id=pt_user_id,
            )
            if folder is None:
                raise TrainingPermissionError("training_package_folder_not_owned")
        return training_repo.create_training_package(
            self._session,
            pt_user_id=pt_user_id,
            folder_id=folder_id,
            title=title,
            description=description,
            status=status,
            duration_days=duration_days,
            is_template=is_template,
        )

    def list_training_packages(self, pt_user_id: uuid.UUID) -> list[TrainingPackage]:
        return training_repo.list_training_packages_for_pt(self._session, pt_user_id)

    def get_training_package(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
    ) -> TrainingPackage:
        training_package = training_repo.get_training_package_for_pt(
            self._session,
            training_package_id=training_package_id,
            pt_user_id=pt_user_id,
        )
        if training_package is None:
            raise TrainingNotFoundError("training_package_not_found")
        return training_package

    def update_training_package(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
        title: str,
        folder_id: uuid.UUID | None,
        description: str | None,
        status: TrainingPackageStatus,
        duration_days: int | None,
        is_template: bool,
    ) -> TrainingPackage:
        training_package = self.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )
        if folder_id is not None:
            folder = training_repo.get_pt_folder_for_pt(
                self._session,
                folder_id=folder_id,
                pt_user_id=pt_user_id,
            )
            if folder is None:
                raise TrainingPermissionError("training_package_folder_not_owned")
        training_package.title = title
        training_package.folder_id = folder_id
        training_package.description = description
        training_package.status = status
        training_package.duration_days = duration_days
        training_package.is_template = is_template
        return training_repo.save_training_package(self._session, training_package)

    def archive_training_package(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
    ) -> TrainingPackage:
        training_package = self.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )
        training_package.status = TrainingPackageStatus.ARCHIVED
        return training_repo.save_training_package(self._session, training_package)

    def replace_package_routines(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
        routines: Sequence[PackageRoutineInput],
    ) -> list[TrainingPackageRoutine]:
        training_package = self.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )

        routine_ids = [item.routine_id for item in routines]
        positions = [item.position for item in routines]
        if len(set(routine_ids)) != len(routine_ids):
            raise TrainingValidationError("duplicate_routine_ids")
        if len(set(positions)) != len(positions):
            raise TrainingValidationError("duplicate_positions")

        owned_routines = training_repo.list_routines_by_ids_for_pt(
            self._session,
            pt_user_id=pt_user_id,
            routine_ids=routine_ids,
        )
        owned_ids = {routine.id for routine in owned_routines}
        if any(routine_id not in owned_ids for routine_id in routine_ids):
            raise TrainingPermissionError("routine_not_owned_by_pt")

        training_repo.delete_training_package_routines(self._session, training_package.id)

        sorted_items = sorted(routines, key=lambda item: item.position)
        return training_repo.create_training_package_routines(
            self._session,
            training_package_id=training_package.id,
            routine_items=[
                (item.routine_id, item.position, item.day_label) for item in sorted_items
            ],
        )

    def list_package_routines(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
    ) -> list[TrainingPackageRoutine]:
        training_package = self.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )
        return training_repo.list_training_package_routines(self._session, training_package.id)


class ChecklistService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_package_checklist(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
        items: Sequence[ChecklistItemInput],
    ) -> list[ChecklistItem]:
        package_service = TrainingPackageService(self._session)
        training_package = package_service.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )
        training_repo.delete_checklist_items_for_package(self._session, training_package.id)
        normalized = [
            (item.label, item.details, item.position, item.is_required)
            for item in sorted(items, key=lambda item: item.position)
        ]
        return training_repo.create_checklist_items(
            self._session,
            owner_package_id=training_package.id,
            owner_routine_id=None,
            items=normalized,
        )

    def replace_routine_checklist(
        self,
        *,
        pt_user_id: uuid.UUID,
        routine_id: uuid.UUID,
        items: Sequence[ChecklistItemInput],
    ) -> list[ChecklistItem]:
        routine_service = RoutineService(self._session)
        routine = routine_service.get_routine(pt_user_id=pt_user_id, routine_id=routine_id)
        training_repo.delete_checklist_items_for_routine(self._session, routine.id)
        normalized = [
            (item.label, item.details, item.position, item.is_required)
            for item in sorted(items, key=lambda item: item.position)
        ]
        return training_repo.create_checklist_items(
            self._session,
            owner_package_id=None,
            owner_routine_id=routine.id,
            items=normalized,
        )

    def list_package_checklist(
        self,
        *,
        pt_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
    ) -> list[ChecklistItem]:
        package_service = TrainingPackageService(self._session)
        training_package = package_service.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )
        return training_repo.list_checklist_items_for_package(self._session, training_package.id)

    def list_routine_checklist(
        self,
        *,
        pt_user_id: uuid.UUID,
        routine_id: uuid.UUID,
    ) -> list[ChecklistItem]:
        routine_service = RoutineService(self._session)
        routine = routine_service.get_routine(pt_user_id=pt_user_id, routine_id=routine_id)
        return training_repo.list_checklist_items_for_routine(self._session, routine.id)


class AssignmentService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def assign_package_to_client(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        training_package_id: uuid.UUID,
        status: AssignmentStatus = AssignmentStatus.ASSIGNED,
        assigned_at: datetime | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> ClientTrainingPackageAssignment:
        package_service = TrainingPackageService(self._session)
        training_package = package_service.get_training_package(
            pt_user_id=pt_user_id,
            training_package_id=training_package_id,
        )
        pt_client_link = training_repo.get_pt_client_link_by_pair(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        if pt_client_link is None:
            raise TrainingValidationError("pt_client_link_required")

        assignment_timestamp = assigned_at or datetime.now(UTC)
        try:
            assignment = training_repo.create_client_training_package_assignment(
                self._session,
                training_package_id=training_package.id,
                pt_user_id=pt_user_id,
                client_user_id=client_user_id,
                pt_client_link_id=pt_client_link.id,
                status=status,
                assigned_at=assignment_timestamp,
                start_date=start_date,
                end_date=end_date,
            )
            _AUDIT_LOGGER.info(
                "assignment_created",
                extra={
                    "pt_user_id": str(pt_user_id),
                    "client_user_id": str(client_user_id),
                    "assignment_id": str(assignment.id),
                    "training_package_id": str(training_package.id),
                },
            )
            audit_log_repo.append_event(
                self._session,
                category=AuditEventCategory.TRAINING,
                action=AuditEventAction.PT_CLIENT_ASSIGNMENT_CREATED,
                actor_user_id=pt_user_id,
                actor_role=Role.PT,
                target_entity_type="client_training_package_assignment",
                target_entity_id=assignment.id,
                related_entity_type="training_package",
                related_entity_id=training_package.id,
                metadata={
                    "pt_user_id": pt_user_id,
                    "client_user_id": client_user_id,
                    "pt_client_link_id": pt_client_link.id,
                    "training_package_id": training_package.id,
                    "status": assignment.status,
                    "assigned_at": assignment.assigned_at,
                    "start_date": assignment.start_date,
                    "end_date": assignment.end_date,
                },
                message="PT assigned a training package to a client",
            )
            return assignment
        except IntegrityError as exc:
            raise TrainingValidationError("invalid_assignment_relationship") from exc

    def list_assignments_for_pt(
        self, pt_user_id: uuid.UUID
    ) -> list[ClientTrainingPackageAssignment]:
        return training_repo.list_assignments_for_pt(self._session, pt_user_id)

    def list_assignments_for_pt_client(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
    ) -> list[ClientTrainingPackageAssignment]:
        return training_repo.list_assignments_for_pt_client(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )

    def update_assignment_status(
        self,
        *,
        pt_user_id: uuid.UUID,
        assignment_id: uuid.UUID,
        status: AssignmentStatus,
    ) -> ClientTrainingPackageAssignment:
        assignment = training_repo.get_assignment_for_pt(
            self._session,
            assignment_id=assignment_id,
            pt_user_id=pt_user_id,
        )
        if assignment is None:
            raise TrainingNotFoundError("assignment_not_found")
        previous_status = assignment.status
        assignment.status = status
        saved = training_repo.save_assignment(self._session, assignment)
        audit_log_repo.append_event(
            self._session,
            category=AuditEventCategory.TRAINING,
            action=AuditEventAction.PT_CLIENT_ASSIGNMENT_STATUS_UPDATED,
            actor_user_id=pt_user_id,
            actor_role=Role.PT,
            target_entity_type="client_training_package_assignment",
            target_entity_id=saved.id,
            related_entity_type="training_package",
            related_entity_id=saved.training_package_id,
            metadata={
                "pt_user_id": pt_user_id,
                "client_user_id": saved.client_user_id,
                "training_package_id": saved.training_package_id,
                "from_status": previous_status,
                "to_status": saved.status,
            },
            message="PT updated assignment status",
        )
        return saved


class ClientTrainingService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_assignments_for_client(
        self,
        client_user_id: uuid.UUID,
    ) -> list[ClientTrainingPackageAssignment]:
        return training_repo.list_assignments_for_client(self._session, client_user_id)

    def get_assignment_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> ClientTrainingPackageAssignment:
        assignment = training_repo.get_assignment_for_client(
            self._session,
            assignment_id=assignment_id,
            client_user_id=client_user_id,
        )
        if assignment is None:
            raise TrainingNotFoundError("assignment_not_found")
        return assignment

    def list_assignment_checklist_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> list[ChecklistItem]:
        assignment = self.get_assignment_for_client(
            client_user_id=client_user_id,
            assignment_id=assignment_id,
        )
        return training_repo.list_checklist_items_for_package(
            self._session,
            assignment.training_package_id,
        )

    def list_assignment_routines_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> list[TrainingPackageRoutine]:
        assignment = self.get_assignment_for_client(
            client_user_id=client_user_id,
            assignment_id=assignment_id,
        )
        return training_repo.list_training_package_routines(
            self._session,
            assignment.training_package_id,
        )

    def list_workout_logs_for_client(self, client_user_id: uuid.UUID) -> list[WorkoutLog]:
        workout_log_service = WorkoutLogService(self._session)
        return workout_log_service.list_workout_logs_for_client(
            requester_user_id=client_user_id,
            client_user_id=client_user_id,
        )

    def create_workout_log_for_client(
        self,
        *,
        client_user_id: uuid.UUID,
        assignment_id: uuid.UUID | None = None,
        routine_id: uuid.UUID | None = None,
        performed_at: datetime | None = None,
        duration_minutes: int | None = None,
        completion_status: WorkoutCompletionStatus = WorkoutCompletionStatus.COMPLETED,
        client_notes: str | None = None,
    ) -> WorkoutLog:
        if assignment_id is None and routine_id is None:
            raise TrainingValidationError("workout_log_anchor_required")

        pt_user_id: uuid.UUID | None = None

        if assignment_id is not None:
            assignment = training_repo.get_assignment_for_client(
                self._session,
                assignment_id=assignment_id,
                client_user_id=client_user_id,
            )
            if assignment is None:
                raise TrainingNotFoundError("assignment_not_found")
            pt_user_id = assignment.pt_user_id

        if routine_id is not None:
            routine = training_repo.get_routine_by_id(self._session, routine_id)
            if routine is None:
                raise TrainingNotFoundError("routine_not_found")
            if routine.is_archived:
                raise TrainingValidationError("routine_archived")

            if pt_user_id is None:
                pt_user_id = routine.pt_user_id
            elif routine.pt_user_id != pt_user_id:
                raise TrainingValidationError("assignment_routine_pt_mismatch")
            if assignment_id is not None and assignment is not None:
                is_in_package = training_repo.package_contains_routine(
                    self._session,
                    training_package_id=assignment.training_package_id,
                    routine_id=routine.id,
                )
                if not is_in_package:
                    raise TrainingValidationError("routine_not_in_assignment_package")

            link = training_repo.get_pt_client_link_by_pair(
                self._session,
                pt_user_id=routine.pt_user_id,
                client_user_id=client_user_id,
            )
            if link is None:
                raise TrainingPermissionError("routine_not_assigned_to_client")

        if pt_user_id is None:
            raise TrainingValidationError("workout_log_anchor_required")

        workout_log_service = WorkoutLogService(self._session)
        workout_log = workout_log_service.create_workout_log(
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
            assignment_id=assignment_id,
            routine_id=routine_id,
            performed_at=performed_at,
            duration_minutes=duration_minutes,
            completion_status=completion_status,
            client_notes=client_notes,
            pt_notes=None,
        )
        _AUDIT_LOGGER.info(
            "client_workout_log_created",
            extra={
                "client_user_id": str(client_user_id),
                "pt_user_id": str(pt_user_id),
                "workout_log_id": str(workout_log.id),
                "assignment_id": (str(assignment_id) if assignment_id is not None else None),
                "routine_id": str(routine_id) if routine_id is not None else None,
            },
        )
        return workout_log


class WorkoutLogService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_workout_log(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        assignment_id: uuid.UUID | None = None,
        routine_id: uuid.UUID | None = None,
        performed_at: datetime | None = None,
        duration_minutes: int | None = None,
        completion_status: WorkoutCompletionStatus = WorkoutCompletionStatus.COMPLETED,
        client_notes: str | None = None,
        pt_notes: str | None = None,
    ) -> WorkoutLog:
        if assignment_id is None and routine_id is None:
            raise TrainingValidationError("workout_log_anchor_required")

        pt_client_link = training_repo.get_pt_client_link_by_pair(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        if pt_client_link is None:
            raise TrainingPermissionError("workout_log_link_not_found")

        if assignment_id is not None:
            assignment = training_repo.get_assignment_for_pt(
                self._session,
                assignment_id=assignment_id,
                pt_user_id=pt_user_id,
            )
            if assignment is None or assignment.client_user_id != client_user_id:
                raise TrainingPermissionError("assignment_not_owned_for_client")

        if routine_id is not None:
            routine = training_repo.get_routine_for_pt(
                self._session,
                routine_id=routine_id,
                pt_user_id=pt_user_id,
            )
            if routine is None:
                raise TrainingPermissionError("routine_not_owned")
            if routine.is_archived:
                raise TrainingValidationError("routine_archived")

        logged_at = performed_at or datetime.now(UTC)
        workout_log = training_repo.create_workout_log(
            self._session,
            client_user_id=client_user_id,
            pt_user_id=pt_user_id,
            assignment_id=assignment_id,
            routine_id=routine_id,
            performed_at=logged_at,
            duration_minutes=duration_minutes,
            completion_status=completion_status,
            client_notes=client_notes,
            pt_notes=pt_notes,
        )
        _AUDIT_LOGGER.info(
            "workout_log_created",
            extra={
                "client_user_id": str(client_user_id),
                "pt_user_id": str(pt_user_id),
                "workout_log_id": str(workout_log.id),
                "assignment_id": (str(assignment_id) if assignment_id is not None else None),
                "routine_id": str(routine_id) if routine_id is not None else None,
            },
        )
        return workout_log

    def list_workout_logs_for_client(
        self,
        *,
        requester_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
    ) -> list[WorkoutLog]:
        if requester_user_id == client_user_id:
            return training_repo.list_workout_logs_for_client(self._session, client_user_id)

        pt_client_link = training_repo.get_pt_client_link_by_pair(
            self._session,
            pt_user_id=requester_user_id,
            client_user_id=client_user_id,
        )
        if pt_client_link is None:
            raise TrainingPermissionError("workout_logs_not_in_scope")
        return training_repo.list_workout_logs_for_pt_client(
            self._session,
            pt_user_id=requester_user_id,
            client_user_id=client_user_id,
        )

    def list_workout_logs_for_pt(self, pt_user_id: uuid.UUID) -> list[WorkoutLog]:
        return training_repo.list_workout_logs_for_pt(self._session, pt_user_id)
