"""CLI runner for building a demo/defense artifact bundle."""

import argparse
import asyncio
from pathlib import Path

from httpx import AsyncClient

from app.automation.models import DeviceSelector
from app.demo.bundle_builder import build_demo_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a demo bundle from the running MVP API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of the running API")
    parser.add_argument("--api-key", default=None, help="Optional X-API-Key value")
    parser.add_argument("--site", default=None, help="Optional site filter")
    parser.add_argument("--role", default=None, help="Optional role filter")
    parser.add_argument("--status", default=None, help="Optional status filter")
    parser.add_argument("--vendor", default=None, help="Optional vendor filter")
    parser.add_argument("--output-dir", default="tmp/demo-bundle", help="Directory for generated artifacts")
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
        artifacts = await build_demo_bundle(
            client=client,
            output_dir=Path(args.output_dir),
            api_key=args.api_key,
            selector=effective_selector,
        )

    print("Demo bundle created:")
    print(f"- directory: {artifacts['directory']}")
    print(f"- validation: {artifacts['validation']}")
    print(f"- openapi: {artifacts['openapi']}")
    print(f"- summary: {artifacts['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
