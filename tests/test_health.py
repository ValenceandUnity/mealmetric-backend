from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_livez(client: TestClient) -> None:
    response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_readyz_without_db_returns_503(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(DATABASE_URL="")

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "detail": "db_unavailable"}
