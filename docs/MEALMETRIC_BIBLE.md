# MealMetric Bible

## Purpose

This document is the Phase 0 source of truth for standards, architecture locks, security boundaries, and review posture across MealMetric. Future PRs must treat these rules as constraints, not suggestions.

## Architecture Locks

- Backend is the system and admin service.
- Frontend BFF is the user interaction layer.
- Browser code never calls backend services directly.
- Browser requests terminate at Next.js BFF routes under `frontend/app/api/*`.
- Backend routes that serve product data or user actions require trusted BFF calls.
- Signed BFF requests are required for normal operation.
- Legacy `X-MM-BFF-Key` fallback is explicitly insecure and is allowed only in `APP_ENV=development` or `APP_ENV=test`.
- Admin and internal surfaces must remain protected and must not be exposed as public browser-direct APIs.

## Role Model

MealMetric currently recognizes these application roles:

- `client`
- `pt`
- `vendor`
- `admin`

Role-aware UX is allowed in the frontend. Role enforcement remains a backend responsibility.

## Layer Responsibilities

### Backend

- Owns auth verification, authorization, persistence, business rules, admin/internal operations, and payment/webhook handling.
- Remains the source of truth for order, payment, role, and audit state.
- May expose internal/admin routes that are not available to browser clients.

### Frontend / BFF

- Owns browser session handling, route composition, UX state, and translation from browser requests to backend requests.
- Must preserve the BFF boundary for every user-facing flow.
- Must not shift product logic into browser-only code when that logic belongs in the backend.

### Browser

- Calls local Next.js BFF routes only.
- Must not hold backend trust secrets.
- Must not bypass signed BFF transport, even for mobile-oriented rebuild work.

## Current Stack Baseline

- Frontend baseline: Next.js 15 App Router on React 19.
- Backend baseline: FastAPI plus SQLAlchemy sync session pattern.
- No Phase 0 document authorizes a dependency addition.

## CCC Language Update

MealMetric CCC guidance for the current frontend stack:

- React 19 and Next 15 are the approved frontend runtime baseline.
- App Router route handlers under `frontend/app/api/*` are the BFF boundary.
- Server and client components may support the UI, but neither may introduce browser-direct backend access.
- Mobile UI rebuild work must stay inside the existing Next 15 plus BFF architecture.
- Unsupported backend areas must be represented as blocked, placeholder, or deferred, not invented in the browser.

## Data Access Standard

SQLAlchemy sync access is allowed in MealMetric.

Interpretation rule:

- The codebase may continue using the current sync SQLAlchemy path.
- The async rule does not ban sync SQLAlchemy by itself.
- The actual restriction is: do not perform blocking database or network work inside async code paths in a way that violates the service boundary or event-loop safety expectations.
- If async database work is introduced later, it requires an explicit ADR and review against the dependency acceptance layer.

## Mobile UI Rebuild Foundation

Phase 0 authorizes standards and documentation only.

- Do not build the mobile UI in this phase.
- Do not bypass the BFF pattern for mobile work.
- Do not treat mobile as a reason to expose backend APIs directly to browser code.
- Use feature flags, review templates, and risk registers before implementation.

## Mandatory Feature Flag

`MM_FLAG_MOBILE_UI_REBUILD`

Definition:

- Purpose: gates future Mobile UI rebuild work at rollout time.
- Default state for implementation planning: off unless explicitly enabled by release controls.
- Scope: frontend/BFF experience changes only; it does not authorize backend contract drift.
- Prohibited use: it must not be used to bypass auth, BFF signing, or admin/internal protections.

## Security Hardening Priorities

### P0

- Remove `X-MM-BFF-Key` from production signed requests.

Clarification:

- This is a hardening task for future implementation.
- Phase 0 does not change production behavior.
- Signed request verification remains the primary contract today.

### P1

- Design a session refresh flow that preserves the BFF boundary and does not move token lifecycle handling into browser-direct backend calls.

## PR Enforcement Rules

Reject or block a PR if it does any of the following without explicit approval and ADR coverage:

- Adds a new dependency.
- Makes browser code call the backend directly.
- Weakens trusted caller verification.
- Exposes admin/internal routes to direct browser use.
- Invents new backend contracts only to satisfy frontend convenience.
- Changes auth behavior during Phase 0 documentation work.

