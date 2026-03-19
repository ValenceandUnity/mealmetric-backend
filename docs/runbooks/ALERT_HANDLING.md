# Alert Handling

## Auth failure alerts

1. Check the alert source for the affected subject and time window.
2. Review structured logs for `mealmetric.auth` and the matching `request_id`.
3. Inspect the persisted tracker state in `auth_failure_trackers`.
4. Confirm whether failures are expected bad credentials, abuse, or integration breakage.
5. If needed, revoke the affected user session set by forcing logout through the app flow.

## Webhook or reconciliation alerts

1. Review `/admin/payments/reconciliation/run`.
2. Inspect the persisted webhook receipt and `processing_error`.
3. Replay only after identifying whether the original failure cause is resolved.

## Probe alerts

1. `livez` failing means process/runtime failure.
2. `readyz` failing means the service cannot safely take traffic, usually due to DB reachability.
