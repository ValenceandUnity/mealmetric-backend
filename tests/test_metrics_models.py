import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.metrics import (
    CalorieIntakeRecord,
    ClientMetricSnapshot,
    DeficitTarget,
    DeficitTargetStatus,
    MetricRecordSource,
    WeeklyMetricRollup,
)
from mealmetric.models.user import Role, User


def _build_sqlite_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _load_migration_module(filename: str, module_name: str) -> object:
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_user(db: Session, email_prefix: str = "metrics") -> User:
    user = User(
        email=f"{email_prefix}-{uuid4()}@example.com", password_hash="hash", role=Role.CLIENT
    )
    db.add(user)
    db.flush()
    return user


def test_phase_i_metrics_migration_lineage_and_upgrade_downgrade() -> None:
    module = cast(
        Any,
        _load_migration_module(
            "9f3a2d7c1b4e_add_phase_i_metrics_domain_schema_foundation.py",
            "phase_i_metrics",
        ),
    )

    assert module.down_revision == "d2f9c7a4b1e3"

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id UUID NOT NULL PRIMARY KEY,
                    email VARCHAR NOT NULL,
                    password_hash VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

        inspector = sa.inspect(conn)
        expected_tables = {
            "calorie_intake_records",
            "activity_expenditure_records",
            "deficit_targets",
            "weekly_metric_rollups",
            "strength_metric_rollups",
            "client_metric_snapshots",
        }
        assert expected_tables.issubset(set(inspector.get_table_names()))

        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()

        remaining_tables = set(sa.inspect(conn).get_table_names())
        assert expected_tables.isdisjoint(remaining_tables)


def test_metrics_tables_registered_in_metadata() -> None:
    expected_tables = {
        "calorie_intake_records",
        "activity_expenditure_records",
        "deficit_targets",
        "weekly_metric_rollups",
        "strength_metric_rollups",
        "client_metric_snapshots",
    }
    assert expected_tables.issubset(set(Base.metadata.tables))


def test_metrics_foreign_key_constraints_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        orphan_record = CalorieIntakeRecord(
            client_user_id=uuid4(),
            recorded_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            business_date=date(2026, 3, 16),
            calories=450,
        )
        db.add(orphan_record)

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_weekly_rollup_uniqueness_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        user = _create_user(db)
        db.commit()

        week_start = date(2026, 3, 16)
        source_window_start = datetime(2026, 3, 10, 5, 0, tzinfo=UTC)
        source_window_end = datetime(2026, 3, 17, 4, 59, tzinfo=UTC)

        first = WeeklyMetricRollup(
            client_user_id=user.id,
            week_start_date=week_start,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
        )
        second = WeeklyMetricRollup(
            client_user_id=user.id,
            week_start_date=week_start,
            source_window_start=source_window_start,
            source_window_end=source_window_end,
        )
        db.add(first)
        db.commit()

        db.add(second)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_client_snapshot_uniqueness_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        user = _create_user(db)
        db.commit()

        window_start = datetime(2026, 3, 10, 5, 0, tzinfo=UTC)
        window_end = datetime(2026, 3, 17, 4, 59, tzinfo=UTC)

        first = ClientMetricSnapshot(
            client_user_id=user.id,
            source_window_start=window_start,
            source_window_end=window_end,
        )
        second = ClientMetricSnapshot(
            client_user_id=user.id,
            source_window_start=window_start,
            source_window_end=window_end,
        )
        db.add(first)
        db.commit()

        db.add(second)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_metrics_enum_and_defaults() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        user = _create_user(db)

        target = DeficitTarget(
            client_user_id=user.id,
            target_daily_deficit_calories=500,
            effective_from_date=date(2026, 3, 16),
        )
        record = CalorieIntakeRecord(
            client_user_id=user.id,
            recorded_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            business_date=date(2026, 3, 16),
            calories=600,
        )

        db.add_all([target, record])
        db.commit()
        db.refresh(target)
        db.refresh(record)

        assert target.status == DeficitTargetStatus.ACTIVE
        assert record.source == MetricRecordSource.MANUAL


def test_metrics_check_constraints_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        user = _create_user(db)
        db.commit()

        invalid_target = DeficitTarget(
            client_user_id=user.id,
            target_daily_deficit_calories=500,
            effective_from_date=date(2026, 3, 20),
            effective_to_date=date(2026, 3, 19),
        )
        db.add(invalid_target)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        invalid_rollup = WeeklyMetricRollup(
            client_user_id=user.id,
            week_start_date=date(2026, 3, 16),
            week_start_day=2,
            source_window_start=datetime(2026, 3, 10, 5, 0, tzinfo=UTC),
            source_window_end=datetime(2026, 3, 17, 4, 59, tzinfo=UTC),
        )
        db.add(invalid_rollup)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
