# Deployment Source Of Truth

This repository does not contain platform-specific deploy manifests, container definitions, or infrastructure code.

The canonical source of truth currently lives in this repo as a deployment contract:

## Required runtime contract

- Start command:
  - `python -m uvicorn mealmetric.core.app:create_app --factory`
- Python:
  - `3.12.x`
- Required environment variables:
  - see `backend/.env.example`
- Required network contract:
  - backend is an internal admin/system service
  - browser traffic must terminate at the frontend/BFF, not this backend
  - BFF requests must be HMAC-signed
  - admin-only surfaces must remain restricted at the network edge as well as in app auth

## Required probes

- Liveness:
  - `GET /livez`
  - expects `200 {"status":"live"}`
- Readiness:
  - `GET /readyz`
  - expects `200 {"status":"ready"}` only when the app can open a DB connection and run `SELECT 1`
- Operational DB health:
  - `GET /db/health`
  - admin-only, signed-BFF protected

## Required pre-deploy checks

- `python -m ruff check .`
- `python -m black --check .`
- `python -m mypy --strict src tests`
- `python -m pytest`

## Required migration checks

- Verify repo head:
  - `python -m alembic heads`
- Verify target DB revision:
  - `python tools/check_alembic_current.py`

## Required human-owned environment items

- TLS / reverse proxy / HTTPS termination
- firewall / network allowlists
- secrets management for `SECRET_KEY`, BFF signing keys, Stripe keys, DB credentials
- Prometheus scrape config and alert routing
- DB backup / restore execution
