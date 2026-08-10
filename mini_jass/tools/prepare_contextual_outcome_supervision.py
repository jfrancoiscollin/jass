#!/usr/bin/env python3
"""Validate M21-P and write the fail-closed contextual freeze report."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import yaml  # noqa: E402


CONTEXT_POWER_PATH = (
    Path(__file__).resolve().parents[1]
    / "python"
    / "mini_jass_lab"
    / "context_power.py"
)
SPEC = importlib.util.spec_from_file_location(
    "context_power_standalone", CONTEXT_POWER_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the standalone contextual power module")
CONTEXT_POWER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTEXT_POWER)
build_power_freeze_report = CONTEXT_POWER.build_power_freeze_report


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
