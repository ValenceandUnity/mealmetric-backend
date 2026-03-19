from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory, AuditLog
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
from mealmetric.models.user import Role, User
from mealmetric.repos import metrics_repo


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _create_user(db: Session, *, role: Role, email_prefix: str) -> User:
    user = User(email=f"{email_prefix}-{uuid4()}@example.com", password_hash="hash", role=role)
    db.add(user)
    db.flush()
    return user


def test_raw_record_reads_are_deterministic() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="raw-client")

        db.add_all(
            [
                CalorieIntakeRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 16, 10, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    calories=400,
                ),
                CalorieIntakeRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 16, 8, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    calories=250,
                ),
                ActivityExpenditureRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 16, 11, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    expenditure_calories=500,
                ),
                ActivityExpenditureRecord(
                    client_user_id=client.id,
                    recorded_at=datetime(2026, 3, 16, 7, 30, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    expenditure_calories=200,
                ),
            ]
        )
        db.commit()

        calorie_records = metrics_repo.list_calorie_intake_records(db, client.id)
        assert [item.calories for item in calorie_records] == [250, 400]

        activity_records = metrics_repo.list_activity_expenditure_records(db, client.id)
        assert [item.expenditure_calories for item in activity_records] == [200, 500]


def test_active_deficit_target_resolution_by_date() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="target-client")

        db.add_all(
            [
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=300,
                    status=DeficitTargetStatus.ACTIVE,
                    effective_from_date=date(2026, 1, 1),
                    effective_to_date=date(2026, 1, 31),
                ),
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=400,
                    status=DeficitTargetStatus.INACTIVE,
                    effective_from_date=date(2026, 2, 1),
                ),
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=500,
                    status=DeficitTargetStatus.ACTIVE,
                    effective_from_date=date(2026, 2, 15),
                ),
            ]
        )
        db.commit()

        jan_target = metrics_repo.get_active_deficit_target_for_client_on_date(
            db,
            client_user_id=client.id,
            as_of_date=date(2026, 1, 20),
        )
        assert jan_target is not None
        assert jan_target.target_daily_deficit_calories == 300

        feb_target = metrics_repo.get_active_deficit_target_for_client_on_date(
            db,
            client_user_id=client.id,
            as_of_date=date(2026, 2, 20),
        )
        assert feb_target is not None
        assert feb_target.target_daily_deficit_calories == 500


def test_active_deficit_target_overlap_selection_is_deterministic() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="target-overlap")

        db.add_all(
            [
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=250,
                    status=DeficitTargetStatus.ACTIVE,
                    effective_from_date=date(2026, 1, 1),
                    effective_to_date=date(2026, 12, 31),
                ),
                DeficitTarget(
                    client_user_id=client.id,
                    target_daily_deficit_calories=450,
                    status=DeficitTargetStatus.ACTIVE,
                    effective_from_date=date(2026, 3, 1),
                    effective_to_date=date(2026, 6, 30),
                ),
            ]
        )
        db.commit()

        chosen = metrics_repo.get_active_deficit_target_for_client_on_date(
            db,
            client_user_id=client.id,
            as_of_date=date(2026, 3, 20),
        )
        assert chosen is not None
        assert chosen.target_daily_deficit_calories == 450


def test_weekly_rollup_upsert_is_idempotent() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="weekly-client")

        first = metrics_repo.upsert_weekly_metric_rollup(
            db,
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
            total_intake_calories=12000,
            total_expenditure_calories=10000,
            net_calorie_balance=2000,
            target_deficit_calories=1500,
            deficit_progress_percent=Decimal("75.00"),
            computed_at=datetime(2026, 3, 17, 4, 0, tzinfo=UTC),
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
            version=1,
        )
        db.commit()

        second = metrics_repo.upsert_weekly_metric_rollup(
            db,
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
            total_intake_calories=11000,
            total_expenditure_calories=10200,
            net_calorie_balance=800,
            target_deficit_calories=1400,
            deficit_progress_percent=Decimal("57.14"),
            computed_at=datetime(2026, 3, 17, 6, 0, tzinfo=UTC),
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 5, 59, tzinfo=UTC),
            version=2,
        )
        db.commit()

        assert first.id == second.id
        assert second.version == 2
        assert second.net_calorie_balance == 800

        count_stmt = select(WeeklyMetricRollup).where(
            WeeklyMetricRollup.client_user_id == client.id,
            WeeklyMetricRollup.week_start_date == date(2026, 3, 16),
        )
        assert len(list(db.scalars(count_stmt))) == 1
        audit_rows = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.action == AuditEventAction.METRICS_WEEKLY_ROLLUP_UPSERTED)
                .order_by(AuditLog.created_at.asc())
            )
        )
        assert len(audit_rows) == 2
        assert audit_rows[0].category == AuditEventCategory.METRICS
        assert audit_rows[0].metadata_json["operation"] == "insert"
        assert audit_rows[1].metadata_json["operation"] == "update"
        assert audit_rows[1].metadata_json["week_start_date"] == "2026-03-16"
        assert audit_rows[1].metadata_json["version"] == 2


