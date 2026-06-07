# Frontend Audit Template

## Scope

- PR or branch:
- Auditor:
- Date:

## Architecture Lock Checks

- Browser code calls only local BFF routes.
- No browser code calls backend services directly.
- Mobile UI work stays inside Next.js 15 App Router plus BFF constraints.
- Unsupported backend areas are blocked or placeholder, not invented.

## Role and Session Checks

- Role-aware UI matches `client`, `pt`, `vendor`, `admin`.
- UI-only gating is not the only authorization control.
- Session handling remains mediated by the BFF.

## Feature Flag Checks

- `MM_FLAG_MOBILE_UI_REBUILD` behavior documented if the change is related to the rebuild.
- Flag default and rollback posture are clear.

## Evidence

- routes reviewed
- BFF handlers reviewed
- tests run
- open UX risks
- open security risks

