import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.db.base import Base
from mealmetric.models.training import (
    ChecklistItem,
    ClientTrainingPackageAssignment,
    PtClientLink,
    PtClientLinkStatus,
    PtFolder,
    Routine,
    TrainingPackage,
    WorkoutLog,
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


def test_training_tables_registered_in_metadata() -> None:
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
    assert expected_tables.issubset(set(Base.metadata.tables))


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


def test_orphan_workout_log_rejected() -> None:
    session_local = _build_sqlite_sessionmaker()

    with session_local() as db:
        pt = User(email="pt-log@example.com", password_hash="hash", role=Role.PT)
        client = User(email="client-log@example.com", password_hash="hash", role=Role.CLIENT)
        db.add_all([pt, client])
        db.flush()
        db.commit()

        orphan_log = WorkoutLog(
            client_user_id=client.id,
            pt_user_id=pt.id,
            assignment_id=None,
            routine_id=None,
            performed_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
        )
        db.add(orphan_log)

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


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
