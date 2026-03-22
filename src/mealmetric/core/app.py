import logging

from fastapi import FastAPI, Request

from mealmetric.api.admin import router as admin_router
from mealmetric.api.admin_orders import router as admin_orders_router
from mealmetric.api.admin_vendors import router as admin_vendors_router
from mealmetric.api.bff import router as bff_router
from mealmetric.api.checkout import router as checkout_router
from mealmetric.api.client_bookmarks import router as client_bookmarks_router
from mealmetric.api.client_meal_plan_recommendations import (
    router as client_meal_plan_recommendations_router,
)
from mealmetric.api.client_meal_plans import router as client_meal_plans_router
from mealmetric.api.client_metrics import router as client_metrics_router
from mealmetric.api.client_orders import router as client_orders_router
from mealmetric.api.client_subscriptions import router as client_subscriptions_router
from mealmetric.api.client_training import router as client_training_router
from mealmetric.api.db_health import router as db_health_router
from mealmetric.api.health import router as health_router
from mealmetric.api.metrics import router as metrics_router
from mealmetric.api.ping import router as ping_router
from mealmetric.api.pt_meal_plan_recommendations import (
    router as pt_meal_plan_recommendations_router,
)
from mealmetric.api.pt_meal_plans import router as pt_meal_plans_router
from mealmetric.api.pt_metrics import router as pt_metrics_router
from mealmetric.api.pt_training import router as pt_training_router
from mealmetric.api.routes.auth import protected_router as protected_auth_router
from mealmetric.api.routes.auth import public_router as public_auth_router
from mealmetric.api.vendor_portal import router as vendor_portal_router
from mealmetric.api.webhooks import router as webhook_router
from mealmetric.core.logging import setup_logging
from mealmetric.core.middleware.input_size_guard import InputSizeGuardMiddleware
from mealmetric.core.middleware.kill_switch import KillSwitchMiddleware
from mealmetric.core.middleware.rate_limiter import RateLimiterMiddleware
from mealmetric.core.middleware.request_id import RequestIDMiddleware, get_request_id
from mealmetric.core.observability import HTTP_REQUESTS_TOTAL
from mealmetric.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="MealMetric API")

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(InputSizeGuardMiddleware, max_request_bytes=settings.max_request_bytes)
    app.add_middleware(RateLimiterMiddleware, rate_per_second=settings.rate_limit_rps)
    app.add_middleware(KillSwitchMiddleware, enabled=settings.kill_switch_enabled)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(db_health_router)
    app.include_router(ping_router)
    app.include_router(bff_router)
    app.include_router(checkout_router)
    app.include_router(admin_router)
    app.include_router(admin_orders_router)
    app.include_router(admin_vendors_router)
    app.include_router(webhook_router)
    app.include_router(pt_training_router)
    app.include_router(pt_metrics_router)
    app.include_router(pt_meal_plans_router)
    app.include_router(pt_meal_plan_recommendations_router)
    app.include_router(client_training_router)
    app.include_router(client_metrics_router)
    app.include_router(client_orders_router)
    app.include_router(client_subscriptions_router)
    app.include_router(client_bookmarks_router)
    app.include_router(client_meal_plans_router)
    app.include_router(client_meal_plan_recommendations_router)
    app.include_router(vendor_portal_router)
    app.include_router(public_auth_router, prefix="/auth", tags=["auth"])
    app.include_router(protected_auth_router, prefix="/auth", tags=["auth"])

    logger = logging.getLogger("mealmetric.http")

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            response = await call_next(request)
        except Exception:
            request_id = getattr(request.state, "request_id", get_request_id())
            logger.exception(
                "unhandled request exception",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            raise
        route_obj = request.scope.get("route")
        route = getattr(route_obj, "path", "unmatched")
        HTTP_REQUESTS_TOTAL.labels(
            route=route, method=request.method, status=str(response.status_code)
        ).inc()
        request_id = getattr(request.state, "request_id", get_request_id())
        logger.info("request complete", extra={"request_id": request_id})
        return response

    return app
