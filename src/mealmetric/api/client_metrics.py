from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import (
    get_current_user,
    require_roles,
    require_trusted_caller,
)
from mealmetric.api.schemas.metrics import (
    MetricsFreshnessResponse,
    MetricsHistoryResponse,
    OverviewMetricsResponse,
    WeeklyMetricsResponse,
)
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.metrics_service import (
    MetricsFreshness,
    MetricsPermissionError,
    MetricsService,
    MetricsServiceError,
    OverviewMetricsView,
    WeeklyMetricsView,
)

router = APIRouter(
    prefix="/metrics",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-metrics"],
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
    if isinstance(exc, MetricsPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, MetricsServiceError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="internal_error",
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


def _parse_iso_date(raw: str | None, detail: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        ) from exc


def _freshness_to_response(freshness: MetricsFreshness) -> MetricsFreshnessResponse:
    return MetricsFreshnessResponse(
        source=freshness.source,
        computed_at=freshness.computed_at,
        snapshot_generated_at=freshness.snapshot_generated_at,
        source_window_start=freshness.source_window_start,
        source_window_end=freshness.source_window_end,
        version=freshness.version,
    )


def _weekly_to_response(view: WeeklyMetricsView) -> WeeklyMetricsResponse:
    return WeeklyMetricsResponse(
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


@router.get("/overview", response_model=OverviewMetricsResponse)
def get_metrics_overview(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    as_of_date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
) -> OverviewMetricsResponse:
    session = _require_db(db)
    service = MetricsService(session)
    try:
        view = service.get_client_overview(
            client_user_id=current_user.id,
            as_of_date=_parse_iso_date(as_of_date, "invalid_date"),
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise _translate_service_error(exc) from exc

    return _overview_to_response(view)


@router.get("/weekly", response_model=WeeklyMetricsResponse)
def get_metrics_weekly(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    week_start_date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> WeeklyMetricsResponse:
    session = _require_db(db)
    service = MetricsService(session)
    try:
        parsed_week_start = _parse_iso_date(week_start_date, "invalid_week_start_date")
        if parsed_week_start is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_week_start_date",
            )
        view = service.get_client_weekly_metrics(
            client_user_id=current_user.id,
            week_start_date=parsed_week_start,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise _translate_service_error(exc) from exc

    return _weekly_to_response(view)


@router.get("/history", response_model=MetricsHistoryResponse)
def get_metrics_history(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
    as_of_date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
) -> MetricsHistoryResponse:
    session = _require_db(db)
    service = MetricsService(session)
    try:
        view = service.get_client_metrics_history(
            client_user_id=current_user.id,
            weeks=weeks,
            as_of_date=_parse_iso_date(as_of_date, "invalid_date"),
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise _translate_service_error(exc) from exc

    items = [_weekly_to_response(item) for item in view.weeks]
    latest_week = items[0] if items else None
    return MetricsHistoryResponse(
        client_user_id=view.client_user_id,
        as_of_date=view.as_of_date,
        week_start_date=(latest_week.week_start_date if latest_week is not None else None),
        week_end_date=latest_week.week_end_date if latest_week is not None else None,
        business_timezone=view.business_timezone,
        week_start_day=view.week_start_day,
        total_intake_calories=(latest_week.total_intake_calories if latest_week is not None else 0),
        total_expenditure_calories=(
            latest_week.total_expenditure_calories if latest_week is not None else 0
        ),
        net_calorie_balance=(latest_week.net_calorie_balance if latest_week is not None else 0),
        weekly_target_deficit_calories=(
            latest_week.weekly_target_deficit_calories if latest_week is not None else None
        ),
        deficit_progress_percent=(
            latest_week.deficit_progress_percent if latest_week is not None else None
        ),
        current_intake_ceiling_calories=(
            latest_week.current_intake_ceiling_calories if latest_week is not None else None
        ),
        current_expenditure_floor_calories=(
            latest_week.current_expenditure_floor_calories if latest_week is not None else None
        ),
        has_data=latest_week.has_data if latest_week is not None else False,
        freshness=(
            latest_week.freshness
            if latest_week is not None
            else MetricsFreshnessResponse(
                source="empty",
                computed_at=None,
                snapshot_generated_at=None,
                source_window_start=None,
                source_window_end=None,
                version=None,
            )
        ),
        weeks=items,
        count=len(items),
    )
