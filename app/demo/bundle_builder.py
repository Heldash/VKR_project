"""Builds a reproducible demo bundle for the MVP defense stand."""

import json
from pathlib import Path

from httpx import AsyncClient

from app.automation.models import DeviceSelector
from app.demo.stand_validator import run_stand_validation


async def build_demo_bundle(
    client: AsyncClient,
    output_dir: str | Path,
    api_key: str | None = None,
    selector: DeviceSelector | None = None,
) -> dict[str, str]:
    """Creates a defense/demo bundle with validation, OpenAPI, and summary artifacts."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    validation_report = await run_stand_validation(
        client=client,
        api_key=api_key,
        selector=selector,
    )
    openapi_response = await client.get("/openapi.json")
    openapi_response.raise_for_status()
    openapi_schema = openapi_response.json()

    validation_path = target_dir / "stand-validation.json"
    openapi_path = target_dir / "openapi.json"
    summary_path = target_dir / "summary.md"

    validation_path.write_text(
        json.dumps(validation_report.to_dict(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    openapi_path.write_text(
        json.dumps(openapi_schema, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    summary_path.write_text(
        _build_summary(validation_report),
        encoding="utf-8",
    )

    return {
        "directory": str(target_dir),
        "validation": str(validation_path),
        "openapi": str(openapi_path),
        "summary": str(summary_path),
    }


def _build_summary(report) -> str:
    lines = [
        "# NetAuto MVP Demo Bundle",
        "",
        f"- Base URL: `{report.base_url}`",
        f"- Generated at: `{report.generated_at}`",
        f"- Overall status: `{'OK' if report.overall_ok else 'FAILED'}`",
        f"- Preflight: `{report.preflight_ready}`",
        f"- Diagnostics: `{report.diagnostics_ok}`",
        f"- Smoke: `{report.smoke_ok}`",
    ]
    if report.selector:
        selector_text = ", ".join(f"{key}={value}" for key, value in report.selector.items())
        lines.append(f"- Selector: `{selector_text}`")
    lines.extend(
        [
            "",
            "## Artifacts",
            "- `stand-validation.json` - combined readiness/diagnostics/smoke report",
            "- `openapi.json` - exported API contract for the current MVP build",
            "- `summary.md` - this short operator-facing overview",
        ]
    )
    return "\n".join(lines) + "\n"
