# Phase B — Stripe Checkout MVP (Server-side only)

## Scope Constraints
- Test mode only
- One-time payments only
- Stripe Price IDs only (no `price_data`)
- Pickup-only
- No webhooks
- No orders DB model/writes
- No auth
- No frontend
- No async SQLAlchemy
- No migrations
- No middleware behavior changes

## What Was Built
- Added settings keys: `STRIPE_SECRET_KEY`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`
- Added Stripe service: `src/mealmetric/services/stripe_service.py`
- Added endpoint: `POST /api/checkout/session`
- Added tests:
  - `tests/test_checkout_success_mocked.py`
  - `tests/test_checkout_stripe_failure.py`
  - `tests/test_checkout_kill_switch_blocked.py`

## Security / CCC Notes
- Structured JSON logging with `request_id` is present in the existing stack
- Kill switch blocks `/api/checkout/session` when enabled (route is not allowlisted)
- No Stripe secret values are logged

## Verification
- `python -m ruff check .` passed
- `python -m black --check .` passed
- `python -m mypy .` passed
- `python -m pytest` passed
- Total coverage: **95.87%**

## Example cURL
```bash
curl -X POST "http://127.0.0.1:8000/api/checkout/session" \
  -H "Content-Type: application/json" \
  -d "{\"price_id\":\"price_1234567890\",\"quantity\":1}"
```