"""Verify DB Alembic revision matches the repository head."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def _print(message: str) -> None:
    print(message, flush=True)


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_database_url() -> str:
    base_dir = _base_dir()
    load_dotenv(base_dir / ".env", override=False)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not found. Set it in the environment or backend/.env")
    return database_url


def _repo_heads() -> list[str]:
    base_dir = _base_dir()
    config = Config(str(base_dir / "alembic.ini"))
    config.set_main_option("script_location", str(base_dir / "alembic"))
    script = ScriptDirectory.from_config(config)
    return sorted(script.get_heads())


def _db_revisions(database_url: str) -> list[str]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            )
    finally:
        engine.dispose()
    return sorted(str(item) for item in rows)


def main() -> int:
    database_url = _load_database_url()
    repo_heads = _repo_heads()
    db_revisions = _db_revisions(database_url)

    _print(f"repo_heads={','.join(repo_heads) if repo_heads else 'none'}")
    _print(f"db_revisions={','.join(db_revisions) if db_revisions else 'none'}")

    if not repo_heads:
        _print("status=error detail=no_repo_heads")
        return 2
    if db_revisions == repo_heads:
        _print("status=ok detail=database_matches_repo_head")
        return 0

    _print("status=error detail=database_revision_mismatch")
    return 1


if __name__ == "__main__":
    sys.exit(main())
