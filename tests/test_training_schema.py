import importlib.util
from datetime import UTC, datetime
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
from mealmetric.models.training import (
    AssignmentStatus,
    ChecklistItem,
    ClientTrainingPackageAssignment,
    PtClientLink,
    PtClientLinkStatus,
    PtFolder,
    PtRosterCategory,
    Routine,
    TrainingPackage,
    TrainingPackageStatus,
    WorkoutCompletionStatus,
    WorkoutLog,
    WorkoutLogExerciseEntry,
    WorkoutLogMode,
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


def test_phase_h1_hardening_migration_lineage_and_upgrade_downgrade() -> None:
    base_module = cast(
        Any,
        _load_migration_module(
            "8c0a5f7d2c19_add_pt_training_domain_schema_foundation.py",
            "phase_h1_base",
        ),
    )
    hardening_module = cast(
        Any,
        _load_migration_module(
            "d2f9c7a4b1e3_harden_h1_training_assignment_and_workout_constraints.py",
            "phase_h1_hardening",
        ),
    )
    assert hardening_module.down_revision == "8c0a5f7d2c19"
    assert base_module.down_revision == "0f2d3a91c6b4"

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
                CREATE TABLE users (
                    id UUID NOT NULL PRIMARY KEY,
                    email VARCHAR NOT NULL,
                    password_hash VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """))

        with Operations.context(MigrationContext.configure(conn)):
            base_module.upgrade()
        with Operations.context(MigrationContext.configure(conn)):
            hardening_module.upgrade()

        inspector = sa.inspect(conn)
        expected_tables = {
            "pt_profiles",
            "pt_client_links",
            "pt_folders",
            "routines",
            "training_packages",
            "training_package_routines",
            "checklist_items",
            "client_training_package_assignments",
            "workout_logs",
        }
        assert expected_tables.issubset(set(inspector.get_table_names()))

        with Operations.context(MigrationContext.configure(conn)):
            hardening_module.downgrade()
        with Operations.context(MigrationContext.configure(conn)):
            base_module.downgrade()

        remaining_tables = set(sa.inspect(conn).get_table_names())
        assert expected_tables.isdisjoint(remaining_tables)


def test_workout_log_exercise_entries_migration_lineage() -> None:
    workout_entries_module = cast(
        Any,
        _load_migration_module(
            "b8f9e3c7d4a1_add_workout_log_exercise_entries.py",
            "phase_h1_workout_entries",
        ),
    )
    assert workout_entries_module.down_revision == "6d1f8b42c3aa"


def test_workout_log_exercise_entries_migration_upgrade_and_downgrade() -> None:
    workout_entries_module = cast(
        Any,
        _load_migration_module(
            "b8f9e3c7d4a1_add_workout_log_exercise_entries.py",
            "phase_h1_workout_entries_upgrade",
        ),
    )

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
                CREATE TABLE workout_logs (
                    id UUID NOT NULL PRIMARY KEY
                )
                """))

        with Operations.context(MigrationContext.configure(conn)):
            workout_entries_module.upgrade()

        inspector = sa.inspect(conn)
        assert "workout_log_exercise_entries" in set(inspector.get_table_names())

        with Operations.context(MigrationContext.configure(conn)):
            workout_entries_module.downgrade()

        remaining_tables = set(sa.inspect(conn).get_table_names())
        assert "workout_log_exercise_entries" not in remaining_tables


def test_workout_log_mode_migration_lineage() -> None:
    workout_mode_module = cast(
        Any,
        _load_migration_module(
            "e7c4a1b2d9f0_add_workout_log_mode_for_history_filters.py",
            "phase_h1_workout_mode",
        ),
    )
    assert workout_mode_module.down_revision == "b8f9e3c7d4a1"


