from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.api.schemas.admin_payments import (
    AdminReconciliationPaymentMismatch,
    AdminReconciliationReportResponse,
    AdminReconciliationSubscriptionMismatch,
    AdminReconciliationWebhookMismatch,
    AdminWebhookEventDetail,
    AdminWebhookEventListResponse,
    AdminWebhookEventSummary,
    AdminWebhookReplayResponse,
)
from mealmetric.api.schemas.subscriptions import (
    SubscriptionListResponse,
    SubscriptionMealPlanRead,
    SubscriptionRead,
)
from mealmetric.core.settings import get_settings
from mealmetric.db.session import get_db
from mealmetric.models.stripe_webhook_event import StripeWebhookEvent, WebhookProcessingStatus
from mealmetric.models.subscription import MealPlanSubscriptionStatus
from mealmetric.models.user import Role
from mealmetric.services.reconciliation_service import ReconciliationReport, ReconciliationService
from mealmetric.services.stripe_webhook_service import (
    StripeWebhookIngressError,
    StripeWebhookIngressService,
)
from mealmetric.services.subscription_service import (
    SubscriptionListView,
    SubscriptionService,
    SubscriptionView,
)

router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.ADMIN))],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]


@router.get("/ping")
def admin_ping() -> dict[str, bool]:
    return {"ok": True}


def _to_event_summary(event: StripeWebhookEvent) -> AdminWebhookEventSummary:
    return AdminWebhookEventSummary(
        stripe_event_id=event.stripe_event_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
        payment_session_id=event.payment_session_id,
        payload_sha256=event.payload_sha256,
        request_id=event.request_id,
        processing_error=event.processing_error,
        received_at=event.received_at,
        processed_at=event.processed_at,
    )


def _to_subscription_read(view: SubscriptionView) -> SubscriptionRead:
    return SubscriptionRead(
        id=view.id,
        stripe_subscription_id=view.stripe_subscription_id,
        stripe_customer_id=view.stripe_customer_id,
        client_user_id=view.client_user_id,
        meal_plan_id=view.meal_plan_id,
        status=view.status,
        billing_interval=view.billing_interval,
        current_period_start=view.current_period_start,
        current_period_end=view.current_period_end,
        cancel_at_period_end=view.cancel_at_period_end,
        canceled_at=view.canceled_at,
        latest_invoice_id=view.latest_invoice_id,
        latest_invoice_status=view.latest_invoice_status,
        latest_stripe_event_id=view.latest_stripe_event_id,
        last_invoice_paid_at=view.last_invoice_paid_at,
        last_invoice_failed_at=view.last_invoice_failed_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
        meal_plan=(
            SubscriptionMealPlanRead(
                id=view.meal_plan.id,
                vendor_id=view.meal_plan.vendor_id,
                slug=view.meal_plan.slug,
                name=view.meal_plan.name,
            )
            if view.meal_plan is not None
            else None
        ),
    )


def _to_subscription_list_response(view: SubscriptionListView) -> SubscriptionListResponse:
    items = [_to_subscription_read(item) for item in view.items]
    return SubscriptionListResponse(items=items, count=len(items))


def _to_reconciliation_report_response(
    report: ReconciliationReport,
) -> AdminReconciliationReportResponse:
    return AdminReconciliationReportResponse(
        generated_at=report.generated_at,
        stale_window_seconds=report.stale_window_seconds,
        payment_sessions_missing_orders=[
            AdminReconciliationPaymentMismatch(
                payment_session_id=item.payment_session_id,
                checkout_session_id=item.checkout_session_id,
                payment_status=item.payment_status.value,
            )
            for item in report.payment_sessions_missing_orders
        ],
        webhook_processing_gaps=[
            AdminReconciliationWebhookMismatch(
                stripe_event_id=item.stripe_event_id,
                event_type=item.event_type,
                processing_status=item.processing_status,
                received_at=item.received_at,
                processing_error=item.processing_error,
            )
            for item in report.webhook_processing_gaps
        ],
        subscriptions_missing_lifecycle_linkage=[
            AdminReconciliationSubscriptionMismatch(
                subscription_id=item.subscription_id,
                stripe_subscription_id=item.stripe_subscription_id,
                status=item.status,
            )
            for item in report.subscriptions_missing_lifecycle_linkage
        ],
    )


@router.get("/payments/webhooks", response_model=AdminWebhookEventListResponse)
def list_payment_webhooks(
    db: DBSessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    processing_status: WebhookProcessingStatus | None = None,
) -> AdminWebhookEventListResponse:
    service = StripeWebhookIngressService(get_settings())
    try:
        events = service.list_webhook_events(
            session=db,
            limit=limit,
            processing_status=processing_status,
        )
    except StripeWebhookIngressError as exc:
        if str(exc) == "db_unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db_unavailable",
            ) from exc
        raise
    items = [_to_event_summary(event) for event in events]
    return AdminWebhookEventListResponse(items=items, count=len(items))


@router.get("/subscriptions", response_model=SubscriptionListResponse)
def list_subscriptions(
    db: DBSessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    client_user_id: UUID | None = None,
    subscription_status: Annotated[MealPlanSubscriptionStatus | None, Query(alias="status")] = None,
) -> SubscriptionListResponse:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    service = SubscriptionService(db)
    view = service.list_for_admin(
        limit=limit,
        offset=offset,
        client_user_id=client_user_id,
        status=subscription_status,
    )
    return _to_subscription_list_response(view)


@router.post(
    "/payments/reconciliation/run",
    response_model=AdminReconciliationReportResponse,
)
def run_payment_reconciliation(
    db: DBSessionDep,
    stale_window_seconds: Annotated[int, Query(ge=60, le=86_400)] = 900,
) -> AdminReconciliationReportResponse:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="db_unavailable",
        )
    report = ReconciliationService(db).run(stale_window_seconds=stale_window_seconds)
    return _to_reconciliation_report_response(report)


@router.get("/payments/webhooks/{stripe_event_id}", response_model=AdminWebhookEventDetail)
def get_payment_webhook(
    stripe_event_id: str,
    db: DBSessionDep,
) -> AdminWebhookEventDetail:
    service = StripeWebhookIngressService(get_settings())
    try:
        event = service.get_webhook_event(session=db, stripe_event_id=stripe_event_id)
    except StripeWebhookIngressError as exc:
        if str(exc) == "db_unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db_unavailable",
            ) from exc
        raise

    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook_event_not_found")

    return AdminWebhookEventDetail(
        **_to_event_summary(event).model_dump(),
        payload=event.payload,
    )


@router.post(
    "/payments/webhooks/{stripe_event_id}/replay",
    response_model=AdminWebhookReplayResponse,
)
def replay_payment_webhook(
    stripe_event_id: str,
    request: Request,
    db: DBSessionDep,
) -> AdminWebhookReplayResponse:
    service = StripeWebhookIngressService(get_settings())
    request_id = getattr(request.state, "request_id", "-")
    try:
        result = service.replay_webhook_event(
            session=db,
            stripe_event_id=stripe_event_id,
            request_id=request_id,
        )
    except StripeWebhookIngressError as exc:
        if str(exc) == "db_unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db_unavailable",
            ) from exc
        raise

    if result.outcome == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook_event_not_found")

    return AdminWebhookReplayResponse(
        stripe_event_id=result.event_id,
        outcome=result.outcome,
        processing_status=result.processing_status,
        detail=result.detail,
    )
