# Commerce Hardening Checklist

## Purpose

S6 checklist for commerce flow hardening. This document uses the current MealMetric checkout, order, and Stripe webhook posture as the baseline.

## S6 Checklist

### Basket Snapshot

- Basket snapshot is persisted with the payment session.
- Snapshot fields are sufficient to reconstruct the order intent.
- Snapshot mutation after payment initiation is controlled or rejected.
- Tests cover valid and malformed snapshot handling.

### Stripe Webhook Signature

- `Stripe-Signature` is required for webhook processing.
- Invalid signatures are rejected.
- Missing signatures are rejected.
- Signed payload handling is covered by tests.

### Webhook Idempotency

- Duplicate webhook deliveries do not create duplicate business effects.
- Idempotency behavior is explicit in persistence/service code.
- Duplicate-delivery tests exist and remain passing.

### Order Creation

- Order creation from successful payment sessions is transactional.
- Failures during order-item persistence roll back the order.
- Basket snapshot and payment linkage remain consistent.
- Tests cover successful creation and rollback behavior.

### Payment Failure Tests

- Checkout/payment failure paths are covered by tests.
- Webhook ingress failure paths are covered by tests.
- Kill-switch or service-disabled behavior is covered where applicable.
- Error mapping remains intentional and documented.

## Review Notes

- Do not invent new checkout contracts from the frontend.
- Do not bypass the BFF for commerce UX.
- Do not weaken webhook validation for local convenience.

