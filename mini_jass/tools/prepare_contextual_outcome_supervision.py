#!/usr/bin/env python3
"""Validate M21-P and write the fail-closed contextual freeze report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import yaml  # noqa: E402

from mini_jass_lab.context_power import build_power_freeze_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--m21-result", type=Path, required=True)
    parser.add_argument("--m21-status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    result = json.loads(args.m21_result.read_text(encoding="utf-8"))
    status = json.loads(args.m21_status.read_text(encoding="utf-8"))
    report = build_power_freeze_report(config, result, status)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    if json.loads(args.output.read_text(encoding="utf-8")) != report:
        raise RuntimeError("contextual freeze report write/read smoke failed")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
