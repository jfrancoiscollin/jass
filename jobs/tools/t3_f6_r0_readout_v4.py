#!/usr/bin/env python3
"""Fail-closed R0-v4 zero-wrapper production leaf contract readout."""
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
ZERO_SHA = "160489327d419e3d7bbbbda900d6e0ec7bc960111149fc0a45cc27aaa55bf6aa"
PREREG_MERGE_SHA = "e857a5a951afa3c78957c7ad92afb67e4b0dae3b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path | None) -> dict:
    return {} if path is None else json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def terminal(payload: dict, out: Path, verdict: str, failed: dict) -> int:
    payload.update({
        "passed": False,
        "verdict": verdict,
        "terminal_r0_v4": True,
        "pool1_authorized": False,
        "automatic_next_job": None,
        "failed_report": failed,
    })
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--wrapper", type=Path)
    parser.add_argument("--relative", type=Path)
    parser.add_argument("--parity", type=Path)
    parser.add_argument("--runtime-profile", type=Path)
    parser.add_argument("--search-profile", type=Path)
    parser.add_argument("--loader-auth", type=Path)
    parser.add_argument("--runtime-contract", type=Path)
    parser.add_argument("--zero-manifest", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--zero", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--probe-executable", type=Path)
    parser.add_argument("--reference-rffd", type=Path)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    require(re.fullmatch(r"[0-9a-f]{40}", args.code_sha) is not None, "code SHA drift")
    require(sha(args.model) == MODEL_SHA, "frozen T3-A bytes drift")
    require(sha(args.curriculum) == CURRICULUM_SHA, "CURRICULUM bytes drift")
    require(sha(args.zero) == ZERO_SHA, "ZERO bytes drift")
    selection = load(args.selection)
    require(selection.get("schema") == "jass.t3_f6_r0_target_blind_selection.v4",
            "R0-v4 selection schema drift")
    payload = {
        "schema": "jass.t3_f6_r0_production_leaf_contract.v4",
        "code_sha": args.code_sha,
        "prereg_merge_sha": PREREG_MERGE_SHA,
        "artifact_sha256": MODEL_SHA,
        "zero_probe_sha256": ZERO_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "rf1_sha256": RF1_SHA,
        "feature_order_sha256": FEATURE_ORDER_SHA,
        "selection": selection,
        "immutable_upstream": {
            "v1": "R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED",
            "v2": "R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED",
            "negamax_autopsy": "QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH",
            "v3": "R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE",
            "v3_job": "cpx62-1652-l3-t3-f6-runtime-r0-v3",
            "v3_attempt": "20260829T152726Z-880fccbe",
        },
        "strength_games_played": 0,
        "q00_games_played": 0,
        "post_freeze_fits": 0,
        "retunes": 0,
        "calibrations": 0,
        "promotion_authorized": False,
        "bake": False,
    }
    if selection.get("passed") is not True:
        return terminal(payload, args.out,
                        selection.get("verdict", "R0_V4_RUNTIME_SUPPORT_INCONCLUSIVE"),
                        selection)
    require(selection.get("candidate_records") == 40000
            and selection.get("selected") == 4096
            and selection.get("search_subset") == 512,
            "R0-v4 corpus cardinality drift")
    require(selection.get("selected_by_phase") == {p: 1024 for p in ("P0", "P1", "P2", "P3")}
            and selection.get("search_subset_by_phase") == {p: 128 for p in ("P0", "P1", "P2", "P3")},
            "R0-v4 phase quotas drift")
    require(tuple(selection.get(k) for k in (
                "selection_seed", "permutation_seed", "search_seed", "benchmark_seed"))
            == (2026092502, 2026092503, 2026092504, 2026092505),
            "R0-v4 seed drift")
    require(selection.get("forbidden_overlap") == 0
            and all(selection.get(k) == 0 for k in (
                "score_reads", "wdl_reads", "deep_label_reads", "runtime_metric_reads")),
            "R0-v4 target-blind contract failed")
    sources = selection.get("excluded_sources", {})
    require(any("v3" in key or "mechanics" in key for key in sources)
            and any("scan" in key or "siblings" in key for key in sources),
            "R0-v4 V3/Scan exclusion receipts missing")

    reports = {
        "wrapper": load(args.wrapper), "relative": load(args.relative),
        "parity": load(args.parity), "runtime": load(args.runtime_profile),
        "search": load(args.search_profile), "loader": load(args.loader_auth),
        "contract": load(args.runtime_contract), "zero_manifest": load(args.zero_manifest),
    }
    failure_defaults = {
        "wrapper": "R0_V4_ZERO_WRAPPER_SEARCH_EQUIVALENCE_FAILED",
        "relative": "R0_V4_RELATIVE_DRIFT_FAILED",
        "parity": "R0_V4_PYTHON_NATIVE_PARITY_FAILED",
        "search": "R0_V4_RUNTIME_TECHNICAL_FAILED",
        "loader": "R0_V4_DORMANT_CONTRACT_FAILED",
        "contract": "R0_V4_DORMANT_CONTRACT_FAILED",
        "zero_manifest": "R0_V4_DORMANT_CONTRACT_FAILED",
    }
    for key, fallback in failure_defaults.items():
        if reports[key].get("passed") is not True:
            return terminal(payload, args.out,
                            reports[key].get("verdict", fallback), reports[key])

    wrapper, relative, parity = reports["wrapper"], reports["relative"], reports["parity"]
    require(wrapper.get("schema") == "jass.t3_f6_runtime_wrapper_contract.v4"
            and wrapper.get("code_sha") == args.code_sha
            and wrapper.get("zero_sha256") == ZERO_SHA
            and wrapper.get("t3_sha256") == MODEL_SHA
            and wrapper.get("curriculum_sha256") == CURRICULUM_SHA,
            "R0-v4 wrapper identity drift")
    require(all(wrapper.get(k) is True for k in (
                "gate1_leaf_api_exactness", "gate3_zero_full_search_equivalence",
                "gate4_synthetic_negamax", "gate5_real_search_semantics",
                "gate9_terminal_tablebase", "gate10_dormant_contract"))
            and wrapper.get("zero_leaf_mismatch_count") == 0
            and wrapper.get("zero_search_mismatch_count") == 0
            and wrapper.get("trace_neutral_mismatch_count") == 0
            and wrapper.get("t3_trace_formula_mismatch_count") == 0
            and wrapper.get("production_env_accepts_zero") is False,
            "R0-v4 ZERO/search wrapper gate failed")
    require(relative.get("schema") == "jass.t3_f6_relative_contract.v4"
            and relative.get("passed") is True and relative.get("positions") == 4096
            and relative.get("permutation_seed") == 2026092503
            and relative.get("gate1_position_transposition") is True
            and relative.get("gate2_f6_residual_invariance") is True
            and relative.get("gate3_relative_drift") is True
            and relative.get("position_replay_mismatches") == 0
            and relative.get("q_wdl_container_mismatches") == 0
            and relative.get("tt_search_state_mismatches") == 0
            and relative.get("explicit_distinct_parent_transposition") is True
            and relative.get("f6_colour_mismatch_rows") == 0
            and relative.get("residual_colour_mismatch_rows") == 0
            and relative.get("engine_extra_drift_mismatch_count") == 0
            and relative.get("max_abs_extra_drift_engine_cp") == 0
            and relative.get("max_abs_extra_drift_float_cp", 1.0) <= 1e-10
            and relative.get("saturations") == 0,
            "R0-v4 position/invariance/relative drift failed")
    require(parity.get("schema") == "jass.t3_f6_runtime_parity.v4"
            and parity.get("passed") is True and parity.get("rows") == 4096
            and parity.get("feature_bitwise_mismatches") == 0
            and parity.get("normalized_bitwise_mismatches") == 0
            and parity.get("integer_score_mismatches") == 0
            and parity.get("zero_residual_bitwise_positive_zero") is True
            and parity.get("zero_engine_mismatches") == 0
            and parity.get("saturations") == 0,
            "R0-v4 Python/native parity failed")
    runtime, search, loader = reports["runtime"], reports["search"], reports["loader"]
    require(runtime.get("positions") == 4096 and runtime.get("order_seed") == 2026092505
            and runtime.get("measured_passes") == 32 and runtime.get("saturations") == 0
            and set(runtime.get("family_us_per_eval", {})) == {"F1", "F2", "F3", "F4", "F5"}
            and runtime.get("movegen_calls", 0) > 0
            and runtime.get("response_enumerations_f2", 0) > 0,
            "R0-v4 runtime profile incomplete")
    require(search.get("passed") is True
            and search.get("off_regression", {}).get("static_mismatches") == 0
            and search.get("off_regression", {}).get("q00_move_score_depth_nodes_mismatches") == 0
            and search.get("order_seed") == 2026092505,
            "R0-v4 OFF regression/search profile failed")
    require(loader.get("off_absent_exact") is True and loader.get("on_exact_load") is True
            and loader.get("empty_env_rejected") is True
            and loader.get("wrong_artifact_rejected") is True
            and loader.get("zero_artifact_rejected_by_production") is True,
            "R0-v4 loader fail-closed failed")
    require(args.executable and args.probe_executable and args.reference_rffd,
            "R0-v4 full readout inputs missing")
    contract = reports["contract"]
    require(contract.get("schema") == "jass.t3_f6_runtime_contract.v4"
            and contract.get("same_executable_force_arms") is True
            and contract.get("leaf_only") is True
            and contract.get("executable_sha256") == sha(args.executable)
            and contract.get("probe_executable_sha256") == sha(args.probe_executable)
            and contract.get("threads") == 1 and contract.get("tt_mb") == 16
            and contract.get("egdb") == "ON" and contract.get("book") == "OFF"
            and contract.get("maxplies") == 160,
            "R0-v4 runtime semantics receipt failed")
    manifest = reports["zero_manifest"]
    require(manifest.get("schema") == "jass.t3_f6_zero_probe_manifest.v4"
            and manifest.get("artifact_sha256") == ZERO_SHA
            and manifest.get("data_inputs") == 0 and manifest.get("fits") == 0,
            "R0-v4 ZERO manifest failed")

    payload.update({
        "passed": True,
        "verdict": "R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
        "terminal_r0_v4": False,
        "pool1_authorized": True,
        "automatic_next_job": "POOL1_ONLY",
        "executable_sha256": sha(args.executable),
        "probe_executable_sha256": sha(args.probe_executable),
        "wrapper_contract": wrapper,
        "relative_contract": relative,
        "python_native_parity": parity,
        "runtime_cost_profile": runtime,
        "search_cost_and_off_regression": search,
        "loader_authentication": loader,
        "runtime_contract": contract,
        "zero_manifest": manifest,
        "components": {key: sha(path) for key, path in {
            "selection": args.selection, "wrapper": args.wrapper,
            "relative": args.relative, "parity": args.parity,
            "runtime_profile": args.runtime_profile, "search_profile": args.search_profile,
            "loader": args.loader_auth, "runtime_contract": args.runtime_contract,
            "zero_manifest": args.zero_manifest, "reference_rffd": args.reference_rffd,
        }.items()},
    })
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
