import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.demo.smoke_runner import run_demo_smoke
from app.main import create_app


@pytest.mark.asyncio
async def test_demo_smoke_runner_reports_success_for_mock_api():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report = await run_demo_smoke(client, api_key=None)

    assert report.ok is True
    assert len(report.steps) == 6
    assert all(step.ok for step in report.steps)
    assert report.steps[1].name == "preflight"
    assert report.steps[3].name == "selector_compliance"


@pytest.mark.asyncio
async def test_demo_smoke_runner_reports_auth_failures_when_api_key_is_missing():
    original_api_key = settings.api_key
    settings.api_key = "demo-secret"
    app = create_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            report = await run_demo_smoke(client, api_key=None)
    finally:
        settings.api_key = original_api_key

    assert report.ok is False
    failed_steps = [step for step in report.steps if not step.ok]
    assert failed_steps
    assert any(step.name == "preflight" and step.status_code == 401 for step in failed_steps)
