import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

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


def get_pt_profile_by_user_id(session: Session, user_id: uuid.UUID) -> PtProfile | None:
    stmt: Select[tuple[PtProfile]] = select(PtProfile).where(PtProfile.user_id == user_id)
    return session.scalar(stmt)


def create_pt_profile(
    session: Session,
    *,
    user_id: uuid.UUID,
    display_name: str | None,
    bio: str | None,
    certifications_text: str | None,
    specialties_text: str | None,
    is_active: bool,
) -> PtProfile:
    profile = PtProfile(
        user_id=user_id,
        display_name=display_name,
        bio=bio,
        certifications_text=certifications_text,
        specialties_text=specialties_text,
        is_active=is_active,
    )
    session.add(profile)
    session.flush()
    return profile


def save_pt_profile(session: Session, profile: PtProfile) -> PtProfile:
    session.add(profile)
    session.flush()
    return profile


def get_pt_client_link_by_id(session: Session, link_id: uuid.UUID) -> PtClientLink | None:
    stmt: Select[tuple[PtClientLink]] = select(PtClientLink).where(PtClientLink.id == link_id)
    return session.scalar(stmt)


def get_pt_client_link_for_pt(
    session: Session,
    *,
    link_id: uuid.UUID,
    pt_user_id: uuid.UUID,
) -> PtClientLink | None:
    stmt: Select[tuple[PtClientLink]] = select(PtClientLink).where(
        PtClientLink.id == link_id,
        PtClientLink.pt_user_id == pt_user_id,
    )
    return session.scalar(stmt)


