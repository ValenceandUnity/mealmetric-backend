from fastapi.testclient import TestClient


def test_metrics_missing_bff_header_returns_401(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/metrics",
        headers={"Authorization": str(admin_auth_headers["Authorization"])},
    )

    assert response.status_code == 401


def test_metrics_missing_jwt_with_valid_bff_returns_401(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    response = client.get("/metrics", headers=bff_headers)

    assert response.status_code == 401


def test_metrics_non_admin_forbidden(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/metrics", headers=auth_headers)

    assert response.status_code == 403


def test_metrics_admin_allowed(client: TestClient, admin_auth_headers: dict[str, str]) -> None:
    response = client.get("/metrics", headers=admin_auth_headers)

    assert response.status_code == 200
    assert "mealmetric_http_requests_total" in response.text
    assert "mealmetric_stripe_webhook_received_total" in response.text
    assert "mealmetric_stripe_webhook_processed_total" in response.text
    assert "mealmetric_stripe_webhook_processing_seconds" in response.text
    assert "mealmetric_payment_lifecycle_transitions_total" in response.text
