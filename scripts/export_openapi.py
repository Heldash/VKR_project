"""Export the current FastAPI OpenAPI schema to a JSON file."""

import argparse
import json
from pathlib import Path

from app.main import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema")
    parser.add_argument(
        "--output",
        default="tmp/openapi.json",
        help="Path to the output JSON file",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = create_app()
    schema = app.openapi()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"OpenAPI schema exported to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