def get_pt_client_link_by_pair(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> PtClientLink | None:
    stmt: Select[tuple[PtClientLink]] = select(PtClientLink).where(
        PtClientLink.pt_user_id == pt_user_id,
        PtClientLink.client_user_id == client_user_id,
    )
    return session.scalar(stmt)


def list_pt_client_links_for_pt(session: Session, pt_user_id: uuid.UUID) -> list[PtClientLink]:
    stmt: Select[tuple[PtClientLink]] = (
        select(PtClientLink)
        .where(PtClientLink.pt_user_id == pt_user_id)
        .order_by(PtClientLink.created_at.desc(), PtClientLink.id.desc())
    )
    return list(session.scalars(stmt))


def list_pt_client_links_for_client(
    session: Session, client_user_id: uuid.UUID
) -> list[PtClientLink]:
    stmt: Select[tuple[PtClientLink]] = (
        select(PtClientLink)
        .where(PtClientLink.client_user_id == client_user_id)
        .order_by(PtClientLink.created_at.desc(), PtClientLink.id.desc())
    )
    return list(session.scalars(stmt))


def create_pt_client_link(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
    status: PtClientLinkStatus,
    notes: str | None,
) -> PtClientLink:
    link = PtClientLink(
        pt_user_id=pt_user_id,
        client_user_id=client_user_id,
        status=status,
        notes=notes,
    )
    session.add(link)
    session.flush()
    return link


def save_pt_client_link(session: Session, link: PtClientLink) -> PtClientLink:
    session.add(link)
    session.flush()
    return link


def create_pt_folder(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    name: str,
    description: str | None,
    sort_order: int,
) -> PtFolder:
    folder = PtFolder(
        pt_user_id=pt_user_id,
        name=name,
        description=description,
        sort_order=sort_order,
    )
    session.add(folder)
    session.flush()
    return folder


def get_pt_folder_for_pt(
    session: Session,
    *,
    folder_id: uuid.UUID,
    pt_user_id: uuid.UUID,
) -> PtFolder | None:
    stmt: Select[tuple[PtFolder]] = select(PtFolder).where(
        PtFolder.id == folder_id,
        PtFolder.pt_user_id == pt_user_id,
    )
    return session.scalar(stmt)


def list_pt_folders_for_pt(session: Session, pt_user_id: uuid.UUID) -> list[PtFolder]:
    stmt: Select[tuple[PtFolder]] = (
        select(PtFolder)
        .where(PtFolder.pt_user_id == pt_user_id)
        .order_by(PtFolder.sort_order.asc(), PtFolder.created_at.asc())
    )
    return list(session.scalars(stmt))


def save_pt_folder(session: Session, folder: PtFolder) -> PtFolder:
    session.add(folder)
    session.flush()
    return folder


def delete_pt_folder(session: Session, folder: PtFolder) -> None:
    session.delete(folder)
    session.flush()


def create_routine(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    title: str,
    description: str | None,
    difficulty: str | None,
    estimated_minutes: int | None,
) -> Routine:
    routine = Routine(
        pt_user_id=pt_user_id,
        folder_id=folder_id,
        title=title,
        description=description,
        difficulty=difficulty,
        estimated_minutes=estimated_minutes,
    )
    session.add(routine)
    session.flush()
    return routine


def get_routine_for_pt(
    session: Session,
    *,
    routine_id: uuid.UUID,
    pt_user_id: uuid.UUID,
) -> Routine | None:
    stmt: Select[tuple[Routine]] = select(Routine).where(
        Routine.id == routine_id,
        Routine.pt_user_id == pt_user_id,
    )
    return session.scalar(stmt)


def get_routine_by_id(session: Session, routine_id: uuid.UUID) -> Routine | None:
    stmt: Select[tuple[Routine]] = select(Routine).where(Routine.id == routine_id)
    return session.scalar(stmt)


def list_routines_for_pt(session: Session, pt_user_id: uuid.UUID) -> list[Routine]:
    stmt: Select[tuple[Routine]] = (
        select(Routine)
        .where(Routine.pt_user_id == pt_user_id)
        .order_by(Routine.created_at.desc(), Routine.id.desc())
    )
    return list(session.scalars(stmt))


def list_routines_by_ids_for_pt(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    routine_ids: Sequence[uuid.UUID],
) -> list[Routine]:
    if not routine_ids:
        return []
    stmt: Select[tuple[Routine]] = select(Routine).where(
        Routine.pt_user_id == pt_user_id,
        Routine.id.in_(tuple(routine_ids)),
    )
    return list(session.scalars(stmt))


def save_routine(session: Session, routine: Routine) -> Routine:
    session.add(routine)
    session.flush()
    return routine


def create_training_package(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    title: str,
    description: str | None,
    status: TrainingPackageStatus,
    duration_days: int | None,
    is_template: bool,
) -> TrainingPackage:
    training_package = TrainingPackage(
        pt_user_id=pt_user_id,
        folder_id=folder_id,
        title=title,
        description=description,
        status=status,
        duration_days=duration_days,
        is_template=is_template,
    )
    session.add(training_package)
    session.flush()
    return training_package


def get_training_package_for_pt(
    session: Session,
    *,
    training_package_id: uuid.UUID,
    pt_user_id: uuid.UUID,
) -> TrainingPackage | None:
    stmt: Select[tuple[TrainingPackage]] = select(TrainingPackage).where(
        TrainingPackage.id == training_package_id,
        TrainingPackage.pt_user_id == pt_user_id,
    )
    return session.scalar(stmt)


def list_training_packages_for_pt(session: Session, pt_user_id: uuid.UUID) -> list[TrainingPackage]:
    stmt: Select[tuple[TrainingPackage]] = (
        select(TrainingPackage)
        .where(TrainingPackage.pt_user_id == pt_user_id)
        .order_by(TrainingPackage.created_at.desc(), TrainingPackage.id.desc())
    )
    return list(session.scalars(stmt))


def save_training_package(session: Session, training_package: TrainingPackage) -> TrainingPackage:
    session.add(training_package)
    session.flush()
    return training_package


def delete_training_package_routines(session: Session, training_package_id: uuid.UUID) -> None:
    session.execute(
        delete(TrainingPackageRoutine).where(
            TrainingPackageRoutine.training_package_id == training_package_id
        )
    )
    session.flush()


def create_training_package_routines(
    session: Session,
    *,
    training_package_id: uuid.UUID,
    routine_items: Sequence[tuple[uuid.UUID, int, str | None]],
) -> list[TrainingPackageRoutine]:
    links: list[TrainingPackageRoutine] = []
    for routine_id, position, day_label in routine_items:
        link = TrainingPackageRoutine(
            training_package_id=training_package_id,
            routine_id=routine_id,
            position=position,
            day_label=day_label,
        )
        session.add(link)
        links.append(link)
    session.flush()
    return links


def list_training_package_routines(
    session: Session,
    training_package_id: uuid.UUID,
) -> list[TrainingPackageRoutine]:
    stmt: Select[tuple[TrainingPackageRoutine]] = (
        select(TrainingPackageRoutine)
        .where(TrainingPackageRoutine.training_package_id == training_package_id)
        .order_by(TrainingPackageRoutine.position.asc(), TrainingPackageRoutine.created_at.asc())
    )
    return list(session.scalars(stmt))


def delete_checklist_items_for_package(session: Session, training_package_id: uuid.UUID) -> None:
    session.execute(
        delete(ChecklistItem).where(ChecklistItem.training_package_id == training_package_id)
    )
    session.flush()


def delete_checklist_items_for_routine(session: Session, routine_id: uuid.UUID) -> None:
    session.execute(delete(ChecklistItem).where(ChecklistItem.routine_id == routine_id))
    session.flush()


def create_checklist_items(
    session: Session,
    *,
    owner_package_id: uuid.UUID | None,
    owner_routine_id: uuid.UUID | None,
    items: Sequence[tuple[str, str | None, int, bool]],
) -> list[ChecklistItem]:
    created: list[ChecklistItem] = []
    for label, details, position, is_required in items:
        checklist_item = ChecklistItem(
            training_package_id=owner_package_id,
            routine_id=owner_routine_id,
            label=label,
            details=details,
            position=position,
            is_required=is_required,
        )
        session.add(checklist_item)
        created.append(checklist_item)
    session.flush()
    return created


def list_checklist_items_for_package(
    session: Session,
    training_package_id: uuid.UUID,
) -> list[ChecklistItem]:
    stmt: Select[tuple[ChecklistItem]] = (
        select(ChecklistItem)
        .where(ChecklistItem.training_package_id == training_package_id)
        .order_by(ChecklistItem.position.asc(), ChecklistItem.created_at.asc())
    )
    return list(session.scalars(stmt))


def list_checklist_items_for_routine(
    session: Session, routine_id: uuid.UUID
) -> list[ChecklistItem]:
    stmt: Select[tuple[ChecklistItem]] = (
        select(ChecklistItem)
        .where(ChecklistItem.routine_id == routine_id)
        .order_by(ChecklistItem.position.asc(), ChecklistItem.created_at.asc())
    )
    return list(session.scalars(stmt))


def create_client_training_package_assignment(
    session: Session,
    *,
    training_package_id: uuid.UUID,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
    pt_client_link_id: uuid.UUID,
    status: AssignmentStatus,
    assigned_at: datetime,
    start_date: date | None,
    end_date: date | None,
) -> ClientTrainingPackageAssignment:
    assignment = ClientTrainingPackageAssignment(
        training_package_id=training_package_id,
        pt_user_id=pt_user_id,
        client_user_id=client_user_id,
        pt_client_link_id=pt_client_link_id,
        status=status,
        assigned_at=assigned_at,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(assignment)
    session.flush()
    return assignment


def get_assignment_for_pt(
    session: Session,
    *,
    assignment_id: uuid.UUID,
    pt_user_id: uuid.UUID,
) -> ClientTrainingPackageAssignment | None:
    stmt: Select[tuple[ClientTrainingPackageAssignment]] = select(
        ClientTrainingPackageAssignment
    ).where(
        ClientTrainingPackageAssignment.id == assignment_id,
        ClientTrainingPackageAssignment.pt_user_id == pt_user_id,
    )
    return session.scalar(stmt)


def get_assignment_for_client(
    session: Session,
    *,
    assignment_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> ClientTrainingPackageAssignment | None:
    stmt: Select[tuple[ClientTrainingPackageAssignment]] = select(
        ClientTrainingPackageAssignment
    ).where(
        ClientTrainingPackageAssignment.id == assignment_id,
        ClientTrainingPackageAssignment.client_user_id == client_user_id,
    )
    return session.scalar(stmt)


def list_assignments_for_pt(
    session: Session, pt_user_id: uuid.UUID
) -> list[ClientTrainingPackageAssignment]:
    stmt: Select[tuple[ClientTrainingPackageAssignment]] = (
        select(ClientTrainingPackageAssignment)
        .where(ClientTrainingPackageAssignment.pt_user_id == pt_user_id)
        .order_by(
            ClientTrainingPackageAssignment.assigned_at.desc(),
            ClientTrainingPackageAssignment.created_at.desc(),
            ClientTrainingPackageAssignment.id.desc(),
        )
    )
    return list(session.scalars(stmt))


def list_assignments_for_client(
    session: Session, client_user_id: uuid.UUID
) -> list[ClientTrainingPackageAssignment]:
    stmt: Select[tuple[ClientTrainingPackageAssignment]] = (
        select(ClientTrainingPackageAssignment)
        .where(ClientTrainingPackageAssignment.client_user_id == client_user_id)
        .order_by(
            ClientTrainingPackageAssignment.assigned_at.desc(),
            ClientTrainingPackageAssignment.created_at.desc(),
            ClientTrainingPackageAssignment.id.desc(),
        )
    )
    return list(session.scalars(stmt))


def list_assignments_for_pt_client(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> list[ClientTrainingPackageAssignment]:
    stmt: Select[tuple[ClientTrainingPackageAssignment]] = (
        select(ClientTrainingPackageAssignment)
        .where(
            ClientTrainingPackageAssignment.pt_user_id == pt_user_id,
            ClientTrainingPackageAssignment.client_user_id == client_user_id,
        )
        .order_by(
            ClientTrainingPackageAssignment.assigned_at.desc(),
            ClientTrainingPackageAssignment.created_at.desc(),
            ClientTrainingPackageAssignment.id.desc(),
        )
    )
    return list(session.scalars(stmt))


def save_assignment(
    session: Session,
    assignment: ClientTrainingPackageAssignment,
) -> ClientTrainingPackageAssignment:
    session.add(assignment)
    session.flush()
    return assignment


def create_workout_log(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    pt_user_id: uuid.UUID,
    assignment_id: uuid.UUID | None,
    routine_id: uuid.UUID | None,
    performed_at: datetime,
    duration_minutes: int | None,
    completion_status: WorkoutCompletionStatus,
    client_notes: str | None,
    pt_notes: str | None,
) -> WorkoutLog:
    workout_log = WorkoutLog(
        client_user_id=client_user_id,
        pt_user_id=pt_user_id,
        assignment_id=assignment_id,
        routine_id=routine_id,
        performed_at=performed_at,
        duration_minutes=duration_minutes,
        completion_status=completion_status,
        client_notes=client_notes,
        pt_notes=pt_notes,
    )
    session.add(workout_log)
    session.flush()
    return workout_log


def list_workout_logs_for_client(session: Session, client_user_id: uuid.UUID) -> list[WorkoutLog]:
    stmt: Select[tuple[WorkoutLog]] = (
        select(WorkoutLog)
        .where(WorkoutLog.client_user_id == client_user_id)
        .order_by(
            WorkoutLog.performed_at.desc(), WorkoutLog.created_at.desc(), WorkoutLog.id.desc()
        )
    )
    return list(session.scalars(stmt))


def list_workout_logs_for_pt(session: Session, pt_user_id: uuid.UUID) -> list[WorkoutLog]:
    stmt: Select[tuple[WorkoutLog]] = (
        select(WorkoutLog)
        .where(WorkoutLog.pt_user_id == pt_user_id)
        .order_by(
            WorkoutLog.performed_at.desc(), WorkoutLog.created_at.desc(), WorkoutLog.id.desc()
        )
    )
    return list(session.scalars(stmt))


def list_workout_logs_for_pt_client(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> list[WorkoutLog]:
    stmt: Select[tuple[WorkoutLog]] = (
        select(WorkoutLog)
        .where(
            WorkoutLog.pt_user_id == pt_user_id,
            WorkoutLog.client_user_id == client_user_id,
        )
        .order_by(
            WorkoutLog.performed_at.desc(), WorkoutLog.created_at.desc(), WorkoutLog.id.desc()
        )
    )
    return list(session.scalars(stmt))


def package_contains_routine(
    session: Session,
    *,
    training_package_id: uuid.UUID,
    routine_id: uuid.UUID,
) -> bool:
    stmt: Select[tuple[TrainingPackageRoutine]] = select(TrainingPackageRoutine).where(
        TrainingPackageRoutine.training_package_id == training_package_id,
        TrainingPackageRoutine.routine_id == routine_id,
    )
    return session.scalar(stmt) is not None
