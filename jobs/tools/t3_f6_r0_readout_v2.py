#!/usr/bin/env python3
"""Fail-closed R0-v2 relative production-leaf contract readout."""
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
PREREG_MERGE_SHA = "b6c747091aea265cd3f7ddeb4175fe05912ad255"
V1_TERMINAL_JOB = "cpx62-1647-l3-t3-f6-runtime-r0-terminal-readout-v1"
V1_TERMINAL_ATTEMPT = "20260829T120556Z-362d1a09"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def base_payload(args: argparse.Namespace, selection: dict, relative: dict) -> dict:
    return {
        "schema": "jass.t3_f6_r0_relative_production_leaf_contract.v2",
        "code_sha": args.code_sha,
        "prereg_merge_sha": PREREG_MERGE_SHA,
        "artifact_sha256": MODEL_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "rf1_sha256": RF1_SHA,
        "rf1_extractor_code": RF1_EXTRACTOR_CODE,
        "feature_order_sha256": FEATURE_ORDER_SHA,
        "selection": selection,
        "relative_contract": relative,
        "r0_v1_terminal": {
            "job": V1_TERMINAL_JOB,
            "attempt": V1_TERMINAL_ATTEMPT,
            "verdict": "R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED",
            "unchanged": True,
        },
        "strength_games_played": 0,
        "q00_games_played": 0,
        "post_freeze_fits": 0,
        "retunes": 0,
        "calibrations": 0,
        "promotion_authorized": False,
        "bake": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--relative", type=Path, required=True)
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
    require(sha(args.model) == MODEL_SHA, "frozen model bytes drift")
    require(sha(args.curriculum) == CURRICULUM_SHA, "CURRICULUM bytes drift")
    selection = load(args.selection)
    relative = load(args.relative)
    require(selection.get("passed") is True and selection.get("selected") == 4096,
            "R0-v2 corpus selection failed")
    require(selection.get("selection_seed") == 2026091702
            and selection.get("permutation_seed") == 2026091703
            and selection.get("benchmark_seed") == 2026091704,
            "R0-v2 target-blind seed drift")
    require(selection.get("selected_by_phase") == {
                name: 1024 for name in ("P0", "P1", "P2", "P3")},
            "R0-v2 phase balance drift")
    require(selection.get("forbidden_overlap") == 0
            and selection.get("score_reads") == 0
            and selection.get("wdl_reads") == 0
            and selection.get("deep_label_reads") == 0,
            "R0-v2 target-blind/exclusion contract failed")
    excluded_sources = selection.get("excluded_sources", {})
    require(any("r0-v1" in key for key in excluded_sources),
            "R0-v1 exclusion receipt missing")
    require(relative.get("schema") == "jass.t3_f6_relative_contract.v2"
            and relative.get("positions") == 4096
            and relative.get("permutation_seed") == 2026091703
            and relative.get("model_sha256") == MODEL_SHA
            and relative.get("curriculum_sha256") == CURRICULUM_SHA
            and relative.get("feature_order_sha256") == FEATURE_ORDER_SHA,
            "relative probe identity/geometry drift")

    payload = base_payload(args, selection, relative)
    if relative.get("passed") is not True:
        payload.update({
            "passed": False,
            "verdict": relative.get("verdict", "R0_V2_RELATIVE_PROBE_FAILED"),
            "terminal_r0_v2": True,
            "pool1_authorized": False,
            "automatic_next_job": None,
        })
        args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(json.dumps(payload, sort_keys=True))
        return 0

    require(relative.get("gate1_position_transposition") is True
            and relative.get("position_replay_mismatches") == 0
            and relative.get("q_wdl_container_mismatches") == 0
            and relative.get("tt_search_state_mismatches") == 0
            and relative.get("explicit_distinct_parent_transposition") is True,
            "R0-v2 position/transposition gate failed")
    require(relative.get("gate2_f6_residual_invariance") is True
            and relative.get("f6_colour_mismatch_rows") == 0
            and relative.get("residual_colour_mismatch_rows") == 0,
            "R0-v2 F6/residual invariance failed")
    require(relative.get("gate3_relative_drift") is True
            and relative.get("engine_extra_drift_mismatch_count") == 0
            and relative.get("max_abs_extra_drift_engine_cp") == 0
            and relative.get("max_abs_extra_drift_float_cp", 1.0) <= 1e-10
            and relative.get("saturations") == 0,
            "R0-v2 relative drift gate failed")
    require(relative.get("gate4_negamax_terminal_tb") is True
            and relative.get("negamax_single_inversion") is True
            and relative.get("terminal_precedence") is True
            and relative.get("egdb_available") is True
            and relative.get("tablebase_precedence") is True,
            "R0-v2 negamax/terminal/TB gate failed")

    parity = load(args.parity)
    runtime = load(args.runtime_profile)
    search = load(args.search_profile)
    loader = load(args.loader_auth)
    contract = load(args.runtime_contract)
    for report, fallback in (
        (parity, "R0_V2_PYTHON_NATIVE_PARITY_FAILED"),
        (search, "R0_V2_DORMANT_OR_OFF_REGRESSION_FAILED"),
        (loader, "R0_V2_DORMANT_OR_LOADER_CONTRACT_FAILED"),
        (contract, "R0_V2_RUNTIME_SEMANTICS_CONTRACT_FAILED"),
    ):
        if report.get("passed") is False:
            payload.update({
                "passed": False,
                "verdict": report.get("verdict", fallback),
                "terminal_r0_v2": True,
                "pool1_authorized": False,
                "automatic_next_job": None,
                "failed_report": report,
            })
            args.out.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(payload, sort_keys=True))
            return 0
    require(parity.get("passed") is True
            and parity.get("schema") == "jass.t3_f6_runtime_parity.v2"
            and parity.get("rows") == 4096
            and parity.get("feature_coordinates") == 4096 * 66
            and parity.get("feature_bitwise_mismatches") == 0
            and parity.get("normalized_feature_coordinates") == 4096 * 66
            and parity.get("normalized_bitwise_mismatches") == 0
            and parity.get("integer_score_mismatches") == 0
            and parity.get("saturations") == 0
            and parity.get("scale_cp") == 1.0,
            "R0-v2 Python/native parity failed")
    require(runtime.get("positions") == 4096
            and runtime.get("warmup_passes") == 2
            and runtime.get("measured_passes") == 32
            and runtime.get("order_seed") == 2026091704
            and runtime.get("instrumented_passes") == 1
            and runtime.get("saturations") == 0
            and set(runtime.get("family_us_per_eval", {})) == {
                "F1", "F2", "F3", "F4", "F5"}
            and runtime.get("mlp_residual_us_per_eval", 0) > 0
            and runtime.get("movegen_calls", 0) > 0
            and runtime.get("response_enumerations_f2", 0) > 0,
            "R0-v2 runtime-cost profile incomplete")
    require(search.get("passed") is True
            and search.get("off_regression", {}).get("static_positions") == 4096
            and search.get("off_regression", {}).get("static_mismatches") == 0
            and search.get("off_regression", {}).get(
                "q00_move_score_depth_nodes_mismatches") == 0
            and search.get("profile_roots") == 128
            and search.get("profile_roots_by_phase") == {
                name: 32 for name in ("P0", "P1", "P2", "P3")}
            and search.get("order_seed") == 2026091704,
            "R0-v2 OFF regression/search profile failed")
    require(loader.get("passed") is True
            and loader.get("off_absent_exact") is True
            and loader.get("on_exact_load") is True
            and loader.get("empty_env_rejected") is True
            and loader.get("wrong_artifact_rejected") is True,
            "R0-v2 fail-closed loader authentication failed")
    require(contract.get("passed") is True
            and contract.get("same_executable_both_arms") is True
            and contract.get("leaf_only") is True
            and contract.get("book") == "OFF"
            and contract.get("threads") == 1
            and contract.get("tt_mb") == 16
            and contract.get("egdb") == "ON"
            and contract.get("maxplies") == 160,
            "R0-v2 runtime semantics contract failed")
    for report in (relative, parity, runtime):
        require(report.get("model_sha256") == MODEL_SHA
                and report.get("curriculum_sha256") == CURRICULUM_SHA,
                "R0-v2 report artifact identity drift")
    require(args.executable is not None and args.reference_rffd is not None,
            "full R0-v2 readout inputs missing")

    payload.update({
        "passed": True,
        "verdict": "R0_RELATIVE_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
        "terminal_r0_v2": False,
        "pool1_authorized": True,
        "automatic_next_job": "POOL1_ONLY",
        "executable_sha256": sha(args.executable),
        "components": {
            "selection": sha(args.selection),
            "relative": sha(args.relative),
            "parity": sha(args.parity),
            "runtime_profile": sha(args.runtime_profile),
            "search_profile": sha(args.search_profile),
            "loader_auth": sha(args.loader_auth),
            "runtime_contract": sha(args.runtime_contract),
            "reference_rffd": sha(args.reference_rffd),
        },
        "python_native_parity": parity,
        "runtime_cost_profile": runtime,
        "search_cost_and_off_regression": search,
        "loader_authentication": loader,
        "runtime_contract": contract,
    })
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
