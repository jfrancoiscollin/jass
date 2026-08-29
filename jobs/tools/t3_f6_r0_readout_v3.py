#!/usr/bin/env python3
"""Fail-closed R0-v3 production leaf/search contract readout."""
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
PREREG_MERGE_SHA = "b326bb6610a7eb9b9b997540c1dbb0508f433ca0"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path | None) -> dict:
    return {} if path is None else json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def terminal(payload: dict, out: Path, verdict: str, failed_report: dict) -> int:
    payload.update({
        "passed": False,
        "verdict": verdict,
        "terminal_r0_v3": True,
        "pool1_authorized": False,
        "automatic_next_job": None,
        "failed_report": failed_report,
    })
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--relative", type=Path)
    parser.add_argument("--leaf-contract", type=Path)
    parser.add_argument("--parity", type=Path)
    parser.add_argument("--runtime-profile", type=Path)
    parser.add_argument("--search-profile", type=Path)
    parser.add_argument("--loader-auth", type=Path)
    parser.add_argument("--runtime-contract", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--reference-rffd", type=Path)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    require(re.fullmatch(r"[0-9a-f]{40}", args.code_sha) is not None,
            "code SHA contract drift")
    require(sha(args.model) == MODEL_SHA, "frozen T3-A bytes drift")
    require(sha(args.curriculum) == CURRICULUM_SHA, "CURRICULUM bytes drift")
    selection = load(args.selection)
    require(selection.get("schema") == "jass.t3_f6_r0_target_blind_selection.v3",
            "R0-v3 selection schema drift")
    payload = {
        "schema": "jass.t3_f6_r0_production_leaf_contract.v3",
        "code_sha": args.code_sha,
        "prereg_merge_sha": PREREG_MERGE_SHA,
        "artifact_sha256": MODEL_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "rf1_sha256": RF1_SHA,
        "rf1_extractor_code": RF1_EXTRACTOR_CODE,
        "feature_order_sha256": FEATURE_ORDER_SHA,
        "selection": selection,
        "immutable_upstream": {
            "v1": "R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED",
            "v2": "R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED",
            "negamax_autopsy": "QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH",
            "autopsy_job": "cpx62-1650-l3-t3-f6-negamax-autopsy-v1",
            "autopsy_attempt": "20260829T141312Z-2a4d1519",
            "autopsy_readout_job": "cpx62-1651-l3-t3-f6-negamax-autopsy-readout-v1",
            "autopsy_readout_attempt": "20260829T142315Z-2a4d1519",
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
                        selection.get("verdict", "R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE"),
                        selection)

    require(selection.get("candidate_records") == 120000
            and selection.get("mechanical_rows") == 120000
            and selection.get("selected") == 4096,
            "R0-v3 corpus cardinality drift")
    require(selection.get("selected_by_phase") == {
                phase: 1024 for phase in ("P0", "P1", "P2", "P3")}
            and selection.get("isolated_roots") == 128
            and selection.get("isolated_by_phase") == {
                phase: 32 for phase in ("P0", "P1", "P2", "P3")}
            and selection.get("real_trace_roots") == 256
            and selection.get("real_trace_by_phase") == {
                phase: 64 for phase in ("P0", "P1", "P2", "P3")},
            "R0-v3 phase/witness quota drift")
    require(tuple(selection.get(key) for key in (
                "selection_seed", "permutation_seed", "benchmark_seed",
                "isolated_seed", "trace_seed"))
            == (2026092102, 2026092103, 2026092104, 2026092105, 2026092106),
            "R0-v3 target-blind seed drift")
    require(selection.get("forbidden_overlap") == 0
            and all(selection.get(key) == 0 for key in (
                "score_reads", "wdl_reads", "deep_label_reads",
                "runtime_metric_reads")),
            "R0-v3 target-blind/exclusion contract failed")
    sources = selection.get("excluded_sources", {})
    require(any("r0-v1" in key for key in sources)
            and any("r0-v2" in key for key in sources)
            and any("autopsy" in key for key in sources),
            "R0-v3 required exclusion receipt missing")

    relative = load(args.relative)
    if relative.get("passed") is not True:
        payload["relative_contract"] = relative
        return terminal(payload, args.out,
                        relative.get("verdict", "R0_V3_RELATIVE_DRIFT_FAILED"),
                        relative)
    require(relative.get("schema") == "jass.t3_f6_relative_contract.v3"
            and relative.get("positions") == 4096
            and relative.get("permutation_seed") == 2026092103
            and relative.get("model_sha256") == MODEL_SHA
            and relative.get("curriculum_sha256") == CURRICULUM_SHA,
            "R0-v3 relative identity drift")
    require(relative.get("gate1_position_transposition") is True
            and relative.get("position_replay_mismatches") == 0
            and relative.get("q_wdl_container_mismatches") == 0
            and relative.get("tt_search_state_mismatches") == 0
            and relative.get("explicit_distinct_parent_transposition") is True,
            "R0-v3 position/transposition failed")
    require(relative.get("gate2_f6_residual_invariance") is True
            and relative.get("f6_colour_mismatch_rows") == 0
            and relative.get("residual_colour_mismatch_rows") == 0,
            "R0-v3 F6/residual invariance failed")
    require(relative.get("gate3_relative_drift") is True
            and relative.get("engine_extra_drift_mismatch_count") == 0
            and relative.get("max_abs_extra_drift_engine_cp") == 0
            and relative.get("max_abs_extra_drift_float_cp", 1.0) <= 1e-10
            and relative.get("saturations") == 0
            and relative.get("legacy_gate4_executed") is False,
            "R0-v3 relative drift failed")

    leaf = load(args.leaf_contract)
    if leaf.get("passed") is not True:
        payload.update({"relative_contract": relative, "leaf_search_contract": leaf})
        return terminal(payload, args.out,
                        leaf.get("verdict", "R0_V3_REAL_SEARCH_SEMANTICS_FAILED"),
                        leaf)
    require(leaf.get("schema") == "jass.t3_f6_leaf_search_contract.v3"
            and leaf.get("code_sha") == args.code_sha
            and leaf.get("model_sha256") == MODEL_SHA
            and leaf.get("curriculum_sha256") == CURRICULUM_SHA
            and leaf.get("same_search_code_and_params") is True
            and leaf.get("candidate_only_changes_leaf_source") is True,
            "R0-v3 leaf/search identity drift")
    require(leaf.get("gate4a_isolated_static_leaf") is True
            and leaf.get("gate4a", {}).get("roots") == 128
            and leaf.get("gate4a", {}).get("mechanical_mismatches") == 0
            and leaf.get("gate4a", {}).get("t0_mismatches") == 0
            and leaf.get("gate4a", {}).get("t3_mismatches") == 0,
            "R0-v3 isolated negamax failed")
    require(leaf.get("gate4b_real_search_semantics") is True
            and leaf.get("gate4b", {}).get("roots") == 256
            and leaf.get("gate4b", {}).get("t0_mismatches") == 0
            and leaf.get("gate4b", {}).get("t3_mismatches") == 0,
            "R0-v3 real search semantics failed")
    require(leaf.get("gate5_terminal_tablebase") is True
            and leaf.get("egdb_available") is True
            and leaf.get("terminal_precedence") is True
            and leaf.get("tablebase_precedence") is True
            and all(leaf.get(key) == 0 for key in (
                "terminal_eval_calls_t0", "terminal_eval_calls_t3",
                "tablebase_eval_calls_t0", "tablebase_eval_calls_t3")),
            "R0-v3 terminal/tablebase precedence failed")

    parity = load(args.parity)
    runtime = load(args.runtime_profile)
    search = load(args.search_profile)
    loader = load(args.loader_auth)
    contract = load(args.runtime_contract)
    for report, failure_verdict in (
        (parity, "R0_V3_PYTHON_NATIVE_PARITY_FAILED"),
        (search, "R0_V3_DORMANT_OR_OFF_REGRESSION_FAILED"),
        (loader, "R0_V3_DORMANT_OR_OFF_REGRESSION_FAILED"),
        (contract, "R0_V3_DORMANT_OR_OFF_REGRESSION_FAILED"),
    ):
        if report.get("passed") is not True:
            payload.update({"relative_contract": relative,
                            "leaf_search_contract": leaf})
            return terminal(payload, args.out, failure_verdict, report)
    require(parity.get("schema") == "jass.t3_f6_runtime_parity.v2"
            and parity.get("rows") == 4096
            and parity.get("feature_coordinates") == 4096 * 66
            and parity.get("feature_bitwise_mismatches") == 0
            and parity.get("normalized_feature_coordinates") == 4096 * 66
            and parity.get("normalized_bitwise_mismatches") == 0
            and parity.get("integer_score_mismatches") == 0
            and parity.get("saturations") == 0
            and parity.get("scale_cp") == 1.0,
            "R0-v3 Python/native parity failed")
    require(runtime.get("positions") == 4096
            and runtime.get("warmup_passes") == 2
            and runtime.get("measured_passes") == 32
            and runtime.get("order_seed") == 2026092104
            and runtime.get("instrumented_passes") == 1
            and runtime.get("saturations") == 0
            and set(runtime.get("family_us_per_eval", {}))
                == {"F1", "F2", "F3", "F4", "F5"}
            and runtime.get("mlp_residual_us_per_eval", 0) > 0
            and runtime.get("movegen_calls", 0) > 0
            and runtime.get("response_enumerations_f2", 0) > 0,
            "R0-v3 runtime profile incomplete")
    for report in (parity, runtime):
        require(report.get("model_sha256") == MODEL_SHA
                and report.get("curriculum_sha256") == CURRICULUM_SHA,
                "R0-v3 parity/runtime artifact identity drift")
    require(search.get("passed") is True
            and search.get("off_regression", {}).get("static_positions") == 4096
            and search.get("off_regression", {}).get("static_mismatches") == 0
            and search.get("off_regression", {}).get(
                "q00_move_score_depth_nodes_mismatches") == 0
            and search.get("profile_roots") == 128
            and search.get("profile_roots_by_phase") == {
                phase: 32 for phase in ("P0", "P1", "P2", "P3")}
            and search.get("order_seed") == 2026092104,
            "R0-v3 OFF regression/search profile failed")
    require(loader.get("passed") is True
            and loader.get("off_absent_exact") is True
            and loader.get("on_exact_load") is True
            and loader.get("empty_env_rejected") is True
            and loader.get("wrong_artifact_rejected") is True,
            "R0-v3 loader fail-closed failed")
    require(args.executable is not None and args.reference_rffd is not None,
            "R0-v3 full readout inputs missing")
    require(contract.get("schema") == "jass.t3_f6_runtime_contract.v3"
            and contract.get("passed") is True
            and contract.get("same_executable_both_arms") is True
            and contract.get("leaf_only") is True
            and contract.get("model_sha256") == MODEL_SHA
            and contract.get("curriculum_sha256") == CURRICULUM_SHA
            and contract.get("executable_sha256") == sha(args.executable)
            and contract.get("book") == "OFF"
            and contract.get("threads") == 1
            and contract.get("tt_mb") == 16
            and contract.get("egdb") == "ON"
            and contract.get("maxplies") == 160,
            "R0-v3 runtime semantics contract failed")

    payload.update({
        "passed": True,
        "verdict": "R0_V3_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
        "terminal_r0_v3": False,
        "pool1_authorized": True,
        "automatic_next_job": "POOL1_ONLY",
        "executable_sha256": sha(args.executable),
        "relative_contract": relative,
        "leaf_search_contract": leaf,
        "python_native_parity": parity,
        "runtime_cost_profile": runtime,
        "search_cost_and_off_regression": search,
        "loader_authentication": loader,
        "runtime_contract": contract,
        "components": {
            "selection": sha(args.selection), "relative": sha(args.relative),
            "leaf_contract": sha(args.leaf_contract), "parity": sha(args.parity),
            "runtime_profile": sha(args.runtime_profile),
            "search_profile": sha(args.search_profile),
            "loader_auth": sha(args.loader_auth),
            "runtime_contract": sha(args.runtime_contract),
            "reference_rffd": sha(args.reference_rffd),
        },
    })
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
