import logging

from fastapi.testclient import TestClient


def test_request_id_header_and_log_enrichment(client: TestClient, caplog) -> None:  # type: ignore[no-untyped-def]
    logger = logging.getLogger("mealmetric.http")

    with caplog.at_level(logging.INFO, logger=logger.name):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    assert any(getattr(record, "request_id", "-") != "-" for record in caplog.records)
