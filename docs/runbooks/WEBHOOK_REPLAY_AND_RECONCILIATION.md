# Webhook Replay And Reconciliation

1. Check protected metrics and logs for webhook failures.
2. Run admin reconciliation:
   - `POST /admin/payments/reconciliation/run`
3. Inspect failed or stale receipts:
   - `GET /admin/payments/webhooks`
   - `GET /admin/payments/webhooks/{stripe_event_id}`
4. Replay only the specific failed receipt you intend to retry:
   - `POST /admin/payments/webhooks/{stripe_event_id}/replay`
5. Re-run reconciliation and confirm the gap is cleared.
6. If the receipt stays failed, preserve the `stripe_event_id`, `request_id`, and `processing_error` for incident follow-up.
