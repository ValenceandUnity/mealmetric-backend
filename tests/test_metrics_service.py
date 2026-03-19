from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.metrics import (
    ActivityExpenditureRecord,
    CalorieIntakeRecord,
    ClientMetricSnapshot,
    DeficitTarget,
    DeficitTargetStatus,
    WeeklyMetricRollup,
)
from mealmetric.models.training import PtClientLink, PtClientLinkStatus
from mealmetric.models.user import Role, User
from mealmetric.services.metrics_service import MetricsPermissionError, MetricsService


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _create_user(db: Session, *, role: Role, prefix: str) -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.com", password_hash="hash", role=role)
    db.add(user)
    db.flush()
    return user


def test_weekly_aggregation_and_deficit_progress_from_raw_records() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="raw-agg")
        db.add(
            DeficitTarget(
                client_user_id=client.id,
                target_daily_deficit_calories=500,
                status=DeficitTargetStatus.ACTIVE,
                effective_from_date=date(2026, 3, 1),
            )
        )
        db.add_all(
            [
                CalorieIntakeRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    calories=2100,
                ),
                CalorieIntakeRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 18),
                    calories=1900,
                ),
                ActivityExpenditureRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 17, 18, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    expenditure_calories=2500,
                ),
                ActivityExpenditureRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 18, 18, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 18),
                    expenditure_calories=2300,
                ),
            ]
        )
        db.commit()

        service = MetricsService(db)
        weekly = service.get_client_weekly_metrics(
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
        )

        assert weekly.total_intake_calories == 4000
        assert weekly.total_expenditure_calories == 4800
        assert weekly.net_calorie_balance == -800
        assert weekly.weekly_target_deficit_calories == 3500
        assert weekly.deficit_progress_percent == Decimal("22.86")
        assert weekly.freshness.source == "raw"
        assert weekly.freshness.computed_at is not None
        assert weekly.freshness.version is None


def test_rollup_source_selected_when_raw_absent() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="rollup-source")
        db.add(
            WeeklyMetricRollup(
                client_user_id=client.id,
                week_start_date=date(2026, 3, 16),
                total_intake_calories=1200,
                total_expenditure_calories=800,
                net_calorie_balance=400,
                target_deficit_calories=700,
                deficit_progress_percent=Decimal("0.00"),
                computed_at=datetime(2026, 3, 17, 6, 0, tzinfo=UTC),
                source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
                source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
                version=3,
            )
        )
        db.commit()

        service = MetricsService(db)
        weekly = service.get_client_weekly_metrics(
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
        )

        assert weekly.freshness.source == "weekly_rollup"
        assert weekly.freshness.version == 3
        assert weekly.has_data is True


def test_snapshot_source_selected_when_raw_and_rollup_absent() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="snapshot-source")
        db.add(
            ClientMetricSnapshot(
                client_user_id=client.id,
                latest_week_start_date=date(2026, 3, 16),
                current_week_intake_calories=900,
                current_week_expenditure_calories=600,
                current_week_net_balance=300,
                current_target_deficit_calories=100,
                current_deficit_progress_percent=Decimal("10.00"),
                snapshot_generated_at=datetime(2026, 3, 17, 7, 0, tzinfo=UTC),
                source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
                source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
                version=2,
            )
        )
        db.commit()

        service = MetricsService(db)
        weekly = service.get_client_weekly_metrics(
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
        )

        assert weekly.freshness.source == "snapshot"
        assert weekly.freshness.version == 2
        assert weekly.has_data is True


def test_no_data_case_returns_empty_source() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="empty-source")
        db.commit()

        service = MetricsService(db)
        weekly = service.get_client_weekly_metrics(
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
        )

        assert weekly.freshness.source == "empty"
        assert weekly.freshness.version is None
        assert weekly.has_data is False


def test_business_week_boundary_is_monday_based() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="week-boundary")
        db.add(
            CalorieIntakeRecord(
                client_user_id=client.id,
                recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                business_date=date(2026, 3, 17),
                calories=1200,
            )
        )
        db.commit()

        service = MetricsService(db)
        overview = service.get_client_overview(
            client_user_id=client.id,
            as_of_date=date(2026, 3, 18),
        )

        assert overview.week_start_date == date(2026, 3, 16)
        assert overview.week_end_date == date(2026, 3, 22)


def test_empty_state_is_stable_and_deterministic() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="empty")
        db.commit()

        service = MetricsService(db)
        overview = service.get_client_overview(
            client_user_id=client.id,
            as_of_date=date(2026, 3, 18),
        )

        assert overview.has_data is False
        assert overview.total_intake_calories == 0
        assert overview.total_expenditure_calories == 0
        assert overview.net_calorie_balance == 0
        assert overview.freshness.source == "empty"

        history = service.get_client_metrics_history(
            client_user_id=client.id,
            weeks=3,
            as_of_date=date(2026, 3, 18),
        )
        assert len(history.weeks) == 3
        assert [item.week_start_date for item in history.weeks] == [
            date(2026, 3, 16),
            date(2026, 3, 9),
            date(2026, 3, 2),
        ]
        assert all(not item.has_data for item in history.weeks)


def test_pt_visibility_requires_active_link() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = _create_user(db, role=Role.PT, prefix="pt")
        client = _create_user(db, role=Role.CLIENT, prefix="client")
        db.add(
            PtClientLink(
                pt_user_id=pt.id,
                client_user_id=client.id,
                status=PtClientLinkStatus.PENDING,
            )
        )
        db.commit()

        service = MetricsService(db)

        with pytest.raises(MetricsPermissionError):
            service.get_pt_client_overview(
                pt_user_id=pt.id,
                client_user_id=client.id,
                as_of_date=date(2026, 3, 18),
            )


