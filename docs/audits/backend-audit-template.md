# Backend Audit Template

## Scope

- PR or branch:
- Auditor:
- Date:

## Architecture Lock Checks

- Backend remains the system/admin service.
- Browser does not call backend directly.
- Trusted BFF caller protections remain intact.
- Admin/internal surfaces remain protected.
- Role checks still support `client`, `pt`, `vendor`, `admin`.

## Data Access Checks

- Sync SQLAlchemy use is intentional and remains within the approved architecture.
- No blocking work was added carelessly inside async code.
- New repos/services do not invent alternate access paths around current controls.

## Security Checks

- auth behavior changed? if yes, link ADR and tests
- trusted caller verification changed? if yes, explain
- session/logout behavior changed? if yes, explain
- admin route protections changed? if yes, explain

## Evidence

- files reviewed
- tests run
- open risks
- follow-up items

