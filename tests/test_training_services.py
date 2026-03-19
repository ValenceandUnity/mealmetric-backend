from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory, AuditLog
from mealmetric.models.training import (
    AssignmentStatus,
    PtClientLinkStatus,
    TrainingPackageStatus,
    WorkoutCompletionStatus,
)
from mealmetric.models.user import Role, User
from mealmetric.services.training_service import (
    AssignmentService,
    ChecklistItemInput,
    ChecklistService,
    PackageRoutineInput,
    PtClientLinkService,
    PtFolderService,
    PtProfileService,
    RoutineService,
    TrainingConflictError,
    TrainingNotFoundError,
    TrainingPackageService,
    TrainingPermissionError,
    TrainingValidationError,
    WorkoutLogService,
)


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _create_user(db: Session, *, email: str, role: Role) -> User:
    user = User(email=email, password_hash="hash", role=role)
    db.add(user)
    db.flush()
    return user


def test_pt_profile_duplicate_prevention() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt = _create_user(db, email="pt-profile@example.com", role=Role.PT)
        service = PtProfileService(db)

        created = service.create_profile(user_id=pt.id, display_name="Coach")
        assert created.user_id == pt.id

        with pytest.raises(TrainingConflictError):
            service.create_profile(user_id=pt.id, display_name="Coach 2")


def test_pt_client_duplicate_prevention() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt = _create_user(db, email="pt-link@example.com", role=Role.PT)
        client = _create_user(db, email="client-link@example.com", role=Role.CLIENT)
        service = PtClientLinkService(db)

        link = service.create_link(pt_user_id=pt.id, client_user_id=client.id)
        assert link.status == PtClientLinkStatus.PENDING

        with pytest.raises(TrainingConflictError):
            service.create_link(pt_user_id=pt.id, client_user_id=client.id)


def test_pt_cannot_operate_on_other_pt_folder_routine_or_package() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt1 = _create_user(db, email="pt1-scope@example.com", role=Role.PT)
        pt2 = _create_user(db, email="pt2-scope@example.com", role=Role.PT)

        folder_service = PtFolderService(db)
        routine_service = RoutineService(db)
        package_service = TrainingPackageService(db)

        folder = folder_service.create_folder(pt_user_id=pt1.id, name="PT1")
        routine = routine_service.create_routine(pt_user_id=pt1.id, title="R1", folder_id=folder.id)
        training_package = package_service.create_training_package(
            pt_user_id=pt1.id,
            title="P1",
            folder_id=folder.id,
        )

        with pytest.raises(TrainingNotFoundError):
            folder_service.update_folder(
                pt_user_id=pt2.id,
                folder_id=folder.id,
                name="nope",
                description=None,
                sort_order=0,
            )

        with pytest.raises(TrainingNotFoundError):
            routine_service.update_routine(
                pt_user_id=pt2.id,
                routine_id=routine.id,
                title="nope",
                folder_id=None,
                description=None,
                difficulty=None,
                estimated_minutes=None,
            )

        with pytest.raises(TrainingNotFoundError):
            package_service.update_training_package(
                pt_user_id=pt2.id,
                training_package_id=training_package.id,
                title="nope",
                folder_id=None,
                description=None,
                status=TrainingPackageStatus.DRAFT,
                duration_days=None,
                is_template=True,
            )


def test_package_composition_rejects_routine_owned_by_other_pt() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt1 = _create_user(db, email="pt1-comp@example.com", role=Role.PT)
        pt2 = _create_user(db, email="pt2-comp@example.com", role=Role.PT)

        routine_service = RoutineService(db)
        package_service = TrainingPackageService(db)

        routine_pt1 = routine_service.create_routine(pt_user_id=pt1.id, title="R1")
        routine_pt2 = routine_service.create_routine(pt_user_id=pt2.id, title="R2")
        training_package = package_service.create_training_package(pt_user_id=pt1.id, title="P1")

        with pytest.raises(TrainingPermissionError):
            package_service.replace_package_routines(
                pt_user_id=pt1.id,
                training_package_id=training_package.id,
                routines=[
                    PackageRoutineInput(routine_id=routine_pt1.id, position=1),
                    PackageRoutineInput(routine_id=routine_pt2.id, position=2),
                ],
            )


