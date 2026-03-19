# Migration Verification

Use this before and after deploying to staging or production.

## Repo head

Run:

```powershell
python -m alembic heads
```

Expected:

- a single repo head revision

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
3. run `python -m alembic upgrade head` only through the approved deployment path
4. re-run `python tools/check_alembic_current.py`
