import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_health():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_list_devices():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/devices")
    assert response.status_code == 200
    assert len(response.json()) == 3
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_list_devices_supports_inventory_filters():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/devices",
            params={"site": "msk-lab", "status": "reachable"},
        )
    assert response.status_code == 200
    assert [device["name"] for device in response.json()] == ["lab-r1", "lab-r2"]


@pytest.mark.asyncio
async def test_get_single_device():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/devices/lab-r2")
    assert response.status_code == 200
    assert response.json()["management_ip"] == "192.0.2.12"
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_database_status():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/system/database")
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == "sqlite"
    assert body["initialized"] is True
    assert body["roles_count"] == 3
    assert body["users_count"] == 3
    assert body["path"].endswith("netauto.db")
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_request_id_header_is_echoed_when_provided():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/health",
            headers={"X-Request-ID": "demo-request-id"},
        )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "demo-request-id"