def test_assignment_requires_matching_link_and_owned_package() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt1 = _create_user(db, email="pt1-assign@example.com", role=Role.PT)
        pt2 = _create_user(db, email="pt2-assign@example.com", role=Role.PT)
        client = _create_user(db, email="client-assign@example.com", role=Role.CLIENT)

        link_service = PtClientLinkService(db)
        package_service = TrainingPackageService(db)
        assignment_service = AssignmentService(db)

        package_pt1 = package_service.create_training_package(pt_user_id=pt1.id, title="P1")
        package_pt2 = package_service.create_training_package(pt_user_id=pt2.id, title="P2")

        with pytest.raises(TrainingValidationError):
            assignment_service.assign_package_to_client(
                pt_user_id=pt1.id,
                client_user_id=client.id,
                training_package_id=package_pt1.id,
            )

        link_service.create_link(pt_user_id=pt1.id, client_user_id=client.id)

        with pytest.raises(TrainingNotFoundError):
            assignment_service.assign_package_to_client(
                pt_user_id=pt1.id,
                client_user_id=client.id,
                training_package_id=package_pt2.id,
            )

        assigned = assignment_service.assign_package_to_client(
            pt_user_id=pt1.id,
            client_user_id=client.id,
            training_package_id=package_pt1.id,
            status=AssignmentStatus.ACTIVE,
        )
        assert assigned.status == AssignmentStatus.ACTIVE
        audit_rows = list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.asc())))
        assert len(audit_rows) == 1
        assert audit_rows[0].category == AuditEventCategory.TRAINING
        assert audit_rows[0].action == AuditEventAction.PT_CLIENT_ASSIGNMENT_CREATED
        assert audit_rows[0].actor_user_id == pt1.id
        assert audit_rows[0].target_entity_id == str(assigned.id)
        assert audit_rows[0].metadata_json["client_user_id"] == str(client.id)
        assert audit_rows[0].metadata_json["status"] == AssignmentStatus.ACTIVE.value


def test_assignment_status_update_persists_audit_row() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt = _create_user(db, email="pt-assign-status@example.com", role=Role.PT)
        client = _create_user(db, email="client-assign-status@example.com", role=Role.CLIENT)

        link_service = PtClientLinkService(db)
        package_service = TrainingPackageService(db)
        assignment_service = AssignmentService(db)

        link_service.create_link(
            pt_user_id=pt.id,
            client_user_id=client.id,
            status=PtClientLinkStatus.ACTIVE,
        )
        training_package = package_service.create_training_package(pt_user_id=pt.id, title="P1")
        assignment = assignment_service.assign_package_to_client(
            pt_user_id=pt.id,
            client_user_id=client.id,
            training_package_id=training_package.id,
            status=AssignmentStatus.ASSIGNED,
        )

        updated = assignment_service.update_assignment_status(
            pt_user_id=pt.id,
            assignment_id=assignment.id,
            status=AssignmentStatus.COMPLETED,
        )

        assert updated.status == AssignmentStatus.COMPLETED
        audit_rows = list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.asc())))
        assert len(audit_rows) == 2
        assert audit_rows[1].action == AuditEventAction.PT_CLIENT_ASSIGNMENT_STATUS_UPDATED
        assert audit_rows[1].metadata_json["from_status"] == AssignmentStatus.ASSIGNED.value
        assert audit_rows[1].metadata_json["to_status"] == AssignmentStatus.COMPLETED.value


