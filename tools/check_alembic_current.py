"""Verify DB Alembic revision matches the repository head."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def _print(message: str) -> None:
    print(message, flush=True)


def _load_database_url() -> str:
    base_dir = Path(__file__).resolve().parents[1]
    load_dotenv(base_dir / ".env", override=False)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not found. Set it in the environment or backend/.env")
    return database_url


def _repo_heads() -> list[str]:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    heads: set[str] = set()
    for revision_file in versions_dir.glob("*.py"):
        revision: str | None = None
        down_revision: str | list[str] | tuple[str, ...] | None = None
        namespace: dict[str, object] = {}
        exec(revision_file.read_text(encoding="utf-8"), namespace)  # noqa: S102
        raw_revision = namespace.get("revision")
        raw_down_revision = namespace.get("down_revision")
        if isinstance(raw_revision, str):
            revision = raw_revision
        if isinstance(raw_down_revision, str) or raw_down_revision is None:
            down_revision = raw_down_revision
        elif isinstance(raw_down_revision, (list, tuple)) and all(
            isinstance(item, str) for item in raw_down_revision
        ):
            down_revision = list(raw_down_revision)
        if revision is None:
            continue
        heads.add(revision)
        if isinstance(down_revision, str):
            heads.discard(down_revision)
        elif isinstance(down_revision, list):
            for item in down_revision:
                heads.discard(item)
    return sorted(heads)


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
