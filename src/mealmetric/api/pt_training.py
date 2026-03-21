from collections.abc import Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import (
    get_current_user,
    require_roles,
    require_trusted_caller,
)
from mealmetric.api.schemas.metrics import (
    MetricsFreshnessResponse,
    OverviewMetricsResponse,
)
from mealmetric.api.schemas.training import (
    ChecklistItemListResponse,
    ChecklistItemRead,
    ChecklistReplaceRequest,
    ClientAssignmentCreateRequest,
    ClientAssignmentListResponse,
    ClientAssignmentRead,
    ClientAssignmentStatusUpdateRequest,
    PackageRoutineListResponse,
    PackageRoutineRead,
    PackageRoutineReplaceRequest,
    PTClientDetailRead,
    PTClientLinkCreateRequest,
    PTClientLinkListResponse,
    PTClientLinkRead,
    PTClientLinkStatusUpdateRequest,
    PTClientProfileRead,
    PTFolderCreateRequest,
    PTFolderListResponse,
    PTFolderRead,
    PTFolderUpdateRequest,
    PTProfileRead,
    PTProfileUpdateRequest,
    RoutineCreateRequest,
    RoutineListResponse,
    RoutineRead,
    RoutineUpdateRequest,
    TrainingPackageCreateRequest,
    TrainingPackageListResponse,
    TrainingPackageRead,
    TrainingPackageUpdateRequest,
)
from mealmetric.db.session import get_db
from mealmetric.models.training import (
    ChecklistItem,
    ClientTrainingPackageAssignment,
    PtClientLink,
    PtFolder,
    PtProfile,
    Routine,
    TrainingPackage,
    TrainingPackageRoutine,
)
from mealmetric.models.user import Role, User
from mealmetric.services.metrics_service import MetricsFreshness, OverviewMetricsView
from mealmetric.services.training_service import (
    AssignmentService,
    ChecklistItemInput,
    ChecklistService,
    PackageRoutineInput,
    PTClientDetailView,
    PtClientLinkService,
    PtFolderService,
    PtProfileService,
    RoutineService,
    TrainingConflictError,
    TrainingNotFoundError,
    TrainingPackageService,
    TrainingPermissionError,
    TrainingValidationError,
)

router = APIRouter(
    prefix="/pt",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.PT))],
    tags=["pt-training"],
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
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error"
    )


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


