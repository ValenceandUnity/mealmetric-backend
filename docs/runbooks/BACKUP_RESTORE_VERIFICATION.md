# Backup / Restore Verification

1. Confirm the environment has a current database backup according to your platform policy.
2. Restore that backup into a non-production database.
3. Point `DATABASE_URL` at the restored database.
4. Verify connectivity:
   - `python tools/check_db_connectivity.py`
5. Verify schema currency:
   - `python tools/check_alembic_current.py`
6. Run a backend smoke test against the restored DB:
   - `GET /livez`
   - `GET /readyz`
   - signed admin `GET /db/health`
7. Record the backup timestamp, restore target, and verification result.
