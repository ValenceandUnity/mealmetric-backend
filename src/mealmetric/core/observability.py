from prometheus_client import Counter, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "mealmetric_http_requests_total",
    "HTTP requests processed",
    ["route", "method", "status"],
)

STRIPE_WEBHOOK_RECEIVED_TOTAL = Counter(
    "mealmetric_stripe_webhook_received_total",
    "Stripe webhooks received",
    ["event_type"],
)

STRIPE_WEBHOOK_PROCESSED_TOTAL = Counter(
    "mealmetric_stripe_webhook_processed_total",
    "Stripe webhook processing outcomes",
    ["event_type", "status"],
)

STRIPE_WEBHOOK_PROCESSING_SECONDS = Histogram(
    "mealmetric_stripe_webhook_processing_seconds",
    "Stripe webhook processing latency in seconds",
    ["event_type", "status"],
)

PAYMENT_LIFECYCLE_TRANSITIONS_TOTAL = Counter(
    "mealmetric_payment_lifecycle_transitions_total",
    "Payment lifecycle transitions applied",
    ["from_status", "to_status", "source"],
)

ORDER_CREATED_TOTAL = Counter(
    "mealmetric_order_created_total",
    "Orders created from successful payment sessions",
)

ORDER_DUPLICATE_SKIPPED_TOTAL = Counter(
    "mealmetric_order_duplicate_skipped_total",
    "Order create attempts skipped due to existing order",
)

ORDER_CREATION_FAILED_TOTAL = Counter(
    "mealmetric_order_creation_failed_total",
    "Order creation failures",
    ["reason"],
)

ORDER_CREATION_WEBHOOK_FAILURE_TOTAL = Counter(
    "mealmetric_order_creation_webhook_failure_total",
    "Order creation failures during checkout.session.completed webhook processing",
)

AUTH_FAILURES_TOTAL = Counter(
    "mealmetric_auth_failures_total",
    "Authentication failures observed",
    ["reason"],
)

AUTH_FAILURE_ALERTS_TOTAL = Counter(
    "mealmetric_auth_failure_alerts_total",
    "Authentication failure alerts emitted",
)
