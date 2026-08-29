#!/usr/bin/env python3
"""Native-only causal strength readout for frozen T3-A/F6 runtime v2."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.t3_f6_strength_readout import cell, chained, game_stats, load_gate, sha

MODEL_SHA = "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
FEATURE_ORDER_SHA = "cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e"
POOL1_GENERATOR_SEED = 2026091801
POOL1_SELECTION_SEED = 2026091802
POOL1_BOOTSTRAP_SEED = 2026091803
POOL2_GENERATOR_SEED = 2026091901
POOL2_SELECTION_SEED = 2026091902
POOL2_BOOTSTRAP_SEED = 2026091903
CHAINED_BOOTSTRAP_SEED = 2026092001


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def authenticate_pool(path: Path, openings: Path, generator_seed: int,
                      selection_seed: int) -> dict:
    provenance = json.loads(path.read_text(encoding="utf-8"))
    require(provenance.get("passed") is True
            and provenance.get("verdict") == "T3_F6_FRESH_FORCE_POOL_READY",
            "pool provenance failed")
    require(provenance.get("openings") == 3000
            and provenance.get("generator_seed") == generator_seed
            and provenance.get("selection_seed") == selection_seed,
            "pool geometry/seed drift")
    require(provenance.get("forbidden_overlap") == 0
            and provenance.get("score_reads") == 0
            and provenance.get("wdl_reads") == 0
            and provenance.get("deep_label_reads") == 0,
            "pool target-blind/exclusion drift")
    require(provenance.get("pool_sha256") == sha(openings),
            "pool opening SHA drift")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool1-native", type=Path, required=True)
    parser.add_argument("--pool2-native", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--pool1-openings", type=Path, required=True)
    parser.add_argument("--pool1-provenance", type=Path, required=True)
    parser.add_argument("--pool2-openings", type=Path)
    parser.add_argument("--pool2-provenance", type=Path)
    parser.add_argument("--r0-summary", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--search-params", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    require(re.fullmatch(r"[0-9a-f]{40}", args.code_sha) is not None,
            "code SHA contract drift")
    require(sha(args.model) == MODEL_SHA, "frozen T3-A bytes drift")
    require(sha(args.curriculum) == CURRICULUM_SHA, "CURRICULUM bytes drift")
    executable_sha = sha(args.executable)
    r0 = json.loads(args.r0_summary.read_text(encoding="utf-8"))
    require(r0.get("verdict") == "R0_RELATIVE_PRODUCTION_LEAF_CONTRACT_ESTABLISHED"
            and r0.get("passed") is True and r0.get("pool1_authorized") is True,
            "R0-v2 authorization missing")
    require(r0.get("code_sha") == args.code_sha
            and r0.get("artifact_sha256") == MODEL_SHA
            and r0.get("curriculum_sha256") == CURRICULUM_SHA
            and r0.get("executable_sha256") == executable_sha,
            "R0/force code or byte drift")
    contract = r0.get("runtime_contract", {})
    require(contract.get("search_params") == args.search_params
            and contract.get("same_executable_both_arms") is True
            and contract.get("leaf_only") is True,
            "R0/force runtime semantics drift")

    p1_sha = sha(args.pool1_openings)
    p1_provenance = authenticate_pool(
        args.pool1_provenance, args.pool1_openings,
        POOL1_GENERATOR_SEED, POOL1_SELECTION_SEED,
    )
    p1 = load_gate(args.pool1_native, seed=POOL1_BOOTSTRAP_SEED, view="native",
                   executable_sha=executable_sha, openings_sha=p1_sha,
                   search_params=args.search_params)
    p1_rate = game_stats(p1)[0]
    payload: dict[str, object] = {
        "schema": "jass.t3_f6_runtime_strength_readout.v2",
        "artifact_sha256": MODEL_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "feature_order_sha256": FEATURE_ORDER_SHA,
        "executable_sha256": executable_sha,
        "code_sha": args.code_sha,
        "search_params": args.search_params,
        "r0_summary_sha256": sha(args.r0_summary),
        "r0_relative_drift": r0.get("relative_contract", {}),
        "r0_python_native_parity": r0.get("python_native_parity", {}),
        "r0_runtime_cost_profile": r0.get("runtime_cost_profile", {}),
        "runtime_contract": contract,
        "pool1_openings_sha256": p1_sha,
        "pool1_provenance_sha256": sha(args.pool1_provenance),
        "pool1_provenance": p1_provenance,
        "pool1": {"native_primary": cell(p1, args.pool1_native)},
        "pool1_native_games": 6000,
        "pool2_native_games": 0,
        "q00_games": 0,
        "q00_status": "SEPARATE_HOME_DIAGNOSTIC_NONBLOCKING",
        "q00_can_rescue_native": False,
        "post_freeze_fits": 0,
        "retunes": 0,
        "calibrations": 0,
        "promotion_authorized": False,
        "bake": False,
    }
    if p1_rate <= 0.5:
        require(args.pool2_native is None and args.pool2_openings is None
                and args.pool2_provenance is None,
                "Pool2 supplied despite non-positive Pool1 native point")
        payload.update({
            "passed": False,
            "verdict": "T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED",
            "decision_reason": "POOL1_NATIVE_POINT_ESTIMATE_NOT_ABOVE_HALF",
            "pool2_authorized": False,
            "automatic_next_job": None,
        })
    elif args.pool2_native is None:
        require(args.pool2_openings is None and args.pool2_provenance is None,
                "partial Pool2 inputs")
        payload.update({
            "passed": True,
            "verdict": "T3_F6_POOL1_POSITIVE_POOL2_AUTHORIZED",
            "decision_reason": "POOL1_NATIVE_POINT_ESTIMATE_ABOVE_HALF",
            "pool2_authorized": True,
            "automatic_next_job": "POOL2_ONLY",
        })
    else:
        require(args.pool2_openings is not None and args.pool2_provenance is not None,
                "incomplete Pool2 inputs")
        p2_sha = sha(args.pool2_openings)
        require(p2_sha != p1_sha, "Pool1/Pool2 byte identity")
        p2_provenance = authenticate_pool(
            args.pool2_provenance, args.pool2_openings,
            POOL2_GENERATOR_SEED, POOL2_SELECTION_SEED,
        )
        p2 = load_gate(args.pool2_native, seed=POOL2_BOOTSTRAP_SEED, view="native",
                       executable_sha=executable_sha, openings_sha=p2_sha,
                       search_params=args.search_params)
        p2_rate = game_stats(p2)[0]
        chained_native = chained(
            p1, p2, samples=200000, seed=CHAINED_BOOTSTRAP_SEED,
        )
        payload.update({
            "pool2": {"native_primary": cell(p2, args.pool2_native)},
            "pool2_openings_sha256": p2_sha,
            "pool2_provenance_sha256": sha(args.pool2_provenance),
            "pool2_provenance": p2_provenance,
            "pool2_native_games": 6000,
            "chained": {"native_primary": chained_native},
            "pool2_authorized": False,
            "automatic_next_job": None,
            "same_artifact_bytes_both_pools": True,
            "same_curriculum_bytes_both_pools": True,
            "same_runtime_semantics_both_pools": True,
        })
        if p2_rate <= 0.5:
            verdict = "T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED"
            reason = "POOL2_NATIVE_POINT_ESTIMATE_NOT_ABOVE_HALF"
            supported = False
        elif float(chained_native["ci_low"]) <= 0.5:
            verdict = "T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE"
            reason = "BOTH_POOLS_POSITIVE_CHAINED_CI_LOW_NOT_ABOVE_HALF"
            supported = False
        else:
            verdict = "T3_F6_RUNTIME_STRENGTH_SUPPORTED"
            reason = "BOTH_POOLS_POSITIVE_CHAINED_CI_LOW_ABOVE_HALF"
            supported = True
        payload.update({"passed": supported, "verdict": verdict,
                        "decision_reason": reason})

    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
