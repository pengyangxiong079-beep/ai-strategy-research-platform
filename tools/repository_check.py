"""Deterministic public-repository hygiene check; no network or credentials required."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit_latest_run import scan_repository


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    result = scan_repository(Path(args.root).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" and not result["large_files"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