def test_workout_logs_are_scope_filtered() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt1 = _create_user(db, email="pt1-logscope@example.com", role=Role.PT)
        pt2 = _create_user(db, email="pt2-logscope@example.com", role=Role.PT)
        client = _create_user(db, email="client-logscope@example.com", role=Role.CLIENT)

        link_service = PtClientLinkService(db)
        routine_service = RoutineService(db)
        package_service = TrainingPackageService(db)
        assignment_service = AssignmentService(db)
        workout_service = WorkoutLogService(db)

        link_service.create_link(
            pt_user_id=pt1.id,
            client_user_id=client.id,
            status=PtClientLinkStatus.ACTIVE,
        )
        routine = routine_service.create_routine(pt_user_id=pt1.id, title="R1")
        training_package = package_service.create_training_package(pt_user_id=pt1.id, title="P1")
        assignment = assignment_service.assign_package_to_client(
            pt_user_id=pt1.id,
            client_user_id=client.id,
            training_package_id=training_package.id,
        )

        workout_service.create_workout_log(
            pt_user_id=pt1.id,
            client_user_id=client.id,
            assignment_id=assignment.id,
            routine_id=routine.id,
            performed_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            completion_status=WorkoutCompletionStatus.COMPLETED,
        )

        pt_logs = workout_service.list_workout_logs_for_pt(pt_user_id=pt1.id)
        assert len(pt_logs) == 1

        client_self_logs = workout_service.list_workout_logs_for_client(
            requester_user_id=client.id,
            client_user_id=client.id,
        )
        assert len(client_self_logs) == 1

        pt_view_logs = workout_service.list_workout_logs_for_client(
            requester_user_id=pt1.id,
            client_user_id=client.id,
        )
        assert len(pt_view_logs) == 1

        with pytest.raises(TrainingPermissionError):
            workout_service.list_workout_logs_for_client(
                requester_user_id=pt2.id,
                client_user_id=client.id,
            )


def test_archive_and_update_behaviors() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt = _create_user(db, email="pt-archive@example.com", role=Role.PT)
        folder_service = PtFolderService(db)
        routine_service = RoutineService(db)
        package_service = TrainingPackageService(db)

        folder = folder_service.create_folder(pt_user_id=pt.id, name="Initial", sort_order=1)
        updated_folder = folder_service.update_folder(
            pt_user_id=pt.id,
            folder_id=folder.id,
            name="Updated",
            description="desc",
            sort_order=2,
        )
        assert updated_folder.name == "Updated"
        assert updated_folder.sort_order == 2

        routine = routine_service.create_routine(pt_user_id=pt.id, title="Routine")
        archived_routine = routine_service.archive_routine(pt_user_id=pt.id, routine_id=routine.id)
        assert archived_routine.is_archived is True

        training_package = package_service.create_training_package(
            pt_user_id=pt.id, title="Package"
        )
        archived_package = package_service.archive_training_package(
            pt_user_id=pt.id,
            training_package_id=training_package.id,
        )
        assert archived_package.status == TrainingPackageStatus.ARCHIVED


def test_checklist_replace_semantics_are_deterministic() -> None:
    session_local = _build_sqlite_sessionmaker()
    with session_local() as db:
        pt = _create_user(db, email="pt-checklist@example.com", role=Role.PT)

        routine_service = RoutineService(db)
        package_service = TrainingPackageService(db)
        checklist_service = ChecklistService(db)

        routine = routine_service.create_routine(pt_user_id=pt.id, title="R1")
        training_package = package_service.create_training_package(pt_user_id=pt.id, title="P1")

        first = checklist_service.replace_package_checklist(
            pt_user_id=pt.id,
            training_package_id=training_package.id,
            items=[
                ChecklistItemInput(label="b", position=2),
                ChecklistItemInput(label="a", position=1),
            ],
        )
        assert [item.position for item in first] == [1, 2]

        second = checklist_service.replace_package_checklist(
            pt_user_id=pt.id,
            training_package_id=training_package.id,
            items=[ChecklistItemInput(label="only", position=5)],
        )
        assert len(second) == 1
        listed = checklist_service.list_package_checklist(
            pt_user_id=pt.id,
            training_package_id=training_package.id,
        )
        assert len(listed) == 1
        assert listed[0].label == "only"

        routine_items = checklist_service.replace_routine_checklist(
            pt_user_id=pt.id,
            routine_id=routine.id,
            items=[ChecklistItemInput(label="r1", position=0)],
        )
        assert len(routine_items) == 1
