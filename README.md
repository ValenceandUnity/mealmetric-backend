# MealMetric Backend

Canonical deployment and operations docs live under [docs/deployment](c:/Users/valen/MealMetric/backend/docs/deployment/DEPLOYMENT_SOURCE_OF_TRUTH.md) and [docs/runbooks](c:/Users/valen/MealMetric/backend/docs/runbooks/DEPLOY.md).

## Local commands

- Install: `python -m pip install -e ".[dev]"`
- Tests: `python -m pytest`
- Lint: `python -m ruff check .`
- Type-check: `python -m mypy --strict src tests`
- Run API: `python -m uvicorn mealmetric.core.app:create_app --factory --reload`

## Endpoints

- `GET /health` legacy health alias
- `GET /livez` process liveness probe
- `GET /readyz` deployment readiness probe
- `GET /metrics` admin-only Prometheus metrics
- `GET /api/ping`

## Environment

- Copy [.env.example](c:/Users/valen/MealMetric/backend/.env.example) and set real values before startup.
- `SECRET_KEY` is required for `APP_ENV=staging` and `APP_ENV=production`.
- Signed BFF headers are the normal request contract. The legacy `X-MM-BFF-Key` path is explicitly insecure and ignored outside `APP_ENV=development` or `APP_ENV=test`.
