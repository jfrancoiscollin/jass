#!/usr/bin/env python3
"""Fail-closed R0 production-leaf contract readout for frozen T3-A/F6."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

MODEL_SHA = "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
RF1_SHA = "0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b"
FEATURE_ORDER_SHA = "cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e"
RF1_EXTRACTOR_CODE = "e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--invariance", type=Path, required=True)
    parser.add_argument("--parity", type=Path, required=True)
    parser.add_argument("--runtime-profile", type=Path, required=True)
    parser.add_argument("--search-profile", type=Path, required=True)
    parser.add_argument("--loader-auth", type=Path, required=True)
    parser.add_argument("--runtime-contract", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--reference-rffd", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    require(re.fullmatch(r"[0-9a-f]{40}", args.code_sha) is not None,
            "code SHA contract drift")
    require(sha(args.model) == MODEL_SHA, "frozen model bytes drift")
    require(sha(args.curriculum) == CURRICULUM_SHA, "CURRICULUM bytes drift")
    selection = load(args.selection)
    invariance = load(args.invariance)
    parity = load(args.parity)
    runtime = load(args.runtime_profile)
    search = load(args.search_profile)
    loader = load(args.loader_auth)
    contract = load(args.runtime_contract)

    require(selection.get("passed") is True and selection.get("selected") == 4096,
            "R0 corpus selection failed")
    require(selection.get("selection_seed") == 2026090902
            and selection.get("permutation_seed") == 2026090903
            and selection.get("benchmark_seed") == 2026090904,
            "R0 target-blind seed drift")
    require(selection.get("selected_by_phase") == {name: 1024 for name in ("P0", "P1", "P2", "P3")},
            "R0 phase balance drift")
    require(selection.get("forbidden_overlap") == 0
            and selection.get("score_reads") == 0
            and selection.get("wdl_reads") == 0
            and selection.get("deep_label_reads") == 0,
            "R0 target-blind/exclusion contract failed")
    require(invariance.get("passed") is True
            and invariance.get("verdict") == "T3_F6_TRANSPOSITION_SAFE"
            and invariance.get("position_only") is True
            and invariance.get("distinct_immediate_parents") is True
            and invariance.get("tt_cold_warm_independent") is True
            and invariance.get("q_wdl_bytes_independent") is True
            and invariance.get("colour_perspective_exact") is True
            and invariance.get("negamax_single_inversion") is True
            and invariance.get("permutation_seed") == 2026090903,
            "position/TT/negamax invariance failed")
    require(parity.get("passed") is True and parity.get("rows") == 4096
            and parity.get("feature_coordinates") == 4096 * 66
            and parity.get("feature_bitwise_mismatches") == 0
            and parity.get("integer_score_mismatches") == 0
            and parity.get("saturations") == 0
            and parity.get("scale_cp") == 1.0,
            "Python/native exactness failed")
    require(runtime.get("positions") == 4096
            and runtime.get("warmup_passes") == 2
            and runtime.get("measured_passes") == 32
            and runtime.get("order_seed") == 2026090904
            and runtime.get("instrumented_passes") == 1
            and runtime.get("saturations") == 0
            and set(runtime.get("family_us_per_eval", {})) == {"F1", "F2", "F3", "F4", "F5"}
            and runtime.get("movegen_calls", 0) > 0
            and runtime.get("response_enumerations_f2", 0) > 0,
            "runtime-cost profile incomplete")
    require(search.get("passed") is True
            and search.get("off_regression", {}).get("static_mismatches") == 0
            and search.get("off_regression", {}).get("q00_move_score_depth_nodes_mismatches") == 0
            and search.get("profile_roots") == 128
            and search.get("profile_roots_by_phase") == {name: 32 for name in ("P0", "P1", "P2", "P3")},
            "OFF regression/search profile failed")
    require(loader.get("passed") is True
            and loader.get("off_absent_exact") is True
            and loader.get("on_exact_load") is True
            and loader.get("empty_env_rejected") is True
            and loader.get("wrong_artifact_rejected") is True,
            "fail-closed loader authentication failed")
    require(contract.get("passed") is True
            and contract.get("same_executable_both_arms") is True
            and contract.get("leaf_only") is True
            and contract.get("book") == "OFF"
            and contract.get("threads") == 1
            and contract.get("tt_mb") == 16
            and contract.get("egdb") == "ON"
            and contract.get("maxplies") == 160,
            "runtime semantics contract failed")
    for report in (invariance, parity, runtime):
        require(report.get("model_sha256") == MODEL_SHA
                and report.get("curriculum_sha256") == CURRICULUM_SHA,
                "R0 report artifact identity drift")
    require(invariance.get("feature_order_sha256") == FEATURE_ORDER_SHA
            and runtime.get("feature_order_sha256") == FEATURE_ORDER_SHA,
            "F6 feature-order identity drift")

    components = {
        "selection": sha(args.selection),
        "invariance": sha(args.invariance),
        "parity": sha(args.parity),
        "runtime_profile": sha(args.runtime_profile),
        "search_profile": sha(args.search_profile),
        "loader_auth": sha(args.loader_auth),
        "runtime_contract": sha(args.runtime_contract),
        "reference_rffd": sha(args.reference_rffd),
    }
    payload = {
        "schema": "jass.t3_f6_r0_production_leaf_contract.v1",
        "passed": True,
        "verdict": "R0_PRODUCTION_LEAF_CONTRACT_PASS",
        "code_sha": args.code_sha,
        "artifact_sha256": MODEL_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "rf1_sha256": RF1_SHA,
        "rf1_extractor_code": RF1_EXTRACTOR_CODE,
        "feature_order_sha256": FEATURE_ORDER_SHA,
        "executable_sha256": sha(args.executable),
        "components": components,
        "selection": selection,
        "invariance": invariance,
        "python_native_parity": parity,
        "runtime_cost_profile": runtime,
        "search_cost_and_off_regression": search,
        "loader_authentication": loader,
        "runtime_contract": contract,
        "strength_games_played": 0,
        "pool1_authorized": True,
        "promotion_authorized": False,
        "automatic_next_job": "POOL1_ONLY",
        "bake": False,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
