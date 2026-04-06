#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import upload_limits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render the canonical backend upload-limit contract.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Use json for machine-readable output.",
    )
    args = parser.parse_args()

    if args.format == "json":
        print(json.dumps(upload_limits.build_upload_limit_contract(), indent=2))
        return 0

    print(upload_limits.render_upload_limit_contract_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
