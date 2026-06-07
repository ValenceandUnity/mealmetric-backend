# Cross-Repo Contract Audit Template

## Scope

- PR or branch:
- Auditor:
- Date:

## Contract Boundaries

- frontend route or BFF contract reviewed:
- backend route or schema reviewed:
- auth/session interaction reviewed:

## Required Checks

- Browser does not call backend directly.
- BFF route shape still matches backend expectations.
- Signed BFF request semantics remain valid.
- No admin/internal contract was exposed to public browser flows.
- Role expectations remain aligned for `client`, `pt`, `vendor`, `admin`.

## Drift Checks

- request method drift
- path drift
- payload shape drift
- error mapping drift
- auth header/signature drift

## Evidence

- files reviewed
- tests reviewed
- mismatches found
- required follow-ups

