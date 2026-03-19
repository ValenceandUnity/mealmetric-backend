# DB Connectivity Checker

This tool verifies Supabase Postgres connectivity using `DATABASE_URL` from `backend/.env`.

## Run (PowerShell)

From the backend folder:

```powershell
python tools/check_db_connectivity.py
python tools/check_alembic_current.py
```

## What It Checks

1. DNS resolution for the DB host.
2. TCP connectivity to the DB port.
3. Postgres auth + SSL by opening a `psycopg2` connection and running `SELECT 1;`.

The script prints only sanitized metadata:
- dialect
- host
- port
- database

It never prints username or password.

## Exit Codes

- `0`: success (DNS + port + auth/SSL all passed)
- `2`: DNS failure
- `3`: port/TCP failure
- `4`: Postgres auth/SSL failure

## Alembic Revision Checker

`check_alembic_current.py` compares the repository Alembic head(s) with the target database `alembic_version` table.

- `0`: target DB matches repo head
- `1`: target DB revision mismatch
- `2`: repo head discovery failed

## Expected Failure Output Types

- DNS failure: `DNS check: FAILED (...)` and exits `2`
- Port failure: `Port check: FAILED (...)` and exits `3`
- Auth/SSL failure: `Postgres auth check: FAILED (...)` and exits `4`
