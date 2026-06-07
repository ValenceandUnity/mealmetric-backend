# Dependency Acceptance Layer

## Purpose

MealMetric Phase 0 adopts a Dependency Acceptance Layer (DAL).

Definition:

- No new dependency is accepted unless it is explicitly approved.
- This applies to backend, frontend, build, lint, test, observability, auth, and design-system dependencies.

## Default Rule

- A PR must not add a dependency by default.
- "Small" or "common" is not approval.
- Temporary, dev-only, or codegen-only packages still require approval.

## Approval Inputs

A dependency request must explain:

- why the current stack cannot reasonably solve the problem
- why built-in platform capability is insufficient
- security impact
- maintenance cost
- rollback/removal path
- effect on bundle size, startup, and operational complexity

## Review Gates

A dependency may be considered only if all are true:

- The dependency does not violate the BFF architecture.
- It does not change production auth behavior unless separately approved.
- It does not require browser-direct backend access.
- It does not weaken admin/internal protections.
- It has a clear owner and test plan.

## ADR Requirement

Use an ADR before approval when the dependency affects:

- auth or session management
- request signing or BFF transport
- data-access architecture
- payment or webhook processing
- core frontend runtime patterns

## Phase 0 Position

- React 19 and Next 15 are already the approved frontend baseline in this repo.
- FastAPI plus sync SQLAlchemy remains the approved backend baseline in this repo.
- This DAL does not authorize any new package for the mobile UI rebuild.