def test_strength_rollup_upsert_is_idempotent() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="strength-client")

        first = metrics_repo.upsert_strength_metric_rollup(
            db,
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
            total_workouts=5,
            completed_workouts=4,
            training_minutes=200,
            volume_score=Decimal("1234.56"),
            computed_at=datetime(2026, 3, 17, 4, 0, tzinfo=UTC),
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
            version=1,
        )
        db.commit()

        second = metrics_repo.upsert_strength_metric_rollup(
            db,
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
            total_workouts=6,
            completed_workouts=5,
            training_minutes=240,
            volume_score=Decimal("1500.00"),
            computed_at=datetime(2026, 3, 17, 6, 0, tzinfo=UTC),
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 5, 59, tzinfo=UTC),
            version=2,
        )
        db.commit()

        assert first.id == second.id
        assert second.training_minutes == 240
        assert second.version == 2

        count_stmt = select(StrengthMetricRollup).where(
            StrengthMetricRollup.client_user_id == client.id,
            StrengthMetricRollup.week_start_date == date(2026, 3, 16),
        )
        assert len(list(db.scalars(count_stmt))) == 1


def test_client_snapshot_upsert_is_idempotent() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="snapshot-client")

        first = metrics_repo.upsert_client_metric_snapshot(
            db,
            client_user_id=client.id,
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
            snapshot_generated_at=datetime(2026, 3, 17, 5, 0, tzinfo=UTC),
            latest_week_start_date=date(2026, 3, 16),
            current_intake_ceiling_calories=1800,
            version=1,
        )
        db.commit()

        second = metrics_repo.upsert_client_metric_snapshot(
            db,
            client_user_id=client.id,
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 5, 59, tzinfo=UTC),
            snapshot_generated_at=datetime(2026, 3, 17, 6, 0, tzinfo=UTC),
            latest_week_start_date=date(2026, 3, 16),
            current_intake_ceiling_calories=1700,
            current_week_net_balance=500,
            version=2,
        )
        db.commit()

        assert first.id == second.id
        assert second.current_intake_ceiling_calories == 1700
        assert second.current_week_net_balance == 500
        assert second.version == 2

        count_stmt = select(ClientMetricSnapshot).where(
            ClientMetricSnapshot.client_user_id == client.id
        )
        assert len(list(db.scalars(count_stmt))) == 1
        audit_rows = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.action == AuditEventAction.METRICS_CLIENT_SNAPSHOT_UPSERTED)
                .order_by(AuditLog.created_at.asc())
            )
        )
        assert len(audit_rows) == 2
        assert audit_rows[0].metadata_json["operation"] == "insert"
        assert audit_rows[1].metadata_json["operation"] == "update"
        assert audit_rows[1].metadata_json["snapshot_generated_at"] == "2026-03-17T06:00:00+00:00"
        assert audit_rows[1].metadata_json["client_user_id"] == str(client.id)


