#!/usr/bin/env python3
"""Preregistered Pool1/Pool2 decision and chained paired-opening bootstrap."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

MODEL_SHA = "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"


def load_gate(path: Path, *, seed: int, view: str, executable_sha: str,
              openings_sha: str, search_params: str) -> dict:
    gate = json.loads(path.read_text(encoding="utf-8"))
    paired = gate.get("paired_opening", {})
    if gate.get("complete") is not True or gate.get("n") != 6000:
        raise ValueError(f"{path}: force budget/complete drift")
    if paired.get("n_openings") != 3000 or paired.get("games_per_opening") != 2:
        raise ValueError(f"{path}: paired opening geometry drift")
    if paired.get("bootstrap_samples") != 200000 or paired.get("seed") != seed:
        raise ValueError(f"{path}: bootstrap contract drift")
    per_opening = np.asarray(paired.get("per_opening_scores", ()), dtype=np.float64)
    if (per_opening.shape != (3000,) or not np.all(np.isfinite(per_opening))
            or not np.all(np.isin(per_opening, (0.0, 0.25, 0.5, 0.75, 1.0)))):
        raise ValueError(f"{path}: paired opening score vector drift")
    if ((paired.get("wins_a"), paired.get("draws"), paired.get("wins_b"))
            != (gate.get("wins_a"), gate.get("draws"), gate.get("wins_b"))):
        raise ValueError(f"{path}: paired/raw WDL drift")
    exact_rate = (int(gate["wins_a"]) + 0.5 * int(gate["draws"])) / int(gate["n"])
    if (not math.isclose(float(per_opening.mean()), exact_rate, abs_tol=1e-15)
            or not math.isclose(float(paired.get("rate", -1.0)), exact_rate, abs_tol=1e-15)):
        raise ValueError(f"{path}: paired score rate drift")
    if paired.get("error_draws") != 0 or any(paired.get("errors_by_arm", {}).values()):
        raise ValueError(f"{path}: technical game errors make cell uninterpretable")
    colours = paired.get("score_by_candidate_colour", {})
    if any(colours.get(colour, {}).get("games") != 3000 for colour in ("white", "black")):
        raise ValueError(f"{path}: candidate colour balance drift")
    if gate.get("jass_a") != gate.get("jass_b"):
        raise ValueError(f"{path}: executable path asymmetry")
    if gate.get("pattern_a") != gate.get("pattern_b"):
        raise ValueError(f"{path}: CURRICULUM path asymmetry")
    if gate.get("search_params_a") != gate.get("search_params_b"):
        raise ValueError(f"{path}: search parameter asymmetry")
    if gate.get("t3_f6_model_a") is None or gate.get("t3_f6_model_b") is not None:
        raise ValueError(f"{path}: evaluator arm wiring drift")
    if gate.get("fail_on_game_error") is not True:
        raise ValueError(f"{path}: fail-closed game contract drift")
    if gate.get("book_disabled") is not True:
        raise ValueError(f"{path}: book-OFF contract drift")
    if gate.get("jass_a_sha256") != executable_sha or gate.get("jass_b_sha256") != executable_sha:
        raise ValueError(f"{path}: executable byte drift")
    if gate.get("pattern_a_sha256") != CURRICULUM_SHA or gate.get("pattern_b_sha256") != CURRICULUM_SHA:
        raise ValueError(f"{path}: CURRICULUM byte drift")
    if gate.get("t3_f6_model_a_sha256") != MODEL_SHA or gate.get("t3_f6_model_b_sha256") is not None:
        raise ValueError(f"{path}: T3-A byte/wiring drift")
    if gate.get("openings_file_sha256") != openings_sha:
        raise ValueError(f"{path}: opening-pool byte drift")
    if gate.get("search_params_a") != search_params or gate.get("search_params_b") != search_params:
        raise ValueError(f"{path}: frozen Q00 fingerprint drift")
    if gate.get("pairs") != 1 or gate.get("max_plies") != 160:
        raise ValueError(f"{path}: paired/maxplies geometry drift")
    if gate.get("game_timeout") is not None:
        raise ValueError(f"{path}: synthetic timeout/draw policy is forbidden")
    if view == "native":
        if gate.get("movetime") != 0.1 or gate.get("depth") is not None:
            raise ValueError(f"{path}: native 0.1 s/move contract drift")
    elif view == "q00":
        if gate.get("depth") != 9 or gate.get("movetime") is not None:
            raise ValueError(f"{path}: Q00 depth-9 contract drift")
    else:
        raise ValueError(f"unknown force view {view}")
    return gate


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def elo(rate: float) -> float:
    if rate <= 0: return -800.0
    if rate >= 1: return 800.0
    return -400.0 * math.log10(1.0 / rate - 1.0)


def game_stats(gate: dict) -> tuple[float, float, float]:
    wins = int(gate["wins_a"])
    draws = int(gate["draws"])
    n = int(gate["n"])
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    return rate, max(0.0, rate - 1.96 * se), min(1.0, rate + 1.96 * se)


def cell(gate: dict, raw_path: Path) -> dict:
    paired = gate["paired_opening"]
    rate, ci_low, ci_high = game_stats(gate)
    return {
        "wins_t3": gate["wins_a"], "draws": gate["draws"],
        "wins_curriculum": gate["wins_b"], "games": gate["n"],
        "score_rate_t3": rate, "elo_t3_minus_curriculum": elo(rate),
        "game_ci95": [ci_low, ci_high],
        "elo_ci95": [elo(ci_low), elo(ci_high)],
        "paired_ci95": [paired["ci_low"], paired["ci_high"]],
        "probability_score_gt_half": paired["probability_rate_gt_half"],
        "errors_by_side": paired["errors_by_arm"],
        "errors_by_candidate_colour": paired.get("errors_by_candidate_colour", {}),
        "score_by_candidate_colour": paired.get("score_by_candidate_colour", {}),
        "telemetry": paired.get("telemetry", {}),
        "raw_result_sha256": sha(raw_path),
    }


def chained(pool1: dict, pool2: dict, *, samples: int, seed: int) -> dict:
    if samples != 200000:
        raise ValueError("chained bootstrap samples drift")
    vectors = [np.asarray(pool["paired_opening"]["per_opening_scores"], dtype=np.float64)
               for pool in (pool1, pool2)]
    if any(vector.shape != (3000,) for vector in vectors):
        raise ValueError("chained opening vector shape drift")
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = 2048
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        means = []
        for vector in vectors:
            indices = rng.integers(0, 3000, size=(stop - start, 3000))
            means.append(vector[indices].mean(axis=1))
        draws[start:stop] = 0.5 * (means[0] + means[1])
    lo, hi = np.quantile(draws, [0.025, 0.975])
    return {
        "method": "equal_pool_weight_chained_paired_opening_bootstrap",
        "samples": samples, "seed": seed,
        "score_rate": float(0.5 * (vectors[0].mean() + vectors[1].mean())),
        "ci_low": float(lo), "ci_high": float(hi),
        "probability_score_gt_half": float(np.mean(draws > 0.5)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool1-native", type=Path, required=True)
    parser.add_argument("--pool1-q00", type=Path, required=True)
    parser.add_argument("--pool2-native", type=Path)
    parser.add_argument("--pool2-q00", type=Path)
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
    parser.add_argument("--pool1-native-seed", type=int, default=2026091003)
    parser.add_argument("--pool1-q00-seed", type=int, default=2026091004)
    parser.add_argument("--pool2-native-seed", type=int, default=2026091103)
    parser.add_argument("--pool2-q00-seed", type=int, default=2026091104)
    parser.add_argument("--chained-native-seed", type=int, default=2026091201)
    parser.add_argument("--chained-q00-seed", type=int, default=2026091202)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if sha(args.model) != MODEL_SHA or sha(args.curriculum) != CURRICULUM_SHA:
        raise ValueError("frozen evaluator bytes drift")
    if not re.fullmatch(r"[0-9a-f]{40}", args.code_sha):
        raise ValueError("code SHA contract drift")
    executable_sha = sha(args.executable)
    pool1_sha = sha(args.pool1_openings)
    pool1_provenance = json.loads(args.pool1_provenance.read_text(encoding="utf-8"))
    if (pool1_provenance.get("passed") is not True
            or pool1_provenance.get("verdict") != "T3_F6_FRESH_FORCE_POOL_READY"
            or pool1_provenance.get("openings") != 3000
            or pool1_provenance.get("generator_seed") != 2026091001
            or pool1_provenance.get("selection_seed") != 2026091002
            or pool1_provenance.get("forbidden_overlap") != 0
            or pool1_provenance.get("pool_sha256") != pool1_sha):
        raise ValueError("Pool1 provenance contract drift")
    r0 = json.loads(args.r0_summary.read_text(encoding="utf-8"))
    if (r0.get("passed") is not True
            or r0.get("verdict") != "R0_PRODUCTION_LEAF_CONTRACT_PASS"
            or r0.get("artifact_sha256") != MODEL_SHA
            or r0.get("curriculum_sha256") != CURRICULUM_SHA
            or r0.get("executable_sha256") != executable_sha
            or r0.get("code_sha") != args.code_sha
            or r0.get("runtime_contract", {}).get("search_params") != args.search_params):
        raise ValueError("R0 authorization/byte contract drift")
    p1n = load_gate(args.pool1_native, seed=args.pool1_native_seed, view="native",
                    executable_sha=executable_sha, openings_sha=pool1_sha,
                    search_params=args.search_params)
    p1q = load_gate(args.pool1_q00, seed=args.pool1_q00_seed, view="q00",
                    executable_sha=executable_sha, openings_sha=pool1_sha,
                    search_params=args.search_params)
    p1_rate = game_stats(p1n)[0]
    payload: dict[str, object] = {
        "schema": "jass.t3_f6_runtime_strength_readout.v1",
        "artifact_sha256": MODEL_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "feature_order_sha256": "cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e",
        "executable_sha256": executable_sha,
        "code_sha": args.code_sha,
        "search_params": args.search_params,
        "r0_summary_sha256": sha(args.r0_summary),
        "r0_runtime_cost_profile": r0.get("runtime_cost_profile", {}),
        "runtime_contract": r0.get("runtime_contract", {}),
        "pool1_openings_sha256": pool1_sha,
        "pool1_provenance_sha256": sha(args.pool1_provenance),
        "pool1_provenance": pool1_provenance,
        "pool1": {"native_primary": cell(p1n, args.pool1_native),
                  "q00_depth9_diagnostic": cell(p1q, args.pool1_q00)},
        "q00_can_rescue_native": False,
        "promotion_authorized": False,
        "bake": False,
    }
    if p1_rate <= 0.5:
        if (args.pool2_native is not None or args.pool2_q00 is not None
                or args.pool2_openings is not None or args.pool2_provenance is not None):
            raise ValueError("Pool2 supplied despite non-positive Pool1 native point")
        payload.update({"passed": False, "pool2_authorized": False,
                        "verdict": "T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED"})
        q00_rate = game_stats(p1q)[0]
        payload["conditional_interpretation"] = (
            "Q00_POSITIVE_NATIVE_NONPOSITIVE_RUNTIME_COST_HYPOTHESIS"
            if q00_rate > 0.5 else
            "RANKING_TO_ALPHA_BETA_VALUE_INCOMPATIBILITY_DIAGNOSTIC_REQUIRED"
        )
    else:
        payload["pool2_authorized"] = True
        supplied = (args.pool2_native, args.pool2_q00, args.pool2_openings,
                    args.pool2_provenance)
        if any(value is None for value in supplied) and not all(value is None for value in supplied):
            raise ValueError("Pool2 views and openings must be supplied together")
        if args.pool2_native is None:
            payload.update({"passed": True,
                            "verdict": "T3_F6_POOL1_POSITIVE_POOL2_AUTHORIZED"})
        else:
            assert (args.pool2_q00 is not None and args.pool2_openings is not None
                    and args.pool2_provenance is not None)
            pool2_sha = sha(args.pool2_openings)
            if pool2_sha == pool1_sha:
                raise ValueError("Pool2 bytes equal Pool1")
            pool2_provenance = json.loads(
                args.pool2_provenance.read_text(encoding="utf-8")
            )
            if (pool2_provenance.get("passed") is not True
                    or pool2_provenance.get("verdict") != "T3_F6_FRESH_FORCE_POOL_READY"
                    or pool2_provenance.get("openings") != 3000
                    or pool2_provenance.get("generator_seed") != 2026091101
                    or pool2_provenance.get("selection_seed") != 2026091102
                    or pool2_provenance.get("forbidden_overlap") != 0
                    or pool2_provenance.get("pool_sha256") != pool2_sha):
                raise ValueError("Pool2 provenance contract drift")
            p2n = load_gate(args.pool2_native, seed=args.pool2_native_seed, view="native",
                            executable_sha=executable_sha, openings_sha=pool2_sha,
                            search_params=args.search_params)
            p2q = load_gate(args.pool2_q00, seed=args.pool2_q00_seed, view="q00",
                            executable_sha=executable_sha, openings_sha=pool2_sha,
                            search_params=args.search_params)
            chained_native = chained(p1n, p2n, samples=200000, seed=args.chained_native_seed)
            chained_q00 = chained(p1q, p2q, samples=200000, seed=args.chained_q00_seed)
            payload["pool2_openings_sha256"] = pool2_sha
            payload["pool2_provenance_sha256"] = sha(args.pool2_provenance)
            payload["pool2_provenance"] = pool2_provenance
            payload["pool2"] = {"native_primary": cell(p2n, args.pool2_native),
                                "q00_depth9_diagnostic": cell(p2q, args.pool2_q00)}
            payload["chained"] = {"native_primary": chained_native,
                                  "q00_depth9_diagnostic": chained_q00}
            if game_stats(p2n)[0] <= 0.5:
                verdict = "T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED"
                passed = False
            elif chained_native["ci_low"] > 0.5:
                verdict = "T3_F6_RUNTIME_STRENGTH_SUPPORTED"
                passed = True
            else:
                verdict = "T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE"
                passed = False
            payload.update({"passed": passed, "verdict": verdict,
                            "same_artifact_bytes_both_pools": True,
                            "same_curriculum_bytes_both_pools": True,
                            "same_runtime_semantics_both_pools": True})
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
