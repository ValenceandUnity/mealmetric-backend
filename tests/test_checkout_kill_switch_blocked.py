from fastapi.testclient import TestClient


def test_checkout_kill_switch_blocked(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(KILL_SWITCH_ENABLED="true")

    response = client.post(
        "/api/checkout/session", json={"price_id": "price_abc123", "quantity": 1}
    )

    assert response.status_code == 503
    assert response.status_code != 200
    assert response.status_code != 404


def test_checkout_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/checkout/session", json={"price_id": "price_abc123", "quantity": 1}
    )
    assert response.status_code == 401
