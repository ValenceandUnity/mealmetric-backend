# Feature Flags

## Purpose

This document defines release expectations for feature-gated changes that touch core UX or risk-sensitive flows.

## Required Flag

### `MM_FLAG_MOBILE_UI_REBUILD`

- Purpose: gates the future mobile UI rebuild.
- Default: off until explicitly enabled by release control.
- Scope: frontend/BFF presentation and UX rollout only.
- Non-scope: does not authorize backend contract invention, direct browser-to-backend calls, or auth weakening.

## Flag Rules

- A feature flag must not bypass backend authorization.
- A feature flag must not expose admin/internal surfaces accidentally.
- A feature flag must not create an alternate direct-call path from browser to backend.
- A feature flag must have a documented rollback state.

## Release Checklist

- Flag name is documented before rollout.
- Default state is defined.
- Target surfaces are defined.
- Exit criteria for removing the flag are defined.
- Security-sensitive interactions were reviewed.

