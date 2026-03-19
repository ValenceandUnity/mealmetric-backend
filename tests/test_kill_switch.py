from fastapi.testclient import TestClient


def test_kill_switch_blocks_non_whitelisted_routes(configured_client) -> None:  # type: ignore[no-untyped-def]
    client: TestClient = configured_client(KILL_SWITCH_ENABLED="true", DATABASE_URL="")

    health = client.get("/health")
    livez = client.get("/livez")
    readyz = client.get("/readyz")
    blocked = client.get("/api/ping")

    assert health.status_code == 200
    assert livez.status_code == 200
    assert readyz.status_code == 503
    assert blocked.status_code == 503
