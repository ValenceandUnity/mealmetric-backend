import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory
from mealmetric.models.metrics import (
    ActivityExpenditureRecord,
    CalorieIntakeRecord,
    ClientMetricSnapshot,
    DeficitTarget,
    DeficitTargetStatus,
    StrengthMetricRollup,
    WeeklyMetricRollup,
)
from mealmetric.models.training import PtClientLink, PtClientLinkStatus
from mealmetric.repos import audit_log_repo


def list_calorie_intake_records(
    session: Session,
    client_user_id: uuid.UUID,
    *,
    recorded_from: datetime | None = None,
    recorded_to: datetime | None = None,
    business_date_from: date | None = None,
    business_date_to: date | None = None,
    limit: int | None = None,
) -> list[CalorieIntakeRecord]:
    stmt: Select[tuple[CalorieIntakeRecord]] = select(CalorieIntakeRecord).where(
        CalorieIntakeRecord.client_user_id == client_user_id
    )
    if recorded_from is not None:
        stmt = stmt.where(CalorieIntakeRecord.recorded_at >= recorded_from)
    if recorded_to is not None:
        stmt = stmt.where(CalorieIntakeRecord.recorded_at <= recorded_to)
    if business_date_from is not None:
        stmt = stmt.where(CalorieIntakeRecord.business_date >= business_date_from)
    if business_date_to is not None:
        stmt = stmt.where(CalorieIntakeRecord.business_date <= business_date_to)

    stmt = stmt.order_by(CalorieIntakeRecord.recorded_at.asc(), CalorieIntakeRecord.id.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def list_activity_expenditure_records(
    session: Session,
    client_user_id: uuid.UUID,
    *,
    recorded_from: datetime | None = None,
    recorded_to: datetime | None = None,
    business_date_from: date | None = None,
    business_date_to: date | None = None,
    limit: int | None = None,
) -> list[ActivityExpenditureRecord]:
    stmt: Select[tuple[ActivityExpenditureRecord]] = select(ActivityExpenditureRecord).where(
        ActivityExpenditureRecord.client_user_id == client_user_id
    )
    if recorded_from is not None:
        stmt = stmt.where(ActivityExpenditureRecord.recorded_at >= recorded_from)
    if recorded_to is not None:
        stmt = stmt.where(ActivityExpenditureRecord.recorded_at <= recorded_to)
    if business_date_from is not None:
        stmt = stmt.where(ActivityExpenditureRecord.business_date >= business_date_from)
    if business_date_to is not None:
        stmt = stmt.where(ActivityExpenditureRecord.business_date <= business_date_to)

    stmt = stmt.order_by(
        ActivityExpenditureRecord.recorded_at.asc(), ActivityExpenditureRecord.id.asc()
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def get_active_deficit_target_for_client_on_date(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    as_of_date: date,
) -> DeficitTarget | None:
    # Deterministic ambiguity handling for overlapping active windows:
    # prefer latest effective_from_date, then latest created_at, then highest id.
    stmt: Select[tuple[DeficitTarget]] = (
        select(DeficitTarget)
        .where(
            DeficitTarget.client_user_id == client_user_id,
            DeficitTarget.status == DeficitTargetStatus.ACTIVE,
            DeficitTarget.effective_from_date <= as_of_date,
            or_(
                DeficitTarget.effective_to_date.is_(None),
                DeficitTarget.effective_to_date >= as_of_date,
            ),
        )
        .order_by(
            DeficitTarget.effective_from_date.desc(),
            DeficitTarget.created_at.desc(),
            DeficitTarget.id.desc(),
        )
        .limit(1)
    )
    return session.scalar(stmt)


def get_weekly_metric_rollup(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    week_start_date: date,
) -> WeeklyMetricRollup | None:
    stmt: Select[tuple[WeeklyMetricRollup]] = select(WeeklyMetricRollup).where(
        WeeklyMetricRollup.client_user_id == client_user_id,
        WeeklyMetricRollup.week_start_date == week_start_date,
    )
    return session.scalar(stmt)


def list_weekly_metric_rollups(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    week_start_from: date | None = None,
    week_start_to: date | None = None,
    limit: int | None = None,
) -> list[WeeklyMetricRollup]:
    stmt: Select[tuple[WeeklyMetricRollup]] = select(WeeklyMetricRollup).where(
        WeeklyMetricRollup.client_user_id == client_user_id
    )
    if week_start_from is not None:
        stmt = stmt.where(WeeklyMetricRollup.week_start_date >= week_start_from)
    if week_start_to is not None:
        stmt = stmt.where(WeeklyMetricRollup.week_start_date <= week_start_to)

    stmt = stmt.order_by(WeeklyMetricRollup.week_start_date.desc(), WeeklyMetricRollup.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def upsert_weekly_metric_rollup(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    week_start_date: date,
    total_intake_calories: int,
    total_expenditure_calories: int,
    net_calorie_balance: int,
    target_deficit_calories: int | None,
    deficit_progress_percent: Decimal | None,
    computed_at: datetime,
    source_window_start: datetime,
    source_window_end: datetime,
    version: int = 1,
    week_start_day: int = 1,
    business_timezone: str = "America/New_York",
) -> WeeklyMetricRollup:
    existing = get_weekly_metric_rollup(
        session,
        client_user_id=client_user_id,
        week_start_date=week_start_date,
    )
    if existing is None:
        rollup = WeeklyMetricRollup(
            client_user_id=client_user_id,
            week_start_date=week_start_date,
            week_start_day=week_start_day,
            business_timezone=business_timezone,
            total_intake_calories=total_intake_calories,
            total_expenditure_calories=total_expenditure_calories,
            net_calorie_balance=net_calorie_balance,
            target_deficit_calories=target_deficit_calories,
            deficit_progress_percent=deficit_progress_percent,
            computed_at=computed_at,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
            version=version,
        )
        session.add(rollup)
        session.flush()
        audit_log_repo.append_event(
            session,
            category=AuditEventCategory.METRICS,
            action=AuditEventAction.METRICS_WEEKLY_ROLLUP_UPSERTED,
            target_entity_type="weekly_metric_rollup",
            target_entity_id=rollup.id,
            related_entity_type="client_user",
            related_entity_id=client_user_id,
            metadata={
                "operation": "insert",
                "client_user_id": client_user_id,
                "week_start_date": week_start_date,
                "net_calorie_balance": net_calorie_balance,
                "target_deficit_calories": target_deficit_calories,
                "version": version,
                "business_timezone": business_timezone,
                "week_start_day": week_start_day,
                "source_window_start": source_window_start,
                "source_window_end": source_window_end,
            },
            message="Weekly metric rollup upserted",
        )
        return rollup

    existing.week_start_day = week_start_day
    existing.business_timezone = business_timezone
    existing.total_intake_calories = total_intake_calories
    existing.total_expenditure_calories = total_expenditure_calories
    existing.net_calorie_balance = net_calorie_balance
    existing.target_deficit_calories = target_deficit_calories
    existing.deficit_progress_percent = deficit_progress_percent
    existing.computed_at = computed_at
    existing.source_window_start = source_window_start
    existing.source_window_end = source_window_end
    existing.version = version
    session.add(existing)
    session.flush()
    audit_log_repo.append_event(
        session,
        category=AuditEventCategory.METRICS,
        action=AuditEventAction.METRICS_WEEKLY_ROLLUP_UPSERTED,
        target_entity_type="weekly_metric_rollup",
        target_entity_id=existing.id,
        related_entity_type="client_user",
        related_entity_id=client_user_id,
        metadata={
            "operation": "update",
            "client_user_id": client_user_id,
            "week_start_date": week_start_date,
            "net_calorie_balance": net_calorie_balance,
            "target_deficit_calories": target_deficit_calories,
            "version": version,
            "business_timezone": business_timezone,
            "week_start_day": week_start_day,
            "source_window_start": source_window_start,
            "source_window_end": source_window_end,
        },
        message="Weekly metric rollup upserted",
    )
    return existing


def get_strength_metric_rollup(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    week_start_date: date,
) -> StrengthMetricRollup | None:
    stmt: Select[tuple[StrengthMetricRollup]] = select(StrengthMetricRollup).where(
        StrengthMetricRollup.client_user_id == client_user_id,
        StrengthMetricRollup.week_start_date == week_start_date,
    )
    return session.scalar(stmt)


def list_strength_metric_rollups(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    week_start_from: date | None = None,
    week_start_to: date | None = None,
    limit: int | None = None,
) -> list[StrengthMetricRollup]:
    stmt: Select[tuple[StrengthMetricRollup]] = select(StrengthMetricRollup).where(
        StrengthMetricRollup.client_user_id == client_user_id
    )
    if week_start_from is not None:
        stmt = stmt.where(StrengthMetricRollup.week_start_date >= week_start_from)
    if week_start_to is not None:
        stmt = stmt.where(StrengthMetricRollup.week_start_date <= week_start_to)

    stmt = stmt.order_by(
        StrengthMetricRollup.week_start_date.desc(), StrengthMetricRollup.id.desc()
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def upsert_strength_metric_rollup(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    week_start_date: date,
    total_workouts: int,
    completed_workouts: int,
    training_minutes: int,
    volume_score: Decimal | None,
    computed_at: datetime,
    source_window_start: datetime,
    source_window_end: datetime,
    version: int = 1,
    week_start_day: int = 1,
    business_timezone: str = "America/New_York",
) -> StrengthMetricRollup:
    existing = get_strength_metric_rollup(
        session,
        client_user_id=client_user_id,
        week_start_date=week_start_date,
    )
    if existing is None:
        rollup = StrengthMetricRollup(
            client_user_id=client_user_id,
            week_start_date=week_start_date,
            week_start_day=week_start_day,
            business_timezone=business_timezone,
            total_workouts=total_workouts,
            completed_workouts=completed_workouts,
            training_minutes=training_minutes,
            volume_score=volume_score,
            computed_at=computed_at,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
            version=version,
        )
        session.add(rollup)
        session.flush()
        audit_log_repo.append_event(
            session,
            category=AuditEventCategory.METRICS,
            action=AuditEventAction.METRICS_STRENGTH_ROLLUP_UPSERTED,
            target_entity_type="strength_metric_rollup",
            target_entity_id=rollup.id,
            related_entity_type="client_user",
            related_entity_id=client_user_id,
            metadata={
                "operation": "insert",
                "client_user_id": client_user_id,
                "week_start_date": week_start_date,
                "total_workouts": total_workouts,
                "completed_workouts": completed_workouts,
                "training_minutes": training_minutes,
                "volume_score": volume_score,
                "version": version,
                "business_timezone": business_timezone,
                "week_start_day": week_start_day,
                "source_window_start": source_window_start,
                "source_window_end": source_window_end,
            },
            message="Strength metric rollup upserted",
        )
        return rollup

    existing.week_start_day = week_start_day
    existing.business_timezone = business_timezone
    existing.total_workouts = total_workouts
    existing.completed_workouts = completed_workouts
    existing.training_minutes = training_minutes
    existing.volume_score = volume_score
    existing.computed_at = computed_at
    existing.source_window_start = source_window_start
    existing.source_window_end = source_window_end
    existing.version = version
    session.add(existing)
    session.flush()
    audit_log_repo.append_event(
        session,
        category=AuditEventCategory.METRICS,
        action=AuditEventAction.METRICS_STRENGTH_ROLLUP_UPSERTED,
        target_entity_type="strength_metric_rollup",
        target_entity_id=existing.id,
        related_entity_type="client_user",
        related_entity_id=client_user_id,
        metadata={
            "operation": "update",
            "client_user_id": client_user_id,
            "week_start_date": week_start_date,
            "total_workouts": total_workouts,
            "completed_workouts": completed_workouts,
            "training_minutes": training_minutes,
            "volume_score": volume_score,
            "version": version,
            "business_timezone": business_timezone,
            "week_start_day": week_start_day,
            "source_window_start": source_window_start,
            "source_window_end": source_window_end,
        },
        message="Strength metric rollup upserted",
    )
    return existing


def get_client_metric_snapshot(
    session: Session,
    *,
    client_user_id: uuid.UUID,
) -> ClientMetricSnapshot | None:
    stmt: Select[tuple[ClientMetricSnapshot]] = select(ClientMetricSnapshot).where(
        ClientMetricSnapshot.client_user_id == client_user_id
    )
    return session.scalar(stmt)


def upsert_client_metric_snapshot(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    source_window_start: datetime,
    source_window_end: datetime,
    snapshot_generated_at: datetime,
    latest_week_start_date: date | None = None,
    current_intake_ceiling_calories: int | None = None,
    current_expenditure_floor_calories: int | None = None,
    current_target_deficit_calories: int | None = None,
    current_week_intake_calories: int | None = None,
    current_week_expenditure_calories: int | None = None,
    current_week_net_balance: int | None = None,
    current_deficit_progress_percent: Decimal | None = None,
    rollup_computed_at: datetime | None = None,
    version: int = 1,
    week_start_day: int = 1,
    business_timezone: str = "America/New_York",
) -> ClientMetricSnapshot:
    existing = get_client_metric_snapshot(session, client_user_id=client_user_id)
    if existing is None:
        snapshot = ClientMetricSnapshot(
            client_user_id=client_user_id,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
            snapshot_generated_at=snapshot_generated_at,
            latest_week_start_date=latest_week_start_date,
            current_intake_ceiling_calories=current_intake_ceiling_calories,
            current_expenditure_floor_calories=current_expenditure_floor_calories,
            current_target_deficit_calories=current_target_deficit_calories,
            current_week_intake_calories=current_week_intake_calories,
            current_week_expenditure_calories=current_week_expenditure_calories,
            current_week_net_balance=current_week_net_balance,
            current_deficit_progress_percent=current_deficit_progress_percent,
            rollup_computed_at=rollup_computed_at,
            version=version,
            week_start_day=week_start_day,
            business_timezone=business_timezone,
        )
        session.add(snapshot)
        session.flush()
        audit_log_repo.append_event(
            session,
            category=AuditEventCategory.METRICS,
            action=AuditEventAction.METRICS_CLIENT_SNAPSHOT_UPSERTED,
            target_entity_type="client_metric_snapshot",
            target_entity_id=snapshot.id,
            related_entity_type="client_user",
            related_entity_id=client_user_id,
            metadata={
                "operation": "insert",
                "client_user_id": client_user_id,
                "latest_week_start_date": latest_week_start_date,
                "current_intake_ceiling_calories": current_intake_ceiling_calories,
                "current_expenditure_floor_calories": current_expenditure_floor_calories,
                "current_target_deficit_calories": current_target_deficit_calories,
                "current_week_net_balance": current_week_net_balance,
                "current_deficit_progress_percent": current_deficit_progress_percent,
                "version": version,
                "business_timezone": business_timezone,
                "week_start_day": week_start_day,
                "source_window_start": source_window_start,
                "source_window_end": source_window_end,
                "snapshot_generated_at": snapshot_generated_at,
            },
            message="Client metric snapshot upserted",
        )
        return snapshot

    existing.source_window_start = source_window_start
    existing.source_window_end = source_window_end
    existing.snapshot_generated_at = snapshot_generated_at
    existing.latest_week_start_date = latest_week_start_date
    existing.current_intake_ceiling_calories = current_intake_ceiling_calories
    existing.current_expenditure_floor_calories = current_expenditure_floor_calories
    existing.current_target_deficit_calories = current_target_deficit_calories
    existing.current_week_intake_calories = current_week_intake_calories
    existing.current_week_expenditure_calories = current_week_expenditure_calories
    existing.current_week_net_balance = current_week_net_balance
    existing.current_deficit_progress_percent = current_deficit_progress_percent
    existing.rollup_computed_at = rollup_computed_at
    existing.version = version
    existing.week_start_day = week_start_day
    existing.business_timezone = business_timezone
    session.add(existing)
    session.flush()
    audit_log_repo.append_event(
        session,
        category=AuditEventCategory.METRICS,
        action=AuditEventAction.METRICS_CLIENT_SNAPSHOT_UPSERTED,
        target_entity_type="client_metric_snapshot",
        target_entity_id=existing.id,
        related_entity_type="client_user",
        related_entity_id=client_user_id,
        metadata={
            "operation": "update",
            "client_user_id": client_user_id,
            "latest_week_start_date": latest_week_start_date,
            "current_intake_ceiling_calories": current_intake_ceiling_calories,
            "current_expenditure_floor_calories": current_expenditure_floor_calories,
            "current_target_deficit_calories": current_target_deficit_calories,
            "current_week_net_balance": current_week_net_balance,
            "current_deficit_progress_percent": current_deficit_progress_percent,
            "version": version,
            "business_timezone": business_timezone,
            "week_start_day": week_start_day,
            "source_window_start": source_window_start,
            "source_window_end": source_window_end,
            "snapshot_generated_at": snapshot_generated_at,
        },
        message="Client metric snapshot upserted",
    )
    return existing


def get_active_pt_client_link(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> PtClientLink | None:
    stmt: Select[tuple[PtClientLink]] = select(PtClientLink).where(
        PtClientLink.pt_user_id == pt_user_id,
        PtClientLink.client_user_id == client_user_id,
        PtClientLink.status == PtClientLinkStatus.ACTIVE,
    )
    return session.scalar(stmt)


def list_active_client_ids_for_pt(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    stmt: Select[tuple[uuid.UUID]] = (
        select(PtClientLink.client_user_id)
        .where(
            PtClientLink.pt_user_id == pt_user_id,
            PtClientLink.status == PtClientLinkStatus.ACTIVE,
        )
        .order_by(PtClientLink.client_user_id.asc())
    )
    return list(session.scalars(stmt))


def list_active_pt_user_ids_for_client(
    session: Session,
    *,
    client_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    stmt: Select[tuple[uuid.UUID]] = (
        select(PtClientLink.pt_user_id)
        .where(
            PtClientLink.client_user_id == client_user_id,
            PtClientLink.status == PtClientLinkStatus.ACTIVE,
        )
        .order_by(PtClientLink.pt_user_id.asc())
    )
    return list(session.scalars(stmt))


def list_active_links_for_pt(
    session: Session,
    *,
    pt_user_id: uuid.UUID,
) -> list[PtClientLink]:
    stmt: Select[tuple[PtClientLink]] = (
        select(PtClientLink)
        .where(
            PtClientLink.pt_user_id == pt_user_id,
            PtClientLink.status == PtClientLinkStatus.ACTIVE,
        )
        .order_by(PtClientLink.client_user_id.asc(), PtClientLink.id.asc())
    )
    return list(session.scalars(stmt))


def list_active_links_for_client(
    session: Session,
    *,
    client_user_id: uuid.UUID,
) -> list[PtClientLink]:
    stmt: Select[tuple[PtClientLink]] = (
        select(PtClientLink)
        .where(
            PtClientLink.client_user_id == client_user_id,
            PtClientLink.status == PtClientLinkStatus.ACTIVE,
        )
        .order_by(PtClientLink.pt_user_id.asc(), PtClientLink.id.asc())
    )
    return list(session.scalars(stmt))


def list_active_calorie_intake_records_for_clients(
    session: Session,
    *,
    client_user_ids: Sequence[uuid.UUID],
    business_date_from: date | None = None,
    business_date_to: date | None = None,
) -> list[CalorieIntakeRecord]:
    if not client_user_ids:
        return []
    stmt: Select[tuple[CalorieIntakeRecord]] = select(CalorieIntakeRecord).where(
        CalorieIntakeRecord.client_user_id.in_(tuple(client_user_ids))
    )
    if business_date_from is not None:
        stmt = stmt.where(CalorieIntakeRecord.business_date >= business_date_from)
    if business_date_to is not None:
        stmt = stmt.where(CalorieIntakeRecord.business_date <= business_date_to)

    stmt = stmt.order_by(
        CalorieIntakeRecord.client_user_id.asc(),
        CalorieIntakeRecord.business_date.asc(),
        CalorieIntakeRecord.id.asc(),
    )
    return list(session.scalars(stmt))


def list_active_activity_expenditure_records_for_clients(
    session: Session,
    *,
    client_user_ids: Sequence[uuid.UUID],
    business_date_from: date | None = None,
    business_date_to: date | None = None,
) -> list[ActivityExpenditureRecord]:
    if not client_user_ids:
        return []
    stmt: Select[tuple[ActivityExpenditureRecord]] = select(ActivityExpenditureRecord).where(
        ActivityExpenditureRecord.client_user_id.in_(tuple(client_user_ids))
    )
    if business_date_from is not None:
        stmt = stmt.where(ActivityExpenditureRecord.business_date >= business_date_from)
    if business_date_to is not None:
        stmt = stmt.where(ActivityExpenditureRecord.business_date <= business_date_to)

    stmt = stmt.order_by(
        ActivityExpenditureRecord.client_user_id.asc(),
        ActivityExpenditureRecord.business_date.asc(),
        ActivityExpenditureRecord.id.asc(),
    )
    return list(session.scalars(stmt))
