import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.automation.models import DeviceSelector
from app.demo.bundle_builder import build_demo_bundle
from app.main import create_app


@pytest.mark.asyncio
async def test_build_demo_bundle_creates_expected_artifacts():
    runtime_dir = Path("tests_runtime") / str(uuid4()) / "demo-bundle"
    app = create_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            artifacts = await build_demo_bundle(
                client=client,
                output_dir=runtime_dir,
                selector=DeviceSelector(site="msk-lab", status="reachable"),
            )

        validation_path = Path(artifacts["validation"])
        openapi_path = Path(artifacts["openapi"])
        summary_path = Path(artifacts["summary"])

        assert validation_path.exists()
        assert openapi_path.exists()
        assert summary_path.exists()

        validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))
        openapi_payload = json.loads(openapi_path.read_text(encoding="utf-8"))
        summary_text = summary_path.read_text(encoding="utf-8")

        assert validation_payload["overall_ok"] is True
        assert validation_payload["selector"] == {"site": "msk-lab", "status": "reachable"}
        assert openapi_payload["info"]["title"] == "NetAuto MVP"
        assert "Overall status: `OK`" in summary_text
    finally:
        shutil.rmtree(runtime_dir.parent, ignore_errors=True)


@pytest.mark.asyncio
async def test_build_demo_bundle_includes_expected_mvp_artifacts():
    runtime_dir = Path("tests_runtime") / str(uuid4()) / "demo-bundle"
    app = create_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            artifacts = await build_demo_bundle(
                client=client,
                output_dir=runtime_dir,
            )

        summary_text = Path(artifacts["summary"]).read_text(encoding="utf-8")

        assert "stand-validation.json" in summary_text
        assert "openapi.json" in summary_text
        assert "summary.md" in summary_text
    finally:
        shutil.rmtree(runtime_dir.parent, ignore_errors=True)
