# Rollback

1. Stop sending new traffic to the new backend revision.
2. Restore the previous application release artifact/config in your deployment system.
3. Re-run probes:
   - `GET /livez`
   - `GET /readyz`
4. If the failed release applied a forward-only migration, do not guess at a downgrade.
   - verify current DB revision with `python tools/check_alembic_current.py`
   - use a DB restore or an explicitly reviewed downgrade plan before changing schema state
5. Re-run the signed admin smoke checks used during deploy.
