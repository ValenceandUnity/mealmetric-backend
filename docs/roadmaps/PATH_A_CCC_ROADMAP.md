# MealMetric — Path A (Fastest MVP) Roadmap — CCC v Layer 3

## Completed

### Phase 0 — CCC Foundation Layer (DONE)
- `src/` layout established
- Python `3.12.x` baseline
- FastAPI + sync SQLAlchemy (Path A)
- Alembic configured
- Structured JSON logging with `request_id`
- Prometheus `/metrics` endpoint
- Security middleware in place:
  - Rate limiter
  - Input size guard
  - Kill switch
- Baseline endpoints in place:
  - `/health`
  - `/metrics`
  - `/api/ping`
  - `/db/health`
- Quality gates configured and enforced (`black`, `ruff`, `mypy`, `pytest`, coverage gate)

### Phase B — Stripe Checkout Session (DONE)
- `POST /api/checkout/session` implemented
- Stripe Price IDs only (`price_...`), no `price_data`
- Error mapping implemented:
  - Invalid input -> `400`
  - Stripe/service failure -> `502`
- Kill switch blocks checkout route when enabled
- Tests added for success/failure/kill-switch behavior
- Coverage gate maintained (>= 90%)

## Upcoming Phases

### Phase C — Auth baseline (JWT) + roles
**Goal**
Establish identity, session security, and role-based authorization for core API surfaces.

**In-scope items**
- JWT issue/verify flow (access token baseline)
- User auth endpoints (login/refresh/logout semantics as defined)
- Role model and role checks in API dependencies
- Security config for token lifetimes and signing settings
- Tests for auth happy-path and denial-path behavior

**Explicit non-goals**
- OAuth/social login providers
- SSO/SAML enterprise integrations
- Fine-grained permissions UI

### Phase D — Vendor profile + admin approval gate
**Goal**
Introduce vendor onboarding with a controlled approval gate before vendor activation.

**In-scope items**
- Vendor profile domain model + CRUD baseline
- Vendor status lifecycle (`pending`, `approved`, `rejected`)
- Admin approval/rejection endpoints
- Guardrails so only approved vendors can publish/sell
- Tests for approval-state transitions and access control

**Explicit non-goals**
- KYC/AML provider integrations
- Complex document verification workflows
- Public vendor discovery UX

### Phase E — Vendor items CRUD
**Goal**
Enable approved vendors to manage catalog items required for selling bundles/orders.

**In-scope items**
- Item model and sync SQLAlchemy repository/service APIs
- Vendor-scoped CRUD endpoints
- Validation for price/availability fields
- Soft visibility control for inactive items
- Tests for CRUD behavior and tenant isolation

**Explicit non-goals**
- Advanced inventory forecasting
- Rich media pipeline/CDN processing
- Dynamic pricing engines

### Phase F — Bundles + market browse by ZIP
**Goal**
Provide customer-facing discovery of purchasable bundles filtered by ZIP.

**In-scope items**
- Bundle model linked to vendor items
- Bundle listing endpoint(s)
- ZIP-based filtering and basic sorting
- Read models optimized for browse responses
- Tests for filtering correctness and boundary cases

**Explicit non-goals**
- Geospatial radius optimization beyond ZIP filter
- Personalized recommendations
- Full-text search infrastructure

### Phase G — Orders model + checkout linkage
**Goal**
Create durable order records and connect checkout initiation to order lifecycle.

**In-scope items**
- Order domain model + persistence
- Checkout-to-order linkage fields (session reference)
- Pre-payment order creation state
- Basic order status progression model
- Tests for order creation and linkage integrity

**Explicit non-goals**
- Fulfillment orchestration workflows
- Refund/dispute automation
- Multi-vendor split settlement logic

### Phase H — Webhooks for payment confirmation
**Goal**
Move from optimistic checkout creation to authoritative payment confirmation.

**In-scope items**
- Stripe webhook endpoint with signature verification
- Event handling for checkout/payment success/failure
- Idempotent event processing strategy
- Order status updates driven by confirmed events
- Tests with signed webhook payload fixtures

**Explicit non-goals**
- Broad event fan-out bus architecture
- Non-Stripe payment providers
- Real-time notification delivery system

### Phase I — Vendor pickup dashboard
**Goal**
Allow vendors to manage pickup-ready orders operationally.

**In-scope items**
- Vendor-facing order queue endpoints
- Status transitions for pickup workflow
- Simple filters (date/status/ZIP as applicable)
- Audit trail fields for operational actions
- Tests for workflow transitions and authorization

**Explicit non-goals**
- Route optimization for couriers
- Driver assignment features
- Complex BI dashboards

### Phase J — Minimal admin panel API
**Goal**
Expose minimal administrative APIs for platform oversight and moderation.

**In-scope items**
- Admin endpoints for vendor/order oversight
- Health/ops readouts needed for manual operations
- Moderation actions and status controls
- Role-gated access protections
- Tests for admin-only access and action effects

**Explicit non-goals**
- Full admin frontend implementation
- Complex analytics warehouse integrations
- Automated policy engine

### Phase K — Operational testing cycle
**Goal**
Harden reliability and release confidence across functional and non-functional criteria.

**In-scope items**
- End-to-end scenario matrix for key flows
- Failure-mode and rollback drills
- Performance smoke checks and baseline SLO tracking
- Security regression checklist execution
- Release readiness checklist and sign-off criteria

**Explicit non-goals**
- Large-scale chaos engineering platform
- Full load-testing infrastructure buildout
- Multi-region active-active deployment redesign