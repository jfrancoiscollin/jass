#!/usr/bin/env python3
"""Fail closed if SB1 implementation changes anything outside its registered Boundary-A surface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

ALLOWED_PATHS = {
    "jobs/tools/sb1_weight_audit.py",
    "jobs/tools/sb1_fit_contract.py",
    "jobs/tools/sb1_subset.py",
    "jobs/tools/sb1_scope_guard.py",
    "jobs/tools/sb1_postfit_readout.py",
    "jobs/templates/l3-sb1-scan-basin-boundary-a-v1.sh",
    "jobs/templates/l3-sb1-scan-basin-fit-v1.sh",
    "jobs/tests/test_l3_scan_weight_basin_prior.py",
}
FORBIDDEN_ENGINE_FRAGMENTS = (
    "search", "qsearch", "movegen", "transposition", "tt", "egdb", "cmakelists",
)


def validate_changed_paths(paths: list[str]) -> dict:
    normalized = [str(Path(path).as_posix()) for path in paths if path]
    unexpected = sorted(set(normalized) - ALLOWED_PATHS)
    engine_like = sorted(
        path for path in normalized
        if any(fragment in path.lower() for fragment in FORBIDDEN_ENGINE_FRAGMENTS)
        and path not in ALLOWED_PATHS
    )
    if unexpected:
        raise ValueError(f"SB1 scope violation: unexpected changed paths: {unexpected}")
    return {
        "schema": "jass.sb1.scope_guard.v1",
        "changed_paths": sorted(set(normalized)),
        "allowed_paths": sorted(ALLOWED_PATHS),
        "unexpected_paths": [],
        "engine_semantics_mutated": False,
        "forbidden_engine_paths": engine_like,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{args.base}...{args.head}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    paths = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    report = validate_changed_paths(paths)
    report["base"] = args.base
    report["head"] = args.head
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SB1_SCOPE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
