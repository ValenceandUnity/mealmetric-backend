import json
import logging
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mealmetric.core.app import create_app
from mealmetric.core.logging import JsonFormatter
from mealmetric.core.settings import get_settings


def test_json_formatter_includes_exception_details() -> None:
    formatter = JsonFormatter()
    logger = logging.getLogger("mealmetric.test")

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logger.makeRecord(
            name="mealmetric.test",
            level=logging.ERROR,
            fn=__file__,
            lno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))
    assert payload["message"] == "failed"
    assert payload["exc_type"] == "RuntimeError"
    assert "RuntimeError: boom" in payload["traceback"]


def test_app_logs_unhandled_request_exceptions(capsys) -> None:  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    app = create_app()

    @app.get("/boom")
    def _boom() -> dict[str, str]:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    captured = capsys.readouterr()
    assert response.status_code == 500
    assert '"message": "unhandled request exception"' in captured.out
    assert '"exc_type": "RuntimeError"' in captured.out
    assert "RuntimeError: boom" in captured.out