def test_workout_log_mode_migration_upgrade_and_downgrade() -> None:
    workout_mode_module = cast(
        Any,
        _load_migration_module(
            "e7c4a1b2d9f0_add_workout_log_mode_for_history_filters.py",
            "phase_h1_workout_mode_upgrade",
        ),
    )

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE workout_logs (
                    id UUID NOT NULL PRIMARY KEY
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            workout_mode_module.upgrade()

        inspector = sa.inspect(conn)
        column_names = {column["name"] for column in inspector.get_columns("workout_logs")}
        assert "mode" in column_names

        with Operations.context(MigrationContext.configure(conn)):
            workout_mode_module.downgrade()

        remaining_columns = {
            column["name"] for column in sa.inspect(conn).get_columns("workout_logs")
        }
        assert "mode" not in remaining_columns


def test_standalone_workout_logs_migration_lineage() -> None:
    standalone_module = cast(
        Any,
        _load_migration_module(
            "7b3c4d5e6f7a_allow_standalone_client_workout_logs.py",
            "phase_h1_standalone_workout_logs",
        ),
    )
    assert standalone_module.down_revision == "fa9c1d2e3b4a"


def test_standalone_workout_logs_migration_upgrade_and_downgrade() -> None:
    standalone_module = cast(
        Any,
        _load_migration_module(
            "7b3c4d5e6f7a_allow_standalone_client_workout_logs.py",
            "phase_h1_standalone_workout_logs_upgrade",
        ),
    )

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE workout_logs (
                    id UUID NOT NULL PRIMARY KEY,
                    pt_user_id UUID NOT NULL,
                    assignment_id UUID NULL,
                    routine_id UUID NULL,
                    CONSTRAINT ck_workout_logs_assignment_or_routine_required
                    CHECK (assignment_id IS NOT NULL OR routine_id IS NOT NULL)
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            standalone_module.upgrade()

        inspector = sa.inspect(conn)
        columns = {column["name"]: column for column in inspector.get_columns("workout_logs")}
        assert columns["pt_user_id"]["nullable"] is True
        check_constraints = {
            constraint["name"] for constraint in inspector.get_check_constraints("workout_logs")
        }
        assert "ck_workout_logs_assignment_or_routine_required" not in check_constraints

        with Operations.context(MigrationContext.configure(conn)):
            standalone_module.downgrade()

        downgraded_columns = {
            column["name"]: column for column in sa.inspect(conn).get_columns("workout_logs")
        }
        assert downgraded_columns["pt_user_id"]["nullable"] is False
        downgraded_checks = {
            constraint["name"]
            for constraint in sa.inspect(conn).get_check_constraints("workout_logs")
        }
        assert "ck_workout_logs_assignment_or_routine_required" in downgraded_checks


def test_pt_roster_categories_migration_lineage() -> None:
    roster_module = cast(
        Any,
        _load_migration_module(
            "9d4e5f6a7b8c_add_pt_roster_categories.py",
            "phase_h1_pt_roster_categories",
        ),
    )
    assert roster_module.down_revision == "7b3c4d5e6f7a"


def test_pt_roster_categories_migration_upgrade_and_downgrade_without_data() -> None:
    roster_module = cast(
        Any,
        _load_migration_module(
            "9d4e5f6a7b8c_add_pt_roster_categories.py",
            "phase_h1_pt_roster_categories_upgrade",
        ),
    )

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
        conn.execute(
            text(
                """
                CREATE TABLE pt_client_links (
                    id UUID NOT NULL PRIMARY KEY,
                    pt_user_id UUID NOT NULL,
                    client_user_id UUID NOT NULL,
                    status VARCHAR NOT NULL,
                    started_at DATETIME NULL,
                    ended_at DATETIME NULL,
                    notes VARCHAR NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            roster_module.upgrade()

        inspector = sa.inspect(conn)
        assert "pt_roster_categories" in set(inspector.get_table_names())
        upgraded_columns = {
            column["name"] for column in inspector.get_columns("pt_client_links")
        }
        assert "roster_category_id" in upgraded_columns

        with Operations.context(MigrationContext.configure(conn)):
            roster_module.downgrade()

        remaining_tables = set(sa.inspect(conn).get_table_names())
        assert "pt_roster_categories" not in remaining_tables
        downgraded_columns = {
            column["name"] for column in sa.inspect(conn).get_columns("pt_client_links")
        }
        assert "roster_category_id" not in downgraded_columns


def test_pt_roster_categories_migration_downgrade_refuses_with_category_rows() -> None:
    roster_module = cast(
        Any,
        _load_migration_module(
            "9d4e5f6a7b8c_add_pt_roster_categories.py",
            "phase_h1_pt_roster_categories_guard_category",
        ),
    )

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
        conn.execute(
            text(
                """
                CREATE TABLE pt_client_links (
                    id UUID NOT NULL PRIMARY KEY,
                    pt_user_id UUID NOT NULL,
                    client_user_id UUID NOT NULL,
                    status VARCHAR NOT NULL,
                    started_at DATETIME NULL,
                    ended_at DATETIME NULL,
                    notes VARCHAR NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            roster_module.upgrade()

        pt_id = str(uuid4())
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, role)
                VALUES (:id, :email, :password_hash, :role)
                """
            ),
            {
                "id": pt_id,
                "email": "pt-roster-guard@example.com",
                "password_hash": "hash",
                "role": "pt",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO pt_roster_categories (id, pt_user_id, name)
                VALUES (:id, :pt_user_id, :name)
                """
            ),
            {
                "id": str(uuid4()),
                "pt_user_id": pt_id,
                "name": "Strength",
            },
        )

        with (
            Operations.context(MigrationContext.configure(conn)),
            pytest.raises(
                RuntimeError,
                match="Cannot downgrade roster categories while roster category data or assignments exist.",
            ),
        ):
            roster_module.downgrade()


def test_pt_roster_categories_migration_downgrade_refuses_with_assignments() -> None:
    roster_module = cast(
        Any,
        _load_migration_module(
            "9d4e5f6a7b8c_add_pt_roster_categories.py",
            "phase_h1_pt_roster_categories_guard_assignment",
        ),
    )

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
        conn.execute(
            text(
                """
                CREATE TABLE pt_client_links (
                    id UUID NOT NULL PRIMARY KEY,
                    pt_user_id UUID NOT NULL,
                    client_user_id UUID NOT NULL,
                    status VARCHAR NOT NULL,
                    started_at DATETIME NULL,
                    ended_at DATETIME NULL,
                    notes VARCHAR NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        with Operations.context(MigrationContext.configure(conn)):
            roster_module.upgrade()

        pt_id = str(uuid4())
        client_id = str(uuid4())
        category_id = str(uuid4())
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, role)
                VALUES (:id, :email, :password_hash, :role)
                """
            ),
            [
                {
                    "id": pt_id,
                    "email": "pt-roster-assignment@example.com",
                    "password_hash": "hash",
                    "role": "pt",
                },
                {
                    "id": client_id,
                    "email": "client-roster-assignment@example.com",
                    "password_hash": "hash",
                    "role": "client",
                },
            ],
        )
        conn.execute(
            text(
                """
                INSERT INTO pt_roster_categories (id, pt_user_id, name)
                VALUES (:id, :pt_user_id, :name)
                """
            ),
            {
                "id": category_id,
                "pt_user_id": pt_id,
                "name": "Conditioning",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO pt_client_links (
                    id,
                    pt_user_id,
                    client_user_id,
                    roster_category_id,
                    status
                )
                VALUES (
                    :id,
                    :pt_user_id,
                    :client_user_id,
                    :roster_category_id,
                    :status
                )
                """
            ),
            {
                "id": str(uuid4()),
                "pt_user_id": pt_id,
                "client_user_id": client_id,
                "roster_category_id": category_id,
                "status": PtClientLinkStatus.ACTIVE.value,
            },
        )

        with (
            Operations.context(MigrationContext.configure(conn)),
            pytest.raises(
                RuntimeError,
                match="Cannot downgrade roster categories while roster category data or assignments exist.",
            ),
        ):
            roster_module.downgrade()


def test_training_tables_registered_in_metadata() -> None:
    expected_tables = {
        "pt_profiles",
        "pt_client_links",
        "pt_roster_categories",
        "pt_folders",
        "routines",
        "training_packages",
        "training_package_routines",
        "checklist_items",
        "client_training_package_assignments",
        "workout_logs",
        "workout_log_exercise_entries",
    }
    assert expected_tables.issubset(set(Base.metadata.tables))


def test_training_enums_persist_lowercase_values() -> None:
    assert PtClientLink.__table__.c.status.type.enums == [status.value for status in PtClientLinkStatus]
    assert TrainingPackage.__table__.c.status.type.enums == [
        status.value for status in TrainingPackageStatus
    ]
    assert ClientTrainingPackageAssignment.__table__.c.status.type.enums == [
        status.value for status in AssignmentStatus
    ]
    assert WorkoutLog.__table__.c.mode.type.enums == [mode.value for mode in WorkoutLogMode]
    assert WorkoutLog.__table__.c.completion_status.type.enums == [
        status.value for status in WorkoutCompletionStatus
    ]


def test_pt_roster_category_relationship_columns_registered() -> None:
    roster_category_columns = set(PtRosterCategory.__table__.c.keys())
    link_columns = set(PtClientLink.__table__.c.keys())

    assert {"id", "pt_user_id", "name", "created_at", "updated_at"}.issubset(
        roster_category_columns
    )
    assert "roster_category_id" in link_columns


def test_mismatched_pt_client_assignment_rejected() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt1 = User(email="pt1@example.com", password_hash="hash", role=Role.PT)
        pt2 = User(email="pt2@example.com", password_hash="hash", role=Role.PT)
        client = User(email="client@example.com", password_hash="hash", role=Role.CLIENT)
        db.add_all([pt1, pt2, client])
        db.flush()

        link = PtClientLink(
            pt_user_id=pt1.id,
            client_user_id=client.id,
            status=PtClientLinkStatus.ACTIVE,
        )
        folder = PtFolder(pt_user_id=pt1.id, name="Main")
        training_package = TrainingPackage(pt_user_id=pt1.id, folder=folder, title="Pack")
        db.add_all([link, folder, training_package])
        db.flush()
        db.commit()

        mismatch = ClientTrainingPackageAssignment(
            training_package_id=training_package.id,
            pt_user_id=pt2.id,
            client_user_id=client.id,
            pt_client_link_id=link.id,
            assigned_at=datetime(2026, 3, 16, tzinfo=UTC),
        )
        db.add(mismatch)

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_standalone_workout_log_without_anchor_is_allowed() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        client = User(email="client-log@example.com", password_hash="hash", role=Role.CLIENT)
        db.add(client)
        db.flush()

        standalone_log = WorkoutLog(
            client_user_id=client.id,
            pt_user_id=None,
            assignment_id=None,
            routine_id=None,
            performed_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            mode=WorkoutLogMode.GENERAL_WORKOUT,
            completion_status=WorkoutCompletionStatus.COMPLETED,
        )
        db.add(standalone_log)
        db.commit()

        db.refresh(standalone_log)
        assert standalone_log.pt_user_id is None
        assert standalone_log.assignment_id is None
        assert standalone_log.routine_id is None
        row = db.execute(text("SELECT mode, completion_status FROM workout_logs")).one()
        assert row.mode == WorkoutLogMode.GENERAL_WORKOUT.value
        assert row.completion_status == WorkoutCompletionStatus.COMPLETED.value


def test_checklist_item_owner_constraint_still_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = User(email="pt-check@example.com", password_hash="hash", role=Role.PT)
        db.add(pt)
        db.flush()

        folder = PtFolder(pt_user_id=pt.id, name="Folder")
        routine = Routine(pt_user_id=pt.id, folder=folder, title="Routine")
        training_package = TrainingPackage(pt_user_id=pt.id, folder=folder, title="Package")
        db.add_all([folder, routine, training_package])
        db.flush()
        db.commit()

        bad_item = ChecklistItem(label="invalid", position=1)
        db.add(bad_item)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        bad_item = ChecklistItem(
            training_package_id=training_package.id,
            routine_id=routine.id,
            label="invalid-double-owner",
            position=2,
        )
        db.add(bad_item)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_workout_log_exercise_entry_position_uniqueness_is_enforced() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = User(email="pt-entry@example.com", password_hash="hash", role=Role.PT)
        client = User(email="client-entry@example.com", password_hash="hash", role=Role.CLIENT)
        db.add_all([pt, client])
        db.flush()

        routine = Routine(pt_user_id=pt.id, title="Entry Routine")
        db.add(routine)
        db.flush()

        workout_log = WorkoutLog(
            client_user_id=client.id,
            pt_user_id=pt.id,
            performed_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
            routine_id=routine.id,
        )
        db.add(workout_log)
        db.flush()

        db.add_all(
            [
                WorkoutLogExerciseEntry(
                    workout_log_id=workout_log.id, exercise_name="Bench", position=0
                ),
                WorkoutLogExerciseEntry(
                    workout_log_id=workout_log.id, exercise_name="Row", position=0
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