def test_pt_visibility_allows_active_link() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = _create_user(db, role=Role.PT, prefix="pt-active")
        client = _create_user(db, role=Role.CLIENT, prefix="client-active")
        db.add(
            PtClientLink(
                pt_user_id=pt.id,
                client_user_id=client.id,
                status=PtClientLinkStatus.ACTIVE,
            )
        )
        db.add(
            CalorieIntakeRecord(
                client_user_id=client.id,
                recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                business_date=date(2026, 3, 17),
                calories=1400,
            )
        )
        db.commit()

        service = MetricsService(db)
        overview = service.get_pt_client_overview(
            pt_user_id=pt.id,
            client_user_id=client.id,
            as_of_date=date(2026, 3, 18),
        )

        assert overview.total_intake_calories == 1400


def test_overlapping_active_targets_pick_latest_effective_from() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, prefix="overlap")
        db.add_all(
            [
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=200,
                    status=DeficitTargetStatus.ACTIVE,
                    effective_from_date=date(2026, 1, 1),
                    effective_to_date=date(2026, 12, 31),
                ),
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=400,
                    status=DeficitTargetStatus.ACTIVE,
                    effective_from_date=date(2026, 3, 1),
                    effective_to_date=date(2026, 6, 30),
                ),
            ]
        )
        db.commit()

        service = MetricsService(db)
        weekly = service.get_client_weekly_metrics(
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
        )
        assert weekly.weekly_target_deficit_calories == 2800


def test_pt_comparison_only_returns_linked_clients_stable_ordering() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = _create_user(db, role=Role.PT, prefix="pt-compare")
        client_a = _create_user(db, role=Role.CLIENT, prefix="compare-a")
        client_b = _create_user(db, role=Role.CLIENT, prefix="compare-b")
        unlinked = _create_user(db, role=Role.CLIENT, prefix="compare-unlinked")

        db.add_all(
            [
                PtClientLink(
                    pt_user_id=pt.id,
                    client_user_id=client_b.id,
                    status=PtClientLinkStatus.ACTIVE,
                ),
                PtClientLink(
                    pt_user_id=pt.id,
                    client_user_id=client_a.id,
                    status=PtClientLinkStatus.ACTIVE,
                ),
            ]
        )
        db.add_all(
            [
                CalorieIntakeRecord(
                    client_user_id=client_a.id,
                    recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    calories=1000,
                ),
                ActivityExpenditureRecord(
                    client_user_id=client_a.id,
                    recorded_at=datetime(2026, 3, 17, 18, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    expenditure_calories=700,
                ),
                CalorieIntakeRecord(
                    client_user_id=client_b.id,
                    recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    calories=2000,
                ),
                ActivityExpenditureRecord(
                    client_user_id=client_b.id,
                    recorded_at=datetime(2026, 3, 17, 18, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    expenditure_calories=1200,
                ),
                CalorieIntakeRecord(
                    client_user_id=unlinked.id,
                    recorded_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 17),
                    calories=9999,
                ),
            ]
        )
        db.commit()

        service = MetricsService(db)
        comparison = service.get_pt_metrics_comparison(
            pt_user_id=pt.id,
            as_of_date=date(2026, 3, 18),
        )

        ids = [item.client_user_id for item in comparison.items]
        assert ids == sorted([client_a.id, client_b.id])
        assert all(item.freshness.source == "raw" for item in comparison.items)
        assert all(item.has_data for item in comparison.items)


def test_pt_comparison_explicit_unlinked_clients_forbidden() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = _create_user(db, role=Role.PT, prefix="pt-compare-forbid")
        linked = _create_user(db, role=Role.CLIENT, prefix="linked")
        unlinked = _create_user(db, role=Role.CLIENT, prefix="unlinked")
        db.add(
            PtClientLink(
                pt_user_id=pt.id,
                client_user_id=linked.id,
                status=PtClientLinkStatus.ACTIVE,
            )
        )
        db.commit()

        service = MetricsService(db)
        with pytest.raises(MetricsPermissionError):
            service.get_pt_metrics_comparison(
                pt_user_id=pt.id,
                as_of_date=date(2026, 3, 18),
                client_user_ids=[linked.id, unlinked.id],
            )


def test_pt_comparison_empty_link_set_is_deterministic() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = _create_user(db, role=Role.PT, prefix="pt-empty-compare")
        db.commit()

        service = MetricsService(db)
        comparison = service.get_pt_metrics_comparison(
            pt_user_id=pt.id,
            as_of_date=date(2026, 3, 18),
        )

        assert comparison.items == ()


def test_deficit_progress_formula() -> None:
    assert MetricsService.calculate_deficit_progress(
        weekly_target_deficit_calories=3500,
        net_calorie_balance=-1750,
    ) == Decimal("50.00")
    assert MetricsService.calculate_deficit_progress(
        weekly_target_deficit_calories=3500,
        net_calorie_balance=100,
    ) == Decimal("0.00")
    assert MetricsService.calculate_deficit_progress(
        weekly_target_deficit_calories=3500,
        net_calorie_balance=-9000,
    ) == Decimal("100.00")
    assert (
        MetricsService.calculate_deficit_progress(
            weekly_target_deficit_calories=None,
            net_calorie_balance=-900,
        )
        is None
    )
