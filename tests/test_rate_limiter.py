from fastapi.testclient import TestClient


def test_rate_limiter_returns_429_when_exceeded(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(RATE_LIMIT_RPS="1")

    first = client.get("/api/ping")
    second = client.get("/api/ping")

    assert first.status_code == 200
    assert second.status_code == 429
