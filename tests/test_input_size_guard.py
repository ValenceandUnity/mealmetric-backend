from fastapi.testclient import TestClient


def test_input_size_guard_rejects_large_content_length(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(MAX_REQUEST_BYTES="5")

    response = client.get("/api/ping", headers={"Content-Length": "6"})

    assert response.status_code == 413


def test_input_size_guard_rejects_invalid_content_length(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(MAX_REQUEST_BYTES="5")

    response = client.get("/api/ping", headers={"Content-Length": "abc"})

    assert response.status_code == 400
