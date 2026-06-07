# Mobile UI Rebuild Risk Register

## Purpose

Track known risks for the future mobile UI rebuild while preserving the current MealMetric architecture.

## Governing Flag

- `MM_FLAG_MOBILE_UI_REBUILD`

## Risks

| ID | Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- | --- |
| MUR-1 | Rebuild pressure causes browser-direct backend calls | High | Medium | Enforce BFF-only rule in reviews and audits |
| MUR-2 | UI work invents unsupported backend contracts | High | Medium | Require placeholder/blocked states instead of invented flows |
| MUR-3 | Mobile-specific auth shortcuts weaken session security | High | Medium | Use auth/session hardening checklist and ADR review |
| MUR-4 | Rebuild expands dependency surface without approval | Medium | Medium | Enforce DAL before any package addition |
| MUR-5 | Role boundaries blur in shared mobile shell | High | Medium | Audit against `client`, `pt`, `vendor`, `admin` matrix |
| MUR-6 | Admin/internal surfaces leak into public UX | High | Low | Keep admin/internal protection as a non-negotiable lock |

## Exit Criteria Before Implementation

- Architecture locks are acknowledged in the active implementation PR.
- Feature flag plan is documented.
- Audit templates are attached to the implementation workflow.
- No dependency additions occur without approval.
- No auth behavior changes occur without explicit approval and design review.

