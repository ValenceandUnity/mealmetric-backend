from fastapi.testclient import TestClient


def test_kill_switch_allows_db_health(configured_client, bff_headers: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(KILL_SWITCH_ENABLED="true", DATABASE_URL="")

    db_health = client.get(
        "/db/health",
        headers={"Authorization": "Bearer placeholder", **bff_headers},
    )
    ping = client.get("/api/ping")

    assert db_health.status_code == 503
    assert db_health.json() == {"detail": "db_unavailable"}
    assert ping.status_code == 503
