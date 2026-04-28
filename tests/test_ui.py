import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_root_redirects_to_ui():
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as ac:
        response = await ac.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


@pytest.mark.asyncio
async def test_ui_dashboard_page_is_served():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ui")

    assert response.status_code == 200
    assert "NetAuto" in response.text
    assert "Swagger UI" in response.text
    assert "add-interface" in response.text


@pytest.mark.asyncio
async def test_ui_static_assets_are_served():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ui/static/app.js")

    assert response.status_code == 200
    assert "refreshDashboard" in response.text
