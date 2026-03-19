import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mealmetric.core.settings import get_settings
from mealmetric.db.session import get_db
from mealmetric.services.stripe_webhook_service import (
    StripeWebhookIngressError,
    StripeWebhookIngressService,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("mealmetric.webhooks.stripe")
DBSessionDep = Annotated[Session | None, Depends(get_db)]


class StripeWebhookResponse(BaseModel):
    received: bool
    duplicate: bool = False


@router.post("/stripe", response_model=StripeWebhookResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
    db: DBSessionDep = None,
) -> StripeWebhookResponse:
    settings = get_settings()
    request_id = getattr(request.state, "request_id", "-")

    if not settings.stripe_webhooks_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhooks are disabled.",
        )

    if stripe_signature is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header.",
        )

    payload = await request.body()
    service = StripeWebhookIngressService(settings)

    try:
        event = service.verify_and_parse_event(payload=payload, signature=stripe_signature)
        result = service.ingest_event(
            session=db, event=event, payload=payload, request_id=request_id
        )
    except StripeWebhookIngressError as exc:
        code = str(exc)
        if code == "invalid_stripe_signature":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stripe signature.",
            ) from exc
        if code == "db_unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook ingress unavailable.",
            ) from exc
        logger.error("stripe webhook ingress misconfigured", extra={"request_id": request_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook ingress unavailable.",
        ) from exc

    logger.info(
        "stripe webhook accepted request_id=%s",
        request_id,
        extra={
            "request_id": request_id,
            "event_id": result.event_id,
            "duplicate": result.duplicate,
            "mode": result.mode,
        },
    )
    return StripeWebhookResponse(received=True, duplicate=result.duplicate)
