from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from mealmetric.db.session import get_engine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "live"}


@router.get("/readyz", response_model=None)
def readyz() -> JSONResponse | dict[str, str]:
    engine = get_engine()
    if engine is None:
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "detail": "db_unavailable"}
        )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "detail": "db_unavailable"}
        )

    return {"status": "ready"}
