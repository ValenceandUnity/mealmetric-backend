# Deploy

1. Run:
   - `python -m ruff check .`
   - `python -m black --check .`
   - `python -m mypy --strict src tests`
   - `python -m pytest`
2. Verify target DB revision:
   - `python tools/check_alembic_current.py`
3. If DB is behind repo heads, run:
   - `python -m alembic upgrade heads`
   - Current workflow note:
   - the migration graph currently has multiple heads
   - local rebuilds and deployments should target all heads
   - a future merge migration may return the repo to a single-head workflow
4. Start the backend with:
   - `python -m uvicorn mealmetric.core.app:create_app --factory`
5. Verify probes:
   - `GET /livez` returns `200`
   - `GET /readyz` returns `200`
6. Verify admin metrics from the trusted network path:
   - `GET /metrics`
