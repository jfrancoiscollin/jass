#!/usr/bin/env python3
"""Run the train-only contextual C3 baseline diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import types
from typing import Any

import yaml

PYTHON_ROOT = Path(__file__).resolve().parents[1] / "python"
PACKAGE_ROOT = PYTHON_ROOT / "mini_jass_lab"
if "mini_jass_lab" not in sys.modules:
    package = types.ModuleType("mini_jass_lab")
    package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["mini_jass_lab"] = package
sys.path.insert(0, str(PYTHON_ROOT))

from mini_jass_lab.context_c3 import run_c3_diagnostic  # noqa: E402
from mini_jass_lab.context_gate import digest  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402


EXPECTED_SEALED_RESULT_HASH = (
    "bcacf5dca4ea2509da91ab3c0aceaea5de057a3197b3b31599a2d36e91d3783c"
)
EXPECTED_FINAL_DECISION = "REJECTED_COMBINED_EFFECT_NONPOSITIVE"
EXPECTED_PROTOCOL_HASH = (
    "1ec2f8e510137714fc95635b11c7ae98400d1ba9ccf0efa2ac37bc0ae20769da"
)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _resolve(config_path: Path, sealed_result_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.contextual_outcome_supervision.v3":
        raise ValueError("C3 requires contextual supervision v3")
    if config.get("status") != "SEALED_TEST_DESCRIPTIVE_READ_COMPLETE":
        raise ValueError("C3 requires the completed single sealed read")
    c3 = config["c3_diagnostic_v1"]
    protocol = c3["protocol"]
    if c3.get("status") != "implementation_ready_for_verification":
        raise ValueError("C3 implementation is not at its verification boundary")
    if c3.get("protocol_hash") != EXPECTED_PROTOCOL_HASH or digest(protocol) != EXPECTED_PROTOCOL_HASH:
        raise ValueError("C3 protocol hash differs from the frozen pin")
    forbidden = protocol["forbidden"]
    if (
        protocol.get("cohort") != "train"
        or protocol.get("nonterminal_only") is not True
        or protocol.get("prerequisite_sealed_result_hash")
        != EXPECTED_SEALED_RESULT_HASH
        or protocol.get("prerequisite_final_decision") != EXPECTED_FINAL_DECISION
        or any(value is not True for value in forbidden.values())
    ):
        raise ValueError("C3 leakage or non-promotion contract changed")

    sealed_pin = config["sealed_test_read"]["frozen_report_v1"]
    sealed = _load_object(sealed_result_path)
    if (
        sealed_pin.get("result_hash") != EXPECTED_SEALED_RESULT_HASH
        or sealed_pin.get("sealed_test_read_count") != 1
        or sealed_pin.get("final_chained_decision_unchanged")
        != EXPECTED_FINAL_DECISION
        or sealed.get("schema") != "mini_jass.contextual_sealed_read.v1"
        or sealed.get("status") != "SEALED_TEST_DESCRIPTIVE_READ_COMPLETE"
        or sealed.get("result_hash") != EXPECTED_SEALED_RESULT_HASH
        or sealed.get("sealed_test_read_count") != 1
        or sealed.get("final_chained_decision_unchanged")
        != EXPECTED_FINAL_DECISION
        or sealed.get("descriptive_only") is not True
        or sealed.get("promotable") is not False
    ):
        raise ValueError("C3 sealed-result prerequisite differs from its pin")
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--sealed-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--execution-host", required=True)
    args = parser.parse_args()

    if len(args.implementation_sha) != 40 or any(
        character not in "0123456789abcdef" for character in args.implementation_sha
    ):
        raise ValueError("implementation SHA must be a lowercase full Git SHA")
    config = _resolve(args.config, args.sealed_result)
    oracle = load_oracle(args.oracle)
    split = build_split(oracle, seed=int(config["data_contract"]["split_seed"]))
    if split.manifest.get("manifest_hash") != config["data_contract"]["split_manifest_hash"]:
        raise ValueError("C3 split manifest differs from the frozen pin")

    report = run_c3_diagnostic(oracle, split, config)
    report["protocol"] = config["c3_diagnostic_v1"]["protocol"]
    report["protocol_hash"] = config["c3_diagnostic_v1"]["protocol_hash"]
    report["split_manifest_hash"] = split.manifest["manifest_hash"]
    report["sealed_prerequisite"] = {
        "result_hash": EXPECTED_SEALED_RESULT_HASH,
        "sealed_test_read_count": 1,
        "final_chained_decision": EXPECTED_FINAL_DECISION,
    }
    report["implementation_sha"] = args.implementation_sha
    report["execution_host"] = args.execution_host
    report["result_hash"] = digest(report)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    if json.loads(args.output.read_text(encoding="utf-8")) != report:
        raise RuntimeError("C3 report write/read smoke failed")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
