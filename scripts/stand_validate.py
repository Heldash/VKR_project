"""CLI runner for validating a live MVP stand before a demo or defense."""

import argparse
import asyncio
import json
from pathlib import Path

from httpx import AsyncClient

from app.automation.models import DeviceSelector
from app.demo.stand_validator import run_stand_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a live MVP stand through its HTTP API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of the running API")
    parser.add_argument("--api-key", default=None, help="Optional X-API-Key value")
    parser.add_argument("--site", default=None, help="Optional site filter for the validation target set")
    parser.add_argument("--role", default=None, help="Optional role filter for the validation target set")
    parser.add_argument("--status", default=None, help="Optional status filter for the validation target set")
    parser.add_argument("--vendor", default=None, help="Optional vendor filter for the validation target set")
    parser.add_argument("--output", default=None, help="Optional path to save the JSON validation report")
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    selector = DeviceSelector(
        site=args.site,
        role=args.role,
        status=args.status,
        vendor=args.vendor,
    )
    effective_selector = selector if any(selector.model_dump().values()) else None

    async with AsyncClient(base_url=args.base_url, timeout=20.0) as client:
        report = await run_stand_validation(
            client=client,
            api_key=args.api_key,
            selector=effective_selector,
        )

    print(f"Stand validation for {report.base_url}: {'OK' if report.overall_ok else 'FAILED'}")
    print(
        f"- preflight={report.preflight_ready} diagnostics={report.diagnostics_ok} smoke={report.smoke_ok}"
    )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding='utf-8')
        print(f"- report saved to {output_path}")
    return 0 if report.overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
