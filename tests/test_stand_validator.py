import pytest
from httpx import ASGITransport, AsyncClient

from app.automation.models import DeviceSelector
from app.core.config import settings
from app.demo.stand_validator import run_stand_validation
from app.main import create_app


@pytest.mark.asyncio
async def test_stand_validation_reports_success_for_mock_api():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report = await run_stand_validation(
            client=client,
            selector=DeviceSelector(site="msk-lab", status="reachable"),
        )

    assert report.overall_ok is True
    assert report.preflight_ready is True
    assert report.diagnostics_ok is True
    assert report.smoke_ok is True
    assert report.selector == {"site": "msk-lab", "status": "reachable"}
    assert report.preflight["payload"]["matched_devices"] == 2
    assert report.diagnostics["payload"]["matched_devices"] == 2


@pytest.mark.asyncio
async def test_stand_validation_uses_api_key_when_enabled():
    original_api_key = settings.api_key
    settings.api_key = "demo-secret"
    app = create_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            report = await run_stand_validation(
                client=client,
                api_key="demo-secret",
            )
    finally:
        settings.api_key = original_api_key

    assert report.overall_ok is True
    assert report.preflight["status_code"] == 200
    assert report.diagnostics["status_code"] == 200
    assert report.smoke_ok is True