def _profile_to_read(profile: PtProfile) -> PTProfileRead:
    return PTProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        display_name=profile.display_name,
        bio=profile.bio,
        certifications_text=profile.certifications_text,
        specialties_text=profile.specialties_text,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _client_link_to_read(link: PtClientLink) -> PTClientLinkRead:
    return PTClientLinkRead(
        id=link.id,
        pt_user_id=link.pt_user_id,
        client_user_id=link.client_user_id,
        status=link.status,
        started_at=link.started_at,
        ended_at=link.ended_at,
        notes=link.notes,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _folder_to_read(folder: PtFolder) -> PTFolderRead:
    return PTFolderRead(
        id=folder.id,
        pt_user_id=folder.pt_user_id,
        name=folder.name,
        description=folder.description,
        sort_order=folder.sort_order,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def _routine_to_read(routine: Routine) -> RoutineRead:
    return RoutineRead(
        id=routine.id,
        pt_user_id=routine.pt_user_id,
        folder_id=routine.folder_id,
        title=routine.title,
        description=routine.description,
        difficulty=routine.difficulty,
        estimated_minutes=routine.estimated_minutes,
        is_archived=routine.is_archived,
        created_at=routine.created_at,
        updated_at=routine.updated_at,
    )


def _training_package_to_read(training_package: TrainingPackage) -> TrainingPackageRead:
    return TrainingPackageRead(
        id=training_package.id,
        pt_user_id=training_package.pt_user_id,
        folder_id=training_package.folder_id,
        title=training_package.title,
        description=training_package.description,
        status=training_package.status,
        duration_days=training_package.duration_days,
        is_template=training_package.is_template,
        created_at=training_package.created_at,
        updated_at=training_package.updated_at,
    )


def _package_routine_to_read(link: TrainingPackageRoutine) -> PackageRoutineRead:
    return PackageRoutineRead(
        id=link.id,
        training_package_id=link.training_package_id,
        routine_id=link.routine_id,
        position=link.position,
        day_label=link.day_label,
        created_at=link.created_at,
    )


def _checklist_item_to_read(item: ChecklistItem) -> ChecklistItemRead:
    return ChecklistItemRead(
        id=item.id,
        training_package_id=item.training_package_id,
        routine_id=item.routine_id,
        label=item.label,
        details=item.details,
        position=item.position,
        is_required=item.is_required,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _assignment_to_read(
    assignment: ClientTrainingPackageAssignment,
) -> ClientAssignmentRead:
    return ClientAssignmentRead(
        id=assignment.id,
        training_package_id=assignment.training_package_id,
        pt_user_id=assignment.pt_user_id,
        client_user_id=assignment.client_user_id,
        pt_client_link_id=assignment.pt_client_link_id,
        status=assignment.status,
        assigned_at=assignment.assigned_at,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


def _freshness_to_response(freshness: MetricsFreshness) -> MetricsFreshnessResponse:
    return MetricsFreshnessResponse(
        source=freshness.source,
        computed_at=freshness.computed_at,
        snapshot_generated_at=freshness.snapshot_generated_at,
        source_window_start=freshness.source_window_start,
        source_window_end=freshness.source_window_end,
        version=freshness.version,
    )


def _overview_to_response(view: OverviewMetricsView) -> OverviewMetricsResponse:
    return OverviewMetricsResponse(
        client_user_id=view.client_user_id,
        as_of_date=view.as_of_date,
        week_start_date=view.week_start_date,
        week_end_date=view.week_end_date,
        business_timezone=view.business_timezone,
        week_start_day=view.week_start_day,
        total_intake_calories=view.total_intake_calories,
        total_expenditure_calories=view.total_expenditure_calories,
        net_calorie_balance=view.net_calorie_balance,
        weekly_target_deficit_calories=view.weekly_target_deficit_calories,
        deficit_progress_percent=view.deficit_progress_percent,
        current_intake_ceiling_calories=view.current_intake_ceiling_calories,
        current_expenditure_floor_calories=view.current_expenditure_floor_calories,
        has_data=view.has_data,
        freshness=_freshness_to_response(view.freshness),
    )


def _client_detail_to_read(view: PTClientDetailView) -> PTClientDetailRead:
    return PTClientDetailRead(
        client=PTClientProfileRead(
            id=view.client.id,
            email=view.client.email,
            role=view.client.role,
            created_at=view.client.created_at,
        ),
        current_assignments=[
            _assignment_to_read(item) for item in view.current_assignments
        ],
        assignments_count=len(view.current_assignments),
        metrics_snapshot=_overview_to_response(view.metrics_snapshot),
    )


@router.get("/profile/me", response_model=PTProfileRead)
def get_pt_profile_me(db: DBSessionDep, current_user: CurrentUserDep) -> PTProfileRead:
    session = _require_db(db)
    service = PtProfileService(session)
    profile = service.get_by_user_id(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="pt_profile_not_found"
        )
    return _profile_to_read(profile)


@router.put("/profile/me", response_model=PTProfileRead)
def update_pt_profile_me(
    payload: PTProfileUpdateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTProfileRead:
    session = _require_db(db)
    service = PtProfileService(session)

    def _operation() -> PtProfile:
        return service.update_profile(
            user_id=current_user.id,
            display_name=payload.display_name,
            bio=payload.bio,
            certifications_text=payload.certifications_text,
            specialties_text=payload.specialties_text,
            is_active=payload.is_active,
        )

    updated = _run_mutation(session, _operation)
    return _profile_to_read(updated)


@router.get("/clients", response_model=PTClientLinkListResponse)
def list_pt_clients(
    db: DBSessionDep, current_user: CurrentUserDep
) -> PTClientLinkListResponse:
    session = _require_db(db)
    service = PtClientLinkService(session)
    links = service.list_for_pt(current_user.id)
    items = [_client_link_to_read(link) for link in links]
    return PTClientLinkListResponse(items=items, count=len(items))


@router.get("/clients/links", response_model=PTClientLinkListResponse)
def list_pt_client_links(
    db: DBSessionDep, current_user: CurrentUserDep
) -> PTClientLinkListResponse:
    return list_pt_clients(db=db, current_user=current_user)


@router.post(
    "/clients/links",
    response_model=PTClientLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_pt_client_link(
    payload: PTClientLinkCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTClientLinkRead:
    session = _require_db(db)
    service = PtClientLinkService(session)

    def _operation() -> PtClientLink:
        return service.create_link(
            pt_user_id=current_user.id,
            client_user_id=payload.client_user_id,
            status=payload.status,
            notes=payload.notes,
        )

    link = _run_mutation(session, _operation)
    return _client_link_to_read(link)


@router.patch("/clients/links/{link_id}", response_model=PTClientLinkRead)
def update_pt_client_link_status(
    link_id: UUID,
    payload: PTClientLinkStatusUpdateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTClientLinkRead:
    session = _require_db(db)
    service = PtClientLinkService(session)

    def _operation() -> PtClientLink:
        return service.update_status(
            pt_user_id=current_user.id,
            link_id=link_id,
            status=payload.status,
        )

    updated = _run_mutation(session, _operation)
    return _client_link_to_read(updated)


@router.get("/folders", response_model=PTFolderListResponse)
def list_pt_folders(
    db: DBSessionDep, current_user: CurrentUserDep
) -> PTFolderListResponse:
    session = _require_db(db)
    service = PtFolderService(session)
    folders = service.list_folders(current_user.id)
    items = [_folder_to_read(folder) for folder in folders]
    return PTFolderListResponse(items=items, count=len(items))


@router.post(
    "/folders", response_model=PTFolderRead, status_code=status.HTTP_201_CREATED
)
def create_pt_folder(
    payload: PTFolderCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTFolderRead:
    session = _require_db(db)
    service = PtFolderService(session)

    def _operation() -> PtFolder:
        return service.create_folder(
            pt_user_id=current_user.id,
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
        )

    folder = _run_mutation(session, _operation)
    return _folder_to_read(folder)


@router.patch("/folders/{folder_id}", response_model=PTFolderRead)
def update_pt_folder(
    folder_id: UUID,
    payload: PTFolderUpdateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PTFolderRead:
    session = _require_db(db)
    service = PtFolderService(session)

    def _operation() -> PtFolder:
        return service.update_folder(
            pt_user_id=current_user.id,
            folder_id=folder_id,
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
        )

    updated = _run_mutation(session, _operation)
    return _folder_to_read(updated)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pt_folder(
    folder_id: UUID, db: DBSessionDep, current_user: CurrentUserDep
) -> Response:
    session = _require_db(db)
    service = PtFolderService(session)

    def _operation() -> None:
        service.delete_folder(pt_user_id=current_user.id, folder_id=folder_id)
        return None

    _run_mutation(session, _operation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/routines", response_model=RoutineListResponse)
def list_pt_routines(
    db: DBSessionDep, current_user: CurrentUserDep
) -> RoutineListResponse:
    session = _require_db(db)
    service = RoutineService(session)
    routines = service.list_routines(current_user.id)
    items = [_routine_to_read(routine) for routine in routines]
    return RoutineListResponse(items=items, count=len(items))


@router.get("/routines/{routine_id}", response_model=RoutineRead)
def get_pt_routine(
    routine_id: UUID, db: DBSessionDep, current_user: CurrentUserDep
) -> RoutineRead:
    session = _require_db(db)
    service = RoutineService(session)
    try:
        routine = service.get_routine(pt_user_id=current_user.id, routine_id=routine_id)
    except (
        TrainingNotFoundError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc
    return _routine_to_read(routine)


@router.post(
    "/routines", response_model=RoutineRead, status_code=status.HTTP_201_CREATED
)
def create_pt_routine(
    payload: RoutineCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> RoutineRead:
    session = _require_db(db)
    service = RoutineService(session)

    def _operation() -> Routine:
        return service.create_routine(
            pt_user_id=current_user.id,
            title=payload.title,
            folder_id=payload.folder_id,
            description=payload.description,
            difficulty=payload.difficulty,
            estimated_minutes=payload.estimated_minutes,
        )

    routine = _run_mutation(session, _operation)
    return _routine_to_read(routine)


@router.patch("/routines/{routine_id}", response_model=RoutineRead)
def update_pt_routine(
    routine_id: UUID,
    payload: RoutineUpdateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> RoutineRead:
    session = _require_db(db)
    service = RoutineService(session)

    def _operation() -> Routine:
        return service.update_routine(
            pt_user_id=current_user.id,
            routine_id=routine_id,
            title=payload.title,
            folder_id=payload.folder_id,
            description=payload.description,
            difficulty=payload.difficulty,
            estimated_minutes=payload.estimated_minutes,
        )

    updated = _run_mutation(session, _operation)
    return _routine_to_read(updated)


@router.delete("/routines/{routine_id}", response_model=RoutineRead)
def archive_pt_routine(
    routine_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> RoutineRead:
    session = _require_db(db)
    service = RoutineService(session)

    def _operation() -> Routine:
        return service.archive_routine(
            pt_user_id=current_user.id, routine_id=routine_id
        )

    archived = _run_mutation(session, _operation)
    return _routine_to_read(archived)


@router.get("/packages", response_model=TrainingPackageListResponse)
def list_pt_packages(
    db: DBSessionDep, current_user: CurrentUserDep
) -> TrainingPackageListResponse:
    session = _require_db(db)
    service = TrainingPackageService(session)
    packages = service.list_training_packages(current_user.id)
    items = [
        _training_package_to_read(training_package) for training_package in packages
    ]
    return TrainingPackageListResponse(items=items, count=len(items))


@router.get("/packages/{package_id}", response_model=TrainingPackageRead)
def get_pt_package(
    package_id: UUID, db: DBSessionDep, current_user: CurrentUserDep
) -> TrainingPackageRead:
    session = _require_db(db)
    service = TrainingPackageService(session)
    try:
        training_package = service.get_training_package(
            pt_user_id=current_user.id,
            training_package_id=package_id,
        )
    except (
        TrainingNotFoundError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc
    return _training_package_to_read(training_package)


@router.post(
    "/packages", response_model=TrainingPackageRead, status_code=status.HTTP_201_CREATED
)
def create_pt_package(
    payload: TrainingPackageCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> TrainingPackageRead:
    session = _require_db(db)
    service = TrainingPackageService(session)

    def _operation() -> TrainingPackage:
        return service.create_training_package(
            pt_user_id=current_user.id,
            title=payload.title,
            folder_id=payload.folder_id,
            description=payload.description,
            status=payload.status,
            duration_days=payload.duration_days,
            is_template=payload.is_template,
        )

    training_package = _run_mutation(session, _operation)
    return _training_package_to_read(training_package)


@router.patch("/packages/{package_id}", response_model=TrainingPackageRead)
def update_pt_package(
    package_id: UUID,
    payload: TrainingPackageUpdateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> TrainingPackageRead:
    session = _require_db(db)
    service = TrainingPackageService(session)

    def _operation() -> TrainingPackage:
        return service.update_training_package(
            pt_user_id=current_user.id,
            training_package_id=package_id,
            title=payload.title,
            folder_id=payload.folder_id,
            description=payload.description,
            status=payload.status,
            duration_days=payload.duration_days,
            is_template=payload.is_template,
        )

    updated = _run_mutation(session, _operation)
    return _training_package_to_read(updated)


@router.delete("/packages/{package_id}", response_model=TrainingPackageRead)
def archive_pt_package(
    package_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> TrainingPackageRead:
    session = _require_db(db)
    service = TrainingPackageService(session)

    def _operation() -> TrainingPackage:
        return service.archive_training_package(
            pt_user_id=current_user.id,
            training_package_id=package_id,
        )

    archived = _run_mutation(session, _operation)
    return _training_package_to_read(archived)


@router.get(
    "/packages/{package_id}/routines", response_model=PackageRoutineListResponse
)
def list_package_routines(
    package_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PackageRoutineListResponse:
    session = _require_db(db)
    service = TrainingPackageService(session)
    try:
        routines = service.list_package_routines(
            pt_user_id=current_user.id,
            training_package_id=package_id,
        )
    except (
        TrainingNotFoundError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc
    items = [_package_routine_to_read(item) for item in routines]
    return PackageRoutineListResponse(items=items, count=len(items))


@router.put(
    "/packages/{package_id}/routines", response_model=PackageRoutineListResponse
)
def replace_package_routines(
    package_id: UUID,
    payload: PackageRoutineReplaceRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> PackageRoutineListResponse:
    session = _require_db(db)
    service = TrainingPackageService(session)

    def _operation() -> list[TrainingPackageRoutine]:
        return service.replace_package_routines(
            pt_user_id=current_user.id,
            training_package_id=package_id,
            routines=[
                PackageRoutineInput(
                    routine_id=item.routine_id,
                    position=item.position,
                    day_label=item.day_label,
                )
                for item in payload.items
            ],
        )

    routines = _run_mutation(session, _operation)
    items = [_package_routine_to_read(item) for item in routines]
    return PackageRoutineListResponse(items=items, count=len(items))


@router.get(
    "/packages/{package_id}/checklist", response_model=ChecklistItemListResponse
)
def list_package_checklist(
    package_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ChecklistItemListResponse:
    session = _require_db(db)
    service = ChecklistService(session)
    try:
        checklist_items = service.list_package_checklist(
            pt_user_id=current_user.id,
            training_package_id=package_id,
        )
    except (
        TrainingNotFoundError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc
    items = [_checklist_item_to_read(item) for item in checklist_items]
    return ChecklistItemListResponse(items=items, count=len(items))


@router.put(
    "/packages/{package_id}/checklist", response_model=ChecklistItemListResponse
)
def replace_package_checklist(
    package_id: UUID,
    payload: ChecklistReplaceRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ChecklistItemListResponse:
    session = _require_db(db)
    service = ChecklistService(session)

    def _operation() -> list[ChecklistItem]:
        return service.replace_package_checklist(
            pt_user_id=current_user.id,
            training_package_id=package_id,
            items=[
                ChecklistItemInput(
                    label=item.label,
                    details=item.details,
                    position=item.position,
                    is_required=item.is_required,
                )
                for item in payload.items
            ],
        )

    checklist_items = _run_mutation(session, _operation)
    items = [_checklist_item_to_read(item) for item in checklist_items]
    return ChecklistItemListResponse(items=items, count=len(items))


@router.get(
    "/routines/{routine_id}/checklist", response_model=ChecklistItemListResponse
)
def list_routine_checklist(
    routine_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ChecklistItemListResponse:
    session = _require_db(db)
    service = ChecklistService(session)
    try:
        checklist_items = service.list_routine_checklist(
            pt_user_id=current_user.id,
            routine_id=routine_id,
        )
    except (
        TrainingNotFoundError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc
    items = [_checklist_item_to_read(item) for item in checklist_items]
    return ChecklistItemListResponse(items=items, count=len(items))


@router.put(
    "/routines/{routine_id}/checklist", response_model=ChecklistItemListResponse
)
def replace_routine_checklist(
    routine_id: UUID,
    payload: ChecklistReplaceRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ChecklistItemListResponse:
    session = _require_db(db)
    service = ChecklistService(session)

    def _operation() -> list[ChecklistItem]:
        return service.replace_routine_checklist(
            pt_user_id=current_user.id,
            routine_id=routine_id,
            items=[
                ChecklistItemInput(
                    label=item.label,
                    details=item.details,
                    position=item.position,
                    is_required=item.is_required,
                )
                for item in payload.items
            ],
        )

    checklist_items = _run_mutation(session, _operation)
    items = [_checklist_item_to_read(item) for item in checklist_items]
    return ChecklistItemListResponse(items=items, count=len(items))


@router.get("/clients/{client_user_id}", response_model=PTClientDetailRead)
def get_pt_client_detail(
    client_user_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    as_of_date: date | None = None,
) -> PTClientDetailRead:
    session = _require_db(db)
    service = PtClientLinkService(session)
    try:
        view = service.get_client_detail(
            pt_user_id=current_user.id,
            client_user_id=client_user_id,
            as_of_date=as_of_date,
        )
    except (
        TrainingNotFoundError,
        TrainingPermissionError,
        TrainingValidationError,
    ) as exc:
        raise _translate_service_error(exc) from exc
    return _client_detail_to_read(view)


@router.get(
    "/clients/{client_user_id}/assignments",
    response_model=ClientAssignmentListResponse,
)
def list_client_assignments(
    client_user_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ClientAssignmentListResponse:
    session = _require_db(db)
    service = AssignmentService(session)
    assignments = service.list_assignments_for_pt_client(
        pt_user_id=current_user.id,
        client_user_id=client_user_id,
    )
    items = [_assignment_to_read(assignment) for assignment in assignments]
    return ClientAssignmentListResponse(items=items, count=len(items))


@router.post(
    "/clients/{client_user_id}/assignments",
    response_model=ClientAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_package_to_client(
    client_user_id: UUID,
    payload: ClientAssignmentCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ClientAssignmentRead:
    session = _require_db(db)
    service = AssignmentService(session)

    def _operation() -> ClientTrainingPackageAssignment:
        return service.assign_package_to_client(
            pt_user_id=current_user.id,
            client_user_id=client_user_id,
            training_package_id=payload.training_package_id,
            status=payload.status,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )

    assignment = _run_mutation(session, _operation)
    return _assignment_to_read(assignment)


@router.patch("/assignments/{assignment_id}", response_model=ClientAssignmentRead)
def update_assignment_status(
    assignment_id: UUID,
    payload: ClientAssignmentStatusUpdateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ClientAssignmentRead:
    session = _require_db(db)
    service = AssignmentService(session)

    def _operation() -> ClientTrainingPackageAssignment:
        return service.update_assignment_status(
            pt_user_id=current_user.id,
            assignment_id=assignment_id,
            status=payload.status,
        )

    assignment = _run_mutation(session, _operation)
    return _assignment_to_read(assignment)
