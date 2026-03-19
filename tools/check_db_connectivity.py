"""Deterministic connectivity checker for Supabase Postgres."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy.engine.url import make_url


def _print(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    base_dir = Path(__file__).resolve().parents[1]
    load_dotenv(base_dir / ".env", override=True)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not found. Check backend/.env")

    parsed = make_url(database_url)

    dialect = parsed.get_backend_name()
    host = parsed.host or ""
    port = parsed.port or 5432
    database = parsed.database or ""

    _print(f"dialect={dialect}")
    _print(f"host={host or 'unknown'}")
    _print(f"port={port}")
    _print(f"database={database or 'unknown'}")

    # 1) DNS check
    _print("DNS check: starting")
    if not host:
        _print("DNS check: FAILED (ValueError: host is empty)")
        return 2

    try:
        dns_results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        unique_ips = sorted({item[4][0] for item in dns_results if item[4]})
        _print(f"DNS check: OK ({len(unique_ips)} IPs)")
    except Exception as exc:  # pragma: no cover
        _print(f"DNS check: FAILED ({exc.__class__.__name__}: {exc})")
        return 2

    # 2) Port check
    _print("Port check: starting")
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
        _print(f"Port check: OK ({host}:{port})")
    except Exception as exc:  # pragma: no cover
        _print(f"Port check: FAILED ({exc.__class__.__name__}: {exc})")
        return 3

    # 3) Postgres auth/SSL check
    _print("Postgres auth check: starting")
    auth_url = parsed
    if "sslmode" not in auth_url.query:
        auth_url = auth_url.update_query_dict({"sslmode": "require"})

    dsn = auth_url.render_as_string(hide_password=False)

    try:
        with psycopg2.connect(dsn=dsn, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        _print("Postgres auth check: OK (SELECT 1 succeeded)")
        return 0
    except Exception as exc:  # pragma: no cover
        _print(f"Postgres auth check: FAILED ({exc.__class__.__name__}: {exc})")
        return 4


if __name__ == "__main__":
    sys.exit(main())
