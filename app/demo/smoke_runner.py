"""Reusable smoke-test workflow for demoing the MVP through HTTP API."""

from dataclasses import dataclass, field
from typing import Any

from httpx import AsyncClient


@dataclass(slots=True)
class DemoStepResult:
    """One executed demo step."""

    name: str
    method: str
    path: str
    status_code: int
    ok: bool
    detail: str


@dataclass(slots=True)
class DemoSmokeReport:
    """Aggregated result of the demo smoke workflow."""

    base_url: str
    ok: bool
    steps: list[DemoStepResult] = field(default_factory=list)


async def run_demo_smoke(
    client: AsyncClient,
    api_key: str | None = None,
) -> DemoSmokeReport:
    """Runs a stable set of MVP demo checks against a live HTTP API."""

    headers = {"X-API-Key": api_key} if api_key else {}
    steps = [
        {
            "name": "health",
            "method": "GET",
            "path": "/api/health",
            "expected_status": 200,
            "validator": _validate_health,
        },
        {
            "name": "preflight",
            "method": "POST",
            "path": "/api/automation/preflight",
            "json": {"site": "msk-lab", "status": "reachable"},
            "headers": headers,
            "expected_status": 200,
            "validator": _validate_preflight,
        },
        {
            "name": "profile_preview",
            "method": "POST",
            "path": "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/preview",
            "json": {"hostname": "EDGE-R1", "banner_motd": "Managed by smoke runner"},
            "headers": headers,
            "expected_status": 200,
            "validator": _validate_profile_preview,
        },
        {
            "name": "selector_compliance",
            "method": "POST",
            "path": "/api/automation/selection/base-config/profiles/branch-edge/compliance",
            "json": {
                "selector": {"site": "msk-lab", "status": "reachable"},
                "overrides": {"hostname": "EDGE-R1"},
            },
            "headers": headers,
            "expected_status": 200,
            "validator": _validate_selector_compliance,
        },
        {
            "name": "dry_run_apply",
            "method": "POST",
            "path": "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/apply?dry_run=true",
            "json": {"hostname": "EDGE-R1"},
            "headers": headers,
            "expected_status": 200,
            "validator": _validate_dry_run_apply,
        },
        {
            "name": "history_summary",
            "method": "GET",
            "path": "/api/automation/operations/summary?device_name=lab-r1",
            "expected_status": 200,
            "validator": _validate_history_summary,
        },
    ]

    results: list[DemoStepResult] = []
    overall_ok = True
    for step in steps:
        response = await client.request(
            step["method"],
            step["path"],
            json=step.get("json"),
            headers=step.get("headers"),
        )
        ok, detail = step["validator"](response, step["expected_status"])
        overall_ok = overall_ok and ok
        results.append(
            DemoStepResult(
                name=step["name"],
                method=step["method"],
                path=step["path"],
                status_code=response.status_code,
                ok=ok,
                detail=detail,
            )
        )

    return DemoSmokeReport(base_url=str(client.base_url), ok=overall_ok, steps=results)


def _validate_health(response: Any, expected_status: int) -> tuple[bool, str]:
    if response.status_code != expected_status:
        return False, f"expected HTTP {expected_status}, got {response.status_code}"
    payload = response.json()
    if payload.get("status") != "ok":
        return False, "health payload did not contain status=ok"
    return True, "service health endpoint is reachable"


def _validate_preflight(response: Any, expected_status: int) -> tuple[bool, str]:
    if response.status_code != expected_status:
        return False, f"expected HTTP {expected_status}, got {response.status_code}"
    payload = response.json()
    if not payload.get("matched_devices"):
        return False, "preflight selector did not match any devices"
    if not payload.get("reachable_devices"):
        return False, "preflight did not resolve reachable devices"
    return True, "preflight matched reachable targets"


def _validate_profile_preview(response: Any, expected_status: int) -> tuple[bool, str]:
    if response.status_code != expected_status:
        return False, f"expected HTTP {expected_status}, got {response.status_code}"
    payload = response.json()
    commands = payload.get("commands", [])
    if not any(command == "hostname EDGE-R1" for command in commands):
        return False, "preview did not render the expected hostname command"
    return True, "profile-based preview generated CLI commands"


def _validate_selector_compliance(response: Any, expected_status: int) -> tuple[bool, str]:
    if response.status_code != expected_status:
        return False, f"expected HTTP {expected_status}, got {response.status_code}"
    payload = response.json()
    summary = payload.get("summary", {})
    if summary.get("total_items") != 2:
        return False, "selector compliance did not target the expected number of devices"
    if summary.get("successful_items") != 2:
        return False, "selector compliance did not complete successfully for both reachable lab devices"
    return True, "selector-based compliance returned an aggregate summary"


def _validate_dry_run_apply(response: Any, expected_status: int) -> tuple[bool, str]:
    if response.status_code != expected_status:
        return False, f"expected HTTP {expected_status}, got {response.status_code}"
    payload = response.json()
    if payload.get("dry_run") is not True:
        return False, "apply response did not stay in dry-run mode"
    if payload.get("device_name") != "lab-r1":
        return False, "dry-run apply targeted an unexpected device"
    return True, "dry-run apply completed without changing state"


def _validate_history_summary(response: Any, expected_status: int) -> tuple[bool, str]:
    if response.status_code != expected_status:
        return False, f"expected HTTP {expected_status}, got {response.status_code}"
    payload = response.json()
    if payload.get("total_operations", 0) < 1:
        return False, "operation summary did not record demo activity"
    return True, "operation history summary reflects executed demo steps"
