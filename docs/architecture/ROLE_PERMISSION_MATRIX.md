# Role Permission Matrix

## Purpose

This matrix defines the allowed responsibility split for `client`, `pt`, `vendor`, and `admin` within the existing MealMetric architecture.

## Architecture Reminder

- Backend = system/admin service.
- Frontend/BFF = user interaction layer.
- Browser never calls backend directly.
- Signed BFF requests are required for normal operation.
- Admin/internal surfaces stay protected.

## Matrix

| Capability Area | client | pt | vendor | admin | Enforcement Layer |
| --- | --- | --- | --- | --- | --- |
| Authenticate through BFF | Yes | Yes | Yes | Yes | Frontend entry, backend validation |
| Call Next.js BFF routes | Yes | Yes | Yes | Yes | Frontend |
| Call backend directly from browser | No | No | No | No | Architecture lock |
| Read own user-facing data through BFF | Yes | Yes | Yes | Yes | BFF plus backend authz |
| Access PT client workspace | No | Yes | No | Yes | Backend role checks |
| Access vendor management surfaces | No | No | Yes | Yes | Backend role checks |
| Access admin/internal surfaces | No | No | No | Yes | Backend role checks |
| Trigger checkout/order flows through BFF | Yes | No direct client checkout ownership unless explicitly supported | No | Admin oversight only | BFF plus backend domain logic |
| View operational metrics | Scoped | Scoped | Scoped | Full | Backend role checks |
| Manage platform-wide users, vendors, orders | No | No | No | Yes | Backend admin routes |

## Notes By Role

### client

- Consumes personal product flows through BFF routes.
- Must never receive direct access to backend admin or internal APIs.

### pt

- Operates within PT-scoped client workflows only.
- Must not gain implicit admin powers through convenience endpoints.

### vendor

- Operates within vendor-scoped surfaces only.
- Vendor operations remain restricted to existing backed routes and workflows.

### admin

- Owns protected internal oversight surfaces.
- Admin routes are not general browser-public APIs and remain protected even when surfaced through tooling.

## Review Checklist

- Does the route map to one of the four approved roles?
- Is authorization enforced in the backend, not only in UI chrome?
- Does the change preserve the BFF boundary?
- Does the change expose any admin/internal capability outside protected surfaces?

