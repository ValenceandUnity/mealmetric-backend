# Migration Verification

Use this before and after deploying to staging or production.

## Repo heads

Run:

```powershell
python -m alembic heads
```

Expected:

- the current repo head revisions
- at the time of writing, the repo has multiple heads:
  - `c3d4e5f6a7b8`
  - `e7c4a1b2d9f0`

Current workflow note:

- the migration graph currently has multiple heads
- local rebuilds and deployments should target all heads with `python -m alembic upgrade heads`
- a future merge migration may return the repo to a single-head workflow

## Target DB check

Set `DATABASE_URL` for the target environment and run:

```powershell
python tools/check_alembic_current.py
```

Expected:

- `status=ok detail=database_matches_repo_head`

If it reports `database_revision_mismatch`:

1. stop the deploy
2. review the current DB revision output
3. run `python -m alembic upgrade heads` only through the approved deployment path
4. re-run `python tools/check_alembic_current.py`
