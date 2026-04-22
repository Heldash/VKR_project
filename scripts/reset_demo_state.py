"""Reset the mock demo state and operation history through the HTTP API."""

import argparse
import asyncio

from httpx import AsyncClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reset mock demo state through the running API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of the running API")
    parser.add_argument("--api-key", default=None, help="Optional X-API-Key value")
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    headers = {"X-API-Key": args.api_key} if args.api_key else {}

    async with AsyncClient(base_url=args.base_url, timeout=15.0) as client:
        response = await client.post("/api/automation/demo/reset", headers=headers)
    response.raise_for_status()
    payload = response.json()

    print("Demo state reset completed:")
    print(f"- execution_backend: {payload['execution_backend']}")
    print(f"- inventory_backend: {payload['inventory_backend']}")
    print(f"- devices_reset: {payload['devices_reset']}")
    print(f"- snapshots_cleared: {payload['snapshots_cleared']}")
    print(f"- operations_cleared: {payload['operations_cleared']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
