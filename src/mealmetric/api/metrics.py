from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.models.user import Role

router = APIRouter(
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.ADMIN))]
)


@router.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
