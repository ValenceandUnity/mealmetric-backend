import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from mealmetric.models.metrics import (
    ActivityExpenditureRecord,
    CalorieIntakeRecord,
    ClientMetricSnapshot,
    WeeklyMetricRollup,
)
from mealmetric.repos import metrics_repo

_BUSINESS_TZ = ZoneInfo("America/New_York")
_BUSINESS_TZ_NAME = "America/New_York"
_WEEK_START_DAY = 1
_DAYS_PER_WEEK = 7


class MetricsServiceError(Exception):
    """Base metrics-domain service error."""


class MetricsPermissionError(MetricsServiceError):
    """Raised when PT access is outside active link scope."""


@dataclass(frozen=True, slots=True)
class MetricsFreshness:
    source: str
    computed_at: datetime | None
    snapshot_generated_at: datetime | None
    source_window_start: datetime | None
    source_window_end: datetime | None
    version: int | None


@dataclass(frozen=True, slots=True)
class WeeklyMetricsView:
    client_user_id: uuid.UUID
    as_of_date: date
    week_start_date: date
    week_end_date: date
    business_timezone: str
    week_start_day: int
    total_intake_calories: int
    total_expenditure_calories: int
    net_calorie_balance: int
    weekly_target_deficit_calories: int | None
    deficit_progress_percent: Decimal | None
    current_intake_ceiling_calories: int | None
    current_expenditure_floor_calories: int | None
    has_data: bool
    freshness: MetricsFreshness


@dataclass(frozen=True, slots=True)
class OverviewMetricsView:
    client_user_id: uuid.UUID
    as_of_date: date
    week_start_date: date
    week_end_date: date
    business_timezone: str
    week_start_day: int
    total_intake_calories: int
    total_expenditure_calories: int
    net_calorie_balance: int
    weekly_target_deficit_calories: int | None
    deficit_progress_percent: Decimal | None
    current_intake_ceiling_calories: int | None
    current_expenditure_floor_calories: int | None
    has_data: bool
    freshness: MetricsFreshness


@dataclass(frozen=True, slots=True)
class MetricsHistoryView:
    client_user_id: uuid.UUID
    as_of_date: date
    business_timezone: str
    week_start_day: int
    weeks: tuple[WeeklyMetricsView, ...]


@dataclass(frozen=True, slots=True)
class PTComparisonMetricsItemView:
    client_user_id: uuid.UUID
    total_intake_calories: int
    total_expenditure_calories: int
    net_calorie_balance: int
    weekly_target_deficit_calories: int | None
    deficit_progress_percent: Decimal | None
    has_data: bool
    freshness: MetricsFreshness


@dataclass(frozen=True, slots=True)
class PTComparisonMetricsView:
    week_start_date: date
    week_end_date: date
    business_timezone: str
    week_start_day: int
    items: tuple[PTComparisonMetricsItemView, ...]


class MetricsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_client_overview(
        self,
        *,
        client_user_id: uuid.UUID,
        as_of_date: date | None = None,
    ) -> OverviewMetricsView:
        business_date = as_of_date or self._business_today()
        weekly_view = self._compose_weekly_view(
            client_user_id=client_user_id,
            week_start_date=self._week_start_for_date(business_date),
        )
        snapshot = metrics_repo.get_client_metric_snapshot(
            self._session, client_user_id=client_user_id
        )
        return OverviewMetricsView(
            client_user_id=client_user_id,
            as_of_date=business_date,
            week_start_date=weekly_view.week_start_date,
            week_end_date=weekly_view.week_end_date,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            total_intake_calories=weekly_view.total_intake_calories,
            total_expenditure_calories=weekly_view.total_expenditure_calories,
            net_calorie_balance=weekly_view.net_calorie_balance,
            weekly_target_deficit_calories=weekly_view.weekly_target_deficit_calories,
            deficit_progress_percent=weekly_view.deficit_progress_percent,
            current_intake_ceiling_calories=(
                snapshot.current_intake_ceiling_calories if snapshot is not None else None
            ),
            current_expenditure_floor_calories=(
                snapshot.current_expenditure_floor_calories if snapshot is not None else None
            ),
            has_data=weekly_view.has_data,
            freshness=weekly_view.freshness,
        )

    def get_client_weekly_metrics(
        self,
        *,
        client_user_id: uuid.UUID,
        week_start_date: date,
    ) -> WeeklyMetricsView:
        return self._compose_weekly_view(
            client_user_id=client_user_id,
            week_start_date=week_start_date,
        )

    def get_client_metrics_history(
        self,
        *,
        client_user_id: uuid.UUID,
        weeks: int,
        as_of_date: date | None = None,
    ) -> MetricsHistoryView:
        if weeks <= 0:
            return MetricsHistoryView(
                client_user_id=client_user_id,
                as_of_date=as_of_date or self._business_today(),
                business_timezone=_BUSINESS_TZ_NAME,
                week_start_day=_WEEK_START_DAY,
                weeks=(),
            )

        business_date = as_of_date or self._business_today()
        end_week_start = self._week_start_for_date(business_date)

        views: list[WeeklyMetricsView] = []
        for offset in range(weeks):
            week_start = end_week_start - timedelta(days=7 * offset)
            views.append(
                self._compose_weekly_view(
                    client_user_id=client_user_id,
                    week_start_date=week_start,
                )
            )

        return MetricsHistoryView(
            client_user_id=client_user_id,
            as_of_date=business_date,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            weeks=tuple(views),
        )

    def get_pt_client_overview(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        as_of_date: date | None = None,
    ) -> OverviewMetricsView:
        self._require_active_pt_client_link(pt_user_id=pt_user_id, client_user_id=client_user_id)
        return self.get_client_overview(client_user_id=client_user_id, as_of_date=as_of_date)

    def get_pt_client_weekly_metrics(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        week_start_date: date,
    ) -> WeeklyMetricsView:
        self._require_active_pt_client_link(pt_user_id=pt_user_id, client_user_id=client_user_id)
        return self.get_client_weekly_metrics(
            client_user_id=client_user_id,
            week_start_date=week_start_date,
        )

    def get_pt_client_metrics_history(
        self,
        *,
        pt_user_id: uuid.UUID,
        client_user_id: uuid.UUID,
        weeks: int,
        as_of_date: date | None = None,
    ) -> MetricsHistoryView:
        self._require_active_pt_client_link(pt_user_id=pt_user_id, client_user_id=client_user_id)
        return self.get_client_metrics_history(
            client_user_id=client_user_id,
            weeks=weeks,
            as_of_date=as_of_date,
        )

    def get_pt_metrics_comparison(
        self,
        *,
        pt_user_id: uuid.UUID,
        week_start_date: date | None = None,
        as_of_date: date | None = None,
        client_user_ids: Sequence[uuid.UUID] | None = None,
    ) -> PTComparisonMetricsView:
        if week_start_date is not None and as_of_date is not None:
            raise MetricsServiceError("conflicting_date_filters")

        if week_start_date is not None:
            comparison_week_start = self._week_start_for_date(week_start_date)
        else:
            business_date = as_of_date or self._business_today()
            comparison_week_start = self._week_start_for_date(business_date)

        comparison_week_end = comparison_week_start + timedelta(days=6)

        active_linked_client_ids = metrics_repo.list_active_client_ids_for_pt(
            self._session,
            pt_user_id=pt_user_id,
        )
        active_client_set = set(active_linked_client_ids)

        selected_client_ids: list[uuid.UUID]
        if client_user_ids is None:
            selected_client_ids = sorted(active_linked_client_ids)
        else:
            requested = sorted(set(client_user_ids))
            if any(client_id not in active_client_set for client_id in requested):
                raise MetricsPermissionError("pt_client_link_not_active")
            selected_client_ids = requested

        items = [
            self._to_comparison_item(
                self._compose_weekly_view(
                    client_user_id=client_id,
                    week_start_date=comparison_week_start,
                )
            )
            for client_id in selected_client_ids
        ]

        return PTComparisonMetricsView(
            week_start_date=comparison_week_start,
            week_end_date=comparison_week_end,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            items=tuple(items),
        )

    def _require_active_pt_client_link(
        self, *, pt_user_id: uuid.UUID, client_user_id: uuid.UUID
    ) -> None:
        link = metrics_repo.get_active_pt_client_link(
            self._session,
            pt_user_id=pt_user_id,
            client_user_id=client_user_id,
        )
        if link is None:
            raise MetricsPermissionError("pt_client_link_not_active")

    def _compose_weekly_view(
        self,
        *,
        client_user_id: uuid.UUID,
        week_start_date: date,
    ) -> WeeklyMetricsView:
        week_start = self._week_start_for_date(week_start_date)
        week_end = week_start + timedelta(days=6)

        raw_intake = metrics_repo.list_calorie_intake_records(
            self._session,
            client_user_id,
            business_date_from=week_start,
            business_date_to=week_end,
        )
        raw_activity = metrics_repo.list_activity_expenditure_records(
            self._session,
            client_user_id,
            business_date_from=week_start,
            business_date_to=week_end,
        )
        rollup = metrics_repo.get_weekly_metric_rollup(
            self._session,
            client_user_id=client_user_id,
            week_start_date=week_start,
        )
        snapshot = metrics_repo.get_client_metric_snapshot(
            self._session, client_user_id=client_user_id
        )

        has_raw = bool(raw_intake) or bool(raw_activity)

        if has_raw:
            return self._compose_from_raw(
                client_user_id=client_user_id,
                week_start=week_start,
                week_end=week_end,
                raw_intake=raw_intake,
                raw_activity=raw_activity,
                snapshot=snapshot,
            )

        if rollup is not None:
            return self._compose_from_rollup(
                client_user_id=client_user_id,
                week_start=week_start,
                week_end=week_end,
                rollup=rollup,
                snapshot=snapshot,
            )

        if snapshot is not None and snapshot.latest_week_start_date == week_start:
            return self._compose_from_snapshot(
                client_user_id=client_user_id,
                week_start=week_start,
                week_end=week_end,
                snapshot=snapshot,
            )

        weekly_target = self._weekly_target_for_client(
            client_user_id=client_user_id,
            as_of_date=week_end,
        )

        return WeeklyMetricsView(
            client_user_id=client_user_id,
            as_of_date=week_end,
            week_start_date=week_start,
            week_end_date=week_end,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            total_intake_calories=0,
            total_expenditure_calories=0,
            net_calorie_balance=0,
            weekly_target_deficit_calories=weekly_target,
            deficit_progress_percent=None,
            current_intake_ceiling_calories=(
                snapshot.current_intake_ceiling_calories if snapshot is not None else None
            ),
            current_expenditure_floor_calories=(
                snapshot.current_expenditure_floor_calories if snapshot is not None else None
            ),
            has_data=False,
            freshness=MetricsFreshness(
                source="empty",
                computed_at=None,
                snapshot_generated_at=(
                    snapshot.snapshot_generated_at if snapshot is not None else None
                ),
                source_window_start=None,
                source_window_end=None,
                version=None,
            ),
        )

    def _compose_from_raw(
        self,
        *,
        client_user_id: uuid.UUID,
        week_start: date,
        week_end: date,
        raw_intake: list[CalorieIntakeRecord],
        raw_activity: list[ActivityExpenditureRecord],
        snapshot: ClientMetricSnapshot | None,
    ) -> WeeklyMetricsView:
        total_intake = sum(item.calories for item in raw_intake)
        total_expenditure = sum(item.expenditure_calories for item in raw_activity)
        net_balance = total_intake - total_expenditure

        weekly_target = self._weekly_target_for_client(
            client_user_id=client_user_id,
            as_of_date=week_end,
        )
        progress = self.calculate_deficit_progress(
            weekly_target_deficit_calories=weekly_target,
            net_calorie_balance=net_balance,
        )

        computed_at_candidates = [item.ingested_at for item in raw_intake] + [
            item.ingested_at for item in raw_activity
        ]
        computed_at = max(computed_at_candidates) if computed_at_candidates else None

        source_time_candidates = [item.recorded_at for item in raw_intake] + [
            item.recorded_at for item in raw_activity
        ]

        return WeeklyMetricsView(
            client_user_id=client_user_id,
            as_of_date=week_end,
            week_start_date=week_start,
            week_end_date=week_end,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            total_intake_calories=total_intake,
            total_expenditure_calories=total_expenditure,
            net_calorie_balance=net_balance,
            weekly_target_deficit_calories=weekly_target,
            deficit_progress_percent=progress,
            current_intake_ceiling_calories=(
                snapshot.current_intake_ceiling_calories if snapshot is not None else None
            ),
            current_expenditure_floor_calories=(
                snapshot.current_expenditure_floor_calories if snapshot is not None else None
            ),
            has_data=True,
            freshness=MetricsFreshness(
                source="raw",
                computed_at=computed_at,
                snapshot_generated_at=(
                    snapshot.snapshot_generated_at if snapshot is not None else None
                ),
                source_window_start=(
                    min(source_time_candidates) if source_time_candidates else None
                ),
                source_window_end=(max(source_time_candidates) if source_time_candidates else None),
                version=None,
            ),
        )

    def _compose_from_rollup(
        self,
        *,
        client_user_id: uuid.UUID,
        week_start: date,
        week_end: date,
        rollup: WeeklyMetricRollup,
        snapshot: ClientMetricSnapshot | None,
    ) -> WeeklyMetricsView:
        weekly_target = rollup.target_deficit_calories
        if weekly_target is None:
            weekly_target = self._weekly_target_for_client(
                client_user_id=client_user_id,
                as_of_date=week_end,
            )

        progress = rollup.deficit_progress_percent
        if progress is None:
            progress = self.calculate_deficit_progress(
                weekly_target_deficit_calories=weekly_target,
                net_calorie_balance=rollup.net_calorie_balance,
            )

        return WeeklyMetricsView(
            client_user_id=client_user_id,
            as_of_date=week_end,
            week_start_date=week_start,
            week_end_date=week_end,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            total_intake_calories=rollup.total_intake_calories,
            total_expenditure_calories=rollup.total_expenditure_calories,
            net_calorie_balance=rollup.net_calorie_balance,
            weekly_target_deficit_calories=weekly_target,
            deficit_progress_percent=progress,
            current_intake_ceiling_calories=(
                snapshot.current_intake_ceiling_calories if snapshot is not None else None
            ),
            current_expenditure_floor_calories=(
                snapshot.current_expenditure_floor_calories if snapshot is not None else None
            ),
            has_data=True,
            freshness=MetricsFreshness(
                source="weekly_rollup",
                computed_at=rollup.computed_at,
                snapshot_generated_at=(
                    snapshot.snapshot_generated_at if snapshot is not None else None
                ),
                source_window_start=rollup.source_window_start,
                source_window_end=rollup.source_window_end,
                version=rollup.version,
            ),
        )

    def _compose_from_snapshot(
        self,
        *,
        client_user_id: uuid.UUID,
        week_start: date,
        week_end: date,
        snapshot: ClientMetricSnapshot,
    ) -> WeeklyMetricsView:
        intake = snapshot.current_week_intake_calories or 0
        expenditure = snapshot.current_week_expenditure_calories or 0
        net_balance = snapshot.current_week_net_balance
        if net_balance is None:
            net_balance = intake - expenditure

        weekly_target: int | None
        if snapshot.current_target_deficit_calories is not None:
            weekly_target = snapshot.current_target_deficit_calories * _DAYS_PER_WEEK
        else:
            weekly_target = self._weekly_target_for_client(
                client_user_id=client_user_id,
                as_of_date=week_end,
            )

        progress = snapshot.current_deficit_progress_percent
        if progress is None:
            progress = self.calculate_deficit_progress(
                weekly_target_deficit_calories=weekly_target,
                net_calorie_balance=net_balance,
            )

        return WeeklyMetricsView(
            client_user_id=client_user_id,
            as_of_date=week_end,
            week_start_date=week_start,
            week_end_date=week_end,
            business_timezone=_BUSINESS_TZ_NAME,
            week_start_day=_WEEK_START_DAY,
            total_intake_calories=intake,
            total_expenditure_calories=expenditure,
            net_calorie_balance=net_balance,
            weekly_target_deficit_calories=weekly_target,
            deficit_progress_percent=progress,
            current_intake_ceiling_calories=snapshot.current_intake_ceiling_calories,
            current_expenditure_floor_calories=snapshot.current_expenditure_floor_calories,
            has_data=True,
            freshness=MetricsFreshness(
                source="snapshot",
                computed_at=snapshot.rollup_computed_at,
                snapshot_generated_at=snapshot.snapshot_generated_at,
                source_window_start=snapshot.source_window_start,
                source_window_end=snapshot.source_window_end,
                version=snapshot.version,
            ),
        )

    def _weekly_target_for_client(
        self, *, client_user_id: uuid.UUID, as_of_date: date
    ) -> int | None:
        active_target = metrics_repo.get_active_deficit_target_for_client_on_date(
            self._session,
            client_user_id=client_user_id,
            as_of_date=as_of_date,
        )
        if active_target is None:
            return None
        return active_target.target_daily_deficit_calories * _DAYS_PER_WEEK

    @staticmethod
    def _to_comparison_item(
        weekly_view: WeeklyMetricsView,
    ) -> PTComparisonMetricsItemView:
        return PTComparisonMetricsItemView(
            client_user_id=weekly_view.client_user_id,
            total_intake_calories=weekly_view.total_intake_calories,
            total_expenditure_calories=weekly_view.total_expenditure_calories,
            net_calorie_balance=weekly_view.net_calorie_balance,
            weekly_target_deficit_calories=weekly_view.weekly_target_deficit_calories,
            deficit_progress_percent=weekly_view.deficit_progress_percent,
            has_data=weekly_view.has_data,
            freshness=weekly_view.freshness,
        )

    @staticmethod
    def calculate_deficit_progress(
        *,
        weekly_target_deficit_calories: int | None,
        net_calorie_balance: int,
    ) -> Decimal | None:
        if weekly_target_deficit_calories is None or weekly_target_deficit_calories <= 0:
            return None

        achieved_deficit = Decimal(str(-net_calorie_balance))
        target = Decimal(str(weekly_target_deficit_calories))
        ratio = (achieved_deficit / target) * Decimal("100")

        if ratio < Decimal("0"):
            ratio = Decimal("0")
        if ratio > Decimal("100"):
            ratio = Decimal("100")

        return ratio.quantize(Decimal("0.01"))

    @staticmethod
    def _week_start_for_date(value: date) -> date:
        return value - timedelta(days=value.weekday())

    @staticmethod
    def _business_today() -> date:
        return datetime.now(UTC).astimezone(_BUSINESS_TZ).date()
