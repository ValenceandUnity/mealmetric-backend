import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class MetricsFreshnessResponse(BaseModel):
    source: str
    computed_at: datetime | None
    snapshot_generated_at: datetime | None
    source_window_start: datetime | None
    source_window_end: datetime | None
    version: int | None


class WeeklyMetricsResponse(BaseModel):
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
    freshness: MetricsFreshnessResponse


class OverviewMetricsResponse(BaseModel):
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
    freshness: MetricsFreshnessResponse


class MetricsHistoryResponse(BaseModel):
    client_user_id: uuid.UUID
    as_of_date: date
    week_start_date: date | None
    week_end_date: date | None
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
    freshness: MetricsFreshnessResponse
    weeks: list[WeeklyMetricsResponse]
    count: int


class PTComparisonMetricsItemResponse(BaseModel):
    client_user_id: uuid.UUID
    total_intake_calories: int
    total_expenditure_calories: int
    net_calorie_balance: int
    weekly_target_deficit_calories: int | None
    deficit_progress_percent: Decimal | None
    has_data: bool
    freshness: MetricsFreshnessResponse


class PTComparisonMetricsResponse(BaseModel):
    week_start_date: date
    week_end_date: date
    business_timezone: str
    week_start_day: int
    items: list[PTComparisonMetricsItemResponse]
    count: int