def test_audit_metadata_is_json_safe_and_truncated() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = _create_user(db, role=Role.CLIENT, email_prefix="audit-safe")

        metrics_repo.upsert_strength_metric_rollup(
            db,
            client_user_id=client.id,
            week_start_date=date(2026, 3, 16),
            total_workouts=3,
            completed_workouts=2,
            training_minutes=90,
            volume_score=Decimal("123456789.12"),
            computed_at=datetime(2026, 3, 17, 4, 0, tzinfo=UTC),
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
            version=1,
        )

        audit_row = db.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditEventAction.METRICS_STRENGTH_ROLLUP_UPSERTED
            )
        )
        assert audit_row is not None
        assert audit_row.metadata_json["volume_score"] == "123456789.12"
        assert audit_row.metadata_json["source_window_start"] == "2026-03-10T05:00:00+00:00"
        assert audit_row.metadata_json["client_user_id"] == str(client.id)


def test_pt_link_scope_helpers_only_return_active_links() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt_1 = _create_user(db, role=Role.PT, email_prefix="pt1")
        pt_2 = _create_user(db, role=Role.PT, email_prefix="pt2")
        client_a = _create_user(db, role=Role.CLIENT, email_prefix="client-a")
        client_b = _create_user(db, role=Role.CLIENT, email_prefix="client-b")
        client_c = _create_user(db, role=Role.CLIENT, email_prefix="client-c")

        db.add_all(
            [
                PtClientLink(
                    pt_user_id=pt_1.id,
                    client_user_id=client_a.id,
                    status=PtClientLinkStatus.ACTIVE,
                ),
                PtClientLink(
                    pt_user_id=pt_1.id,
                    client_user_id=client_b.id,
                    status=PtClientLinkStatus.PENDING,
                ),
                PtClientLink(
                    pt_user_id=pt_1.id,
                    client_user_id=client_c.id,
                    status=PtClientLinkStatus.ENDED,
                ),
                PtClientLink(
                    pt_user_id=pt_2.id,
                    client_user_id=client_a.id,
                    status=PtClientLinkStatus.ACTIVE,
                ),
            ]
        )
        db.commit()

        active_clients_for_pt1 = metrics_repo.list_active_client_ids_for_pt(db, pt_user_id=pt_1.id)
        assert active_clients_for_pt1 == [client_a.id]

        active_pts_for_client_a = metrics_repo.list_active_pt_user_ids_for_client(
            db,
            client_user_id=client_a.id,
        )
        assert active_pts_for_client_a == sorted([pt_1.id, pt_2.id])

        assert (
            metrics_repo.get_active_pt_client_link(
                db,
                pt_user_id=pt_1.id,
                client_user_id=client_a.id,
            )
            is not None
        )

        assert (
            metrics_repo.get_active_pt_client_link(
                db,
                pt_user_id=pt_1.id,
                client_user_id=client_b.id,
            )
            is None
        )


def test_bulk_raw_record_helpers_do_not_leak_unlinked_clients() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        linked_client = _create_user(db, role=Role.CLIENT, email_prefix="linked")
        unlinked_client = _create_user(db, role=Role.CLIENT, email_prefix="unlinked")

        db.add_all(
            [
                CalorieIntakeRecord(
                    client_user_id=linked_client.id,
                    recorded_at=datetime(2026, 3, 16, 9, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    calories=300,
                ),
                CalorieIntakeRecord(
                    client_user_id=unlinked_client.id,
                    recorded_at=datetime(2026, 3, 16, 9, 30, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    calories=900,
                ),
                ActivityExpenditureRecord(
                    client_user_id=linked_client.id,
                    recorded_at=datetime(2026, 3, 16, 10, 0, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    expenditure_calories=200,
                ),
                ActivityExpenditureRecord(
                    client_user_id=unlinked_client.id,
                    recorded_at=datetime(2026, 3, 16, 10, 30, tzinfo=UTC),
                    business_date=date(2026, 3, 16),
                    expenditure_calories=700,
                ),
            ]
        )
        db.commit()

        calorie_rows = metrics_repo.list_active_calorie_intake_records_for_clients(
            db,
            client_user_ids=[linked_client.id],
        )
        assert len(calorie_rows) == 1
        assert calorie_rows[0].client_user_id == linked_client.id

        activity_rows = metrics_repo.list_active_activity_expenditure_records_for_clients(
            db,
            client_user_ids=[linked_client.id],
        )
        assert len(activity_rows) == 1
        assert activity_rows[0].client_user_id == linked_client.id
