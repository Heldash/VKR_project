"""CLI runner for the stable MVP demo smoke workflow."""

import argparse
import asyncio

from httpx import AsyncClient

from app.demo.smoke_runner import run_demo_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MVP demo smoke checks against a live API")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running API",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional X-API-Key value for protected automation endpoints",
    )
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    async with AsyncClient(base_url=args.base_url, timeout=15.0) as client:
        report = await run_demo_smoke(client=client, api_key=args.api_key)

    print(f"Demo smoke for {report.base_url}: {'OK' if report.ok else 'FAILED'}")
    for step in report.steps:
        status = "OK" if step.ok else "FAILED"
        print(f"- [{status}] {step.name}: {step.method} {step.path} -> {step.status_code} ({step.detail})")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
