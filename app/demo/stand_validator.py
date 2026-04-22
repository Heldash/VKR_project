"""Combined stand validation workflow for the live MVP environment."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from httpx import AsyncClient

from app.automation.models import DeviceSelector
from app.demo.smoke_runner import DemoSmokeReport, run_demo_smoke


@dataclass(slots=True)
class StandValidationReport:
    """Aggregated validation result for a live demo stand."""

    base_url: str
    generated_at: str
    selector: dict[str, str] | None
    preflight_ready: bool
    diagnostics_ok: bool
    smoke_ok: bool
    overall_ok: bool
    preflight: dict
    diagnostics: dict
    smoke: dict

    def to_dict(self) -> dict:
        return asdict(self)


async def run_stand_validation(
    client: AsyncClient,
    api_key: str | None = None,
    selector: DeviceSelector | None = None,
) -> StandValidationReport:
    """Runs all major stand checks against a live HTTP API."""

    headers = {"X-API-Key": api_key} if api_key else {}
    payload = _selector_payload(selector)

    preflight_response = await client.post(
        "/api/automation/preflight",
        json=payload,
        headers=headers,
    )
    preflight = preflight_response.json()

    diagnostics_response = await client.post(
        "/api/automation/diagnostics",
        json=payload,
        headers=headers,
    )
    diagnostics = diagnostics_response.json()

    smoke = await run_demo_smoke(client=client, api_key=api_key)
    overall_ok = (
        preflight_response.status_code == 200
        and diagnostics_response.status_code == 200
        and bool(preflight.get("ready"))
        and bool(diagnostics.get("ok"))
        and smoke.ok
    )

    return StandValidationReport(
        base_url=str(client.base_url),
        generated_at=datetime.now(UTC).isoformat(),
        selector=payload,
        preflight_ready=bool(preflight.get("ready")),
        diagnostics_ok=bool(diagnostics.get("ok")),
        smoke_ok=smoke.ok,
        overall_ok=overall_ok,
        preflight={
            "status_code": preflight_response.status_code,
            "payload": preflight,
        },
        diagnostics={
            "status_code": diagnostics_response.status_code,
            "payload": diagnostics,
        },
        smoke=_smoke_to_dict(smoke),
    )


def _selector_payload(selector: DeviceSelector | None) -> dict[str, str] | None:
    if selector is None:
        return None
    payload = {
        key: value
        for key, value in selector.model_dump().items()
        if value is not None
    }
    return payload or None


def _smoke_to_dict(report: DemoSmokeReport) -> dict:
    return {
        "base_url": report.base_url,
        "ok": report.ok,
        "steps": [
            {
                "name": step.name,
                "method": step.method,
                "path": step.path,
                "status_code": step.status_code,
                "ok": step.ok,
                "detail": step.detail,
            }
            for step in report.steps
        ],
    }
