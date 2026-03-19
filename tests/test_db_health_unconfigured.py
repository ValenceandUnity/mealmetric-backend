from fastapi.testclient import TestClient


def test_db_health_unconfigured_returns_503(configured_client, bff_headers: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(DATABASE_URL="")

    response = client.get(
        "/db/health",
        headers={"Authorization": "Bearer placeholder", **bff_headers},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "db_unavailable"}


def test_db_health_missing_bff_header_returns_401(
    client: TestClient, admin_auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/db/health",
        headers={"Authorization": str(admin_auth_headers["Authorization"])},
    )
    assert response.status_code == 401


def test_db_health_missing_jwt_with_valid_bff_returns_401(
    client: TestClient, bff_headers: dict[str, str]
) -> None:
    response = client.get("/db/health", headers=bff_headers)
    assert response.status_code == 401
