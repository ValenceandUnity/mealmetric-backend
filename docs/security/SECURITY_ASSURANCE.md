# Security Assurance

## Purpose

This document records the current MealMetric security posture that future PRs must preserve unless an approved ADR says otherwise.

## Assured Boundaries

- Browser code never calls backend services directly.
- Next.js BFF is the mandatory user interaction boundary.
- Backend trusted-caller verification protects backend routes intended for BFF-mediated access.
- Signed BFF requests are the normal trusted-caller contract.
- Admin and internal surfaces are protected and must remain non-public.

## Current Trusted Caller Posture

Baseline from current code:

- Frontend trusted backend headers include `X-MM-BFF-Caller`, `X-MM-BFF-Timestamp`, and `X-MM-BFF-Signature`.
- Current helper also sends `X-MM-BFF-Key`.
- Backend treats signed requests as the normal contract.
- Backend accepts legacy `X-MM-BFF-Key` fallback only when insecure legacy mode is enabled and `APP_ENV` is `development` or `test`.

Implication:

- Production hardening is already oriented around signed requests.
- The remaining Phase 0 gap is removal of `X-MM-BFF-Key` from production signed requests once implemented safely.

## Auth Hardening Roadmap

### P0

- Remove `X-MM-BFF-Key` from production signed requests.

Requirements:

- No production regression in trusted caller verification.
- Preserve compatibility strategy explicitly for development/test as needed.
- Confirm no browser-visible secret expansion.

### P1

- Design session refresh semantics that preserve BFF mediation.

Requirements:

- Browser should not refresh directly against backend auth endpoints.
- Refresh lifecycle must preserve revocation, role validation, and session integrity.
- Rollout must define failure states, expiry behavior, and logout invalidation semantics.

## SQLAlchemy / Async Safety Position

- Sync SQLAlchemy remains an approved backend path.
- The async rule means no blocking operations should be introduced inside async code paths in a way that undermines reliability or event-loop expectations.
- A PR must not claim that sync SQLAlchemy is banned by default; it is the current allowed architecture.

## Admin and Internal Surface Protection

- `/metrics` and similar internal/admin routes remain protected.
- Future admin tools must keep backend authorization checks in place even if the frontend adds convenience screens.
- No PR may weaken route protection for debugging convenience.

## Review Evidence Expectations

Security-sensitive PRs should attach evidence for:

- trusted caller contract preservation
- role authorization behavior
- session and logout behavior
- webhook signature validation where relevant
- failure-mode tests for denied access

