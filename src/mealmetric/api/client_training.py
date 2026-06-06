from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.client_training import (
    ClientAssignmentChecklistItemRead,
    ClientAssignmentChecklistResponse,
    ClientAssignmentDetailResponse,
    ClientAssignmentListResponse,
    ClientAssignmentRead,
    ClientAssignmentRoutineRead,
    ClientTrainingPackageSummary,
    ClientWorkoutLogCreateRequest,
    ClientWorkoutLogExerciseEntryRead,
    ClientWorkoutLogListResponse,
    ClientWorkoutLogRead,
)
from mealmetric.db.session import get_db
from mealmetric.models.training import (
    ChecklistItem,
    ClientTrainingPackageAssignment,
    TrainingPackage,
    TrainingPackageRoutine,
    WorkoutLog,
    WorkoutLogMode,
)
from mealmetric.models.user import Role, User
from mealmetric.services.training_service import (
    ClientTrainingService,
    TrainingConflictError,
    TrainingNotFoundError,
    TrainingPermissionError,
    TrainingValidationError,
    WorkoutLogExerciseEntryInput,
    resolve_workout_log_mode,
)

router = APIRouter(
    prefix="/client/training",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-training"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    return db


def _translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TrainingNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, TrainingConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, TrainingPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, TrainingValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


def _run_mutation[T](db: Session, operation: Callable[[], T]) -> T:
    try:
        result = operation()
        db.commit()
        return result
    except (
        TrainingNotFoundError,
        TrainingConflictError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        db.rollback()
        raise _translate_service_error(exc) from exc


def _to_package_summary(training_package: TrainingPackage) -> ClientTrainingPackageSummary:
    return ClientTrainingPackageSummary(
        id=training_package.id,
        title=training_package.title,
        description=training_package.description,
        status=training_package.status,
        duration_days=training_package.duration_days,
        is_template=training_package.is_template,
    )


def _to_assignment_read(assignment: ClientTrainingPackageAssignment) -> ClientAssignmentRead:
    return ClientAssignmentRead(
        id=assignment.id,
        training_package_id=assignment.training_package_id,
        pt_user_id=assignment.pt_user_id,
        client_user_id=assignment.client_user_id,
        status=assignment.status,
        assigned_at=assignment.assigned_at,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        package=_to_package_summary(assignment.training_package),
    )


def _to_assignment_routine_read(link: TrainingPackageRoutine) -> ClientAssignmentRoutineRead:
    return ClientAssignmentRoutineRead(
        routine_id=link.routine_id,
        position=link.position,
        day_label=link.day_label,
        title=link.routine.title,
        description=link.routine.description,
        difficulty=link.routine.difficulty,
        estimated_minutes=link.routine.estimated_minutes,
    )


def _to_checklist_item_read(item: ChecklistItem) -> ClientAssignmentChecklistItemRead:
    return ClientAssignmentChecklistItemRead(
        id=item.id,
        label=item.label,
        details=item.details,
        position=item.position,
        is_required=item.is_required,
    )


def _to_workout_log_read(workout_log: WorkoutLog) -> ClientWorkoutLogRead:
    return ClientWorkoutLogRead(
        id=workout_log.id,
        client_user_id=workout_log.client_user_id,
        pt_user_id=workout_log.pt_user_id,
        assignment_id=workout_log.assignment_id,
        routine_id=workout_log.routine_id,
        routine_title=workout_log.routine.title if workout_log.routine is not None else None,
        performed_at=workout_log.performed_at,
        duration_minutes=workout_log.duration_minutes,
        mode=resolve_workout_log_mode(mode=workout_log.mode, routine_id=workout_log.routine_id),
        completion_status=workout_log.completion_status,
        client_notes=workout_log.client_notes,
        pt_notes=workout_log.pt_notes,
        exercise_entries=[
            ClientWorkoutLogExerciseEntryRead(
                id=entry.id,
                exercise_name=entry.exercise_name,
                sets=entry.sets,
                reps=entry.reps,
                weight=entry.weight,
                duration_seconds=entry.duration_seconds,
                notes=entry.notes,
                position=entry.position,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
            for entry in workout_log.exercise_entries
        ],
        created_at=workout_log.created_at,
        updated_at=workout_log.updated_at,
    )


@router.get("/assignments", response_model=ClientAssignmentListResponse)
def list_client_assignments(
    db: DBSessionDep, current_user: CurrentUserDep
) -> ClientAssignmentListResponse:
    session = _require_db(db)
    service = ClientTrainingService(session)
    assignments = service.list_assignments_for_client(current_user.id)
    items = [_to_assignment_read(assignment) for assignment in assignments]
    return ClientAssignmentListResponse(items=items, count=len(items))


@router.get("/assignments/{assignment_id}", response_model=ClientAssignmentDetailResponse)
def get_client_assignment_detail(
    assignment_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ClientAssignmentDetailResponse:
    session = _require_db(db)
    service = ClientTrainingService(session)
    try:
        assignment = service.get_assignment_for_client(
            client_user_id=current_user.id,
            assignment_id=assignment_id,
        )
        routines = service.list_assignment_routines_for_client(
            client_user_id=current_user.id,
            assignment_id=assignment_id,
        )
        checklist_items = service.list_assignment_checklist_for_client(
            client_user_id=current_user.id,
            assignment_id=assignment_id,
        )
    except (TrainingNotFoundError, TrainingPermissionError, TrainingValidationError) as exc:
        raise _translate_service_error(exc) from exc

    base = _to_assignment_read(assignment)
    return ClientAssignmentDetailResponse(
        **base.model_dump(),
        routines=[_to_assignment_routine_read(link) for link in routines],
        checklist_items=[_to_checklist_item_read(item) for item in checklist_items],
    )


@router.get(
    "/assignments/{assignment_id}/checklist",
    response_model=ClientAssignmentChecklistResponse,
)
def get_client_assignment_checklist(
    assignment_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ClientAssignmentChecklistResponse:
    session = _require_db(db)
    service = ClientTrainingService(session)
    try:
        checklist_items = service.list_assignment_checklist_for_client(
            client_user_id=current_user.id,
            assignment_id=assignment_id,
        )
    except (TrainingNotFoundError, TrainingPermissionError, TrainingValidationError) as exc:
        raise _translate_service_error(exc) from exc

    items = [_to_checklist_item_read(item) for item in checklist_items]
    return ClientAssignmentChecklistResponse(items=items, count=len(items))


@router.get("/workout-logs", response_model=ClientWorkoutLogListResponse)
def list_client_workout_logs(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    mode: WorkoutLogMode | None = None,
    search: str | None = None,
) -> ClientWorkoutLogListResponse:
    session = _require_db(db)
    service = ClientTrainingService(session)
    page = service.list_workout_log_page_for_client(
        client_user_id=current_user.id,
        limit=limit,
        offset=offset,
        mode=mode,
        search=search,
    )
    items = [_to_workout_log_read(workout_log) for workout_log in page.items]
    return ClientWorkoutLogListResponse(
        items=items,
        count=len(items),
        limit=page.limit,
        offset=page.offset,
        next_offset=page.next_offset,
        has_more=page.has_more,
    )


@router.post(
    "/workout-logs",
    response_model=ClientWorkoutLogRead,
    status_code=status.HTTP_201_CREATED,
)
def create_client_workout_log(
    payload: ClientWorkoutLogCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ClientWorkoutLogRead:
    session = _require_db(db)
    service = ClientTrainingService(session)

    def _operation() -> WorkoutLog:
        return service.create_workout_log_for_client(
            client_user_id=current_user.id,
            assignment_id=payload.assignment_id,
            routine_id=payload.routine_id,
            mode=payload.mode,
            performed_at=payload.performed_at,
            duration_minutes=payload.duration_minutes,
            completion_status=payload.completion_status,
            client_notes=payload.client_notes,
            exercise_entries=[
                WorkoutLogExerciseEntryInput(
                    exercise_name=entry.exercise_name,
                    sets=entry.sets,
                    reps=entry.reps,
                    weight=(str(entry.weight) if entry.weight is not None else None),
                    duration_seconds=entry.duration_seconds,
                    notes=entry.notes,
                    position=entry.position,
                )
                for entry in payload.exercise_entries
            ],
        )

    workout_log = _run_mutation(session, _operation)
    return _to_workout_log_read(workout_log)
