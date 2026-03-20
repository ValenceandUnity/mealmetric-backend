import logging
from collections.abc import Generator
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mealmetric.core.settings import get_settings

_ENGINE: Engine | None = None
_ENGINE_KEY: tuple[str | None, bool, int] | None = None
logger = logging.getLogger("mealmetric.db")


def _build_engine(database_url: str, db_echo: bool, timeout_seconds: int) -> Engine:
    connect_args: dict[str, Any] = {}
    if database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = timeout_seconds

    return create_engine(
        database_url,
        echo=db_echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine() -> Engine | None:
    global _ENGINE
    global _ENGINE_KEY

    settings = get_settings()
    key = (settings.database_url, settings.db_echo, settings.db_connect_timeout_seconds)
    if key == _ENGINE_KEY:
        return _ENGINE

    if _ENGINE is not None:
        _ENGINE.dispose()

    if not settings.database_url:
        _ENGINE = None
    else:
        _ENGINE = _build_engine(
            settings.database_url,
            settings.db_echo,
            settings.db_connect_timeout_seconds,
        )

    _ENGINE_KEY = key
    return _ENGINE


def get_db(request: Request) -> Generator[Session | None, None, None]:
    request_id = getattr(request.state, "request_id", "-")
    try:
        engine = get_engine()
    except Exception:
        logger.exception(
            "database session setup failed",
            extra={"request_id": request_id, "stage": "get_engine"},
        )
        yield None
        return

    if engine is None:
        yield None
        return

    try:
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)
        session = session_local()
    except Exception:
        logger.exception(
            "database session setup failed",
            extra={"request_id": request_id, "stage": "session_open"},
        )
        yield None
        return

    try:
        yield session
    finally:
        try:
            session.close()
        except Exception:
            logger.exception(
                "database session close failed",
                extra={"request_id": request_id, "stage": "session_close"},
            )


def get_db_session() -> Generator[Session | None, None, None]:
    class _RequestState:
        request_id = "-"

    class _Request:
        state = _RequestState()

    yield from get_db(_Request())  # type: ignore[arg-type]
