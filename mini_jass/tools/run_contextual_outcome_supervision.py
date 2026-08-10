#!/usr/bin/env python3
"""Run only the frozen contextual C0 validity gate and write its report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import types

import yaml

PYTHON_ROOT = Path(__file__).resolve().parents[1] / "python"
PACKAGE_ROOT = PYTHON_ROOT / "mini_jass_lab"
if "mini_jass_lab" not in sys.modules:
    package = types.ModuleType("mini_jass_lab")
    package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["mini_jass_lab"] = package
sys.path.insert(0, str(PYTHON_ROOT))

from mini_jass_lab.context_gate import (  # noqa: E402
    attach_export_proof,
    digest,
    evaluate_c0,
)
from mini_jass_lab.context_scaffold import (  # noqa: E402
    ContextualPatternScaffold,
    prove_scalar_export,
)
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.patterns import PatternSet  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--execution-host", required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    frozen = config["power_sizing_v1"]["frozen_report_v1"]
    if frozen.get("c0_or_training_authorized") is not False:
        raise ValueError("C0 must start from a non-authorizing upstream freeze")
    if config.get("status") != "C0_implementation_ready_for_verification":
        raise ValueError("C0 config is not at the frozen verification boundary")

    oracle = load_oracle(args.oracle)
    split = build_split(oracle, seed=int(config["data_contract"]["split_seed"]))
    report = evaluate_c0(oracle, split, config)
    scaffold_config = config["training_scaffold_v1"]
    initialization = scaffold_config["initialization"]
    scaffold = ContextualPatternScaffold(
        PatternSet.from_window(int(scaffold_config["pattern_window"])),
        seed=int(config["c1_decision"]["paired_seeds"][0]),
        rank=int(scaffold_config["shared_rank"]),
        include_reversible_plies=bool(scaffold_config["include_reversible_plies"]),
        bucket_standard_deviation=float(
            initialization["bucket_embedding_standard_deviation"]
        ),
        reversible_standard_deviation=float(
            initialization["reversible_embedding_standard_deviation"]
        ),
        auxiliary_standard_deviation=float(
            initialization["auxiliary_head_standard_deviation"]
        ),
    )
    proof = prove_scalar_export(scaffold, oracle)
    report = attach_export_proof(report, proof, config)
    if len(args.implementation_sha) != 40 or any(
        character not in "0123456789abcdef" for character in args.implementation_sha
    ):
        raise ValueError("implementation SHA must be a lowercase full Git SHA")
    report.pop("report_hash", None)
    report["implementation_sha"] = args.implementation_sha
    report["execution_host"] = args.execution_host
    report["report_hash"] = digest(report)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    if json.loads(args.output.read_text(encoding="utf-8")) != report:
        raise RuntimeError("C0 report write/read smoke failed")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
