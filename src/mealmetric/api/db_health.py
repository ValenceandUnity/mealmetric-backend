import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import require_roles, require_trusted_caller
from mealmetric.db.session import get_db
from mealmetric.models.user import Role

router = APIRouter(
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.ADMIN))]
)
logger = logging.getLogger("mealmetric.db")
db_dependency = Depends(get_db)


@router.get("/db/health", response_model=None)
def db_health(
    request: Request, db: Session | None = db_dependency
) -> JSONResponse | dict[str, str]:
    request_id = getattr(request.state, "request_id", "-")

    if db is None:
        return JSONResponse(
            status_code=503, content={"status": "error", "detail": "db_unavailable"}
        )

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("db health check failed", extra={"request_id": request_id})
        return JSONResponse(
            status_code=503, content={"status": "error", "detail": "db_unavailable"}
        )

    return {"status": "ok"}
