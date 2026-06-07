# Auth Session Hardening Checklist

## Purpose

Track Phase 0 and later auth/session hardening without changing production behavior during the documentation phase.

## P0

### Remove `X-MM-BFF-Key` from production signed requests

- Confirm signed request verification remains the canonical contract.
- Confirm production requests no longer depend on `X-MM-BFF-Key`.
- Preserve any required development/test compatibility intentionally.
- Verify no browser code receives additional secrets as a side effect.
- Add regression tests for signed requests without legacy key reliance.

## P1

### Session refresh design

- Define refresh entrypoint through the BFF, not direct browser-to-backend calls.
- Define token/session expiry behavior.
- Define refresh failure and forced logout behavior.
- Define revocation interaction with refresh.
- Define role revalidation expectations after refresh.
- Define rollout and rollback strategy.

## Always Check

- logout semantics remain safe
- auth cookies/session storage are scoped intentionally
- role checks remain backend enforced
- admin/internal surfaces remain protected

