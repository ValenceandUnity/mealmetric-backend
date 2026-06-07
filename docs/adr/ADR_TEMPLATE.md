# ADR Template

## Title

Short decision title.

## Status

Proposed | Accepted | Superseded | Rejected

## Date

`YYYY-MM-DD`

## Context

- What problem exists?
- What repo constraints already apply?
- Which architecture locks are relevant?

Required checks:

- Backend remains the system/admin service.
- Frontend/BFF remains the user interaction layer.
- Browser does not call backend directly.
- Signed BFF requests remain required unless the decision explicitly replaces them.
- Admin/internal surfaces remain protected.
- Roles remain `client`, `pt`, `vendor`, `admin`.

## Decision

Describe the decision in plain language.

## Consequences

- Positive outcomes
- Negative outcomes
- Migration cost
- Rollback path

## Security Review

- Does this change auth behavior?
- Does this affect BFF signing or trusted caller semantics?
- Does this expose admin/internal capability?
- Does this require new secrets or dependency approval?

## Alternatives Considered

- Option A
- Option B
- Option C

## Evidence

- code references
- tests
- docs
- rollout plan

