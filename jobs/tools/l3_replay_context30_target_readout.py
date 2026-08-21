#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit the two-pool target-only REPLAY25 force experiment.

The candidate and baseline must share byte-identical training rows, metadata,
sample weights, CURRICULUM prior, architecture and optimizer recipe.  The only
scientific difference is the target: aligned historical CONTEXT_30 versus
native terminal WDL.  Native 0.1 s is primary; Q00 depth 9 is diagnostic and
cannot reverse the native classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


SUPPORTED_OPENING_SCORES = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0])


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _elo(rate: float) -> float | None:
    if not 0.0 < rate < 1.0:
        return None
    return 400.0 * math.log10(rate / (1.0 - rate))


def audit_gate(
    path: Path,
    *,
    view: str,
    pool_index: int,
    openings: int,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> tuple[dict[str, Any], np.ndarray]:
    raw = _load(path)
    paired = raw.get("paired_opening") or {}
    scores = np.asarray(paired.get("per_opening_scores", []), dtype=np.float64)
    wins = int(raw.get("wins_a", -1))
    draws = int(raw.get("draws", -1))
    losses = int(raw.get("wins_b", -1))
    games = 2 * openings
    rate = (wins + 0.5 * draws) / games
    label = f"pool{pool_index}/{view}"

    _require(raw.get("complete") is True, f"{label}: incomplete gate")
    _require(raw.get("n") == games and wins + draws + losses == games,
             f"{label}: WDL/cardinality drift")
    _require(scores.shape == (openings,), f"{label}: opening evidence drift")
    _require(bool(np.all(np.isin(scores, SUPPORTED_OPENING_SCORES))),
             f"{label}: unsupported paired score")
    _require(math.isclose(float(scores.mean()), rate, abs_tol=1e-12),
             f"{label}: score/WDL mismatch")
    _require(math.isclose(float(raw.get("rate")), rate, abs_tol=5e-7),
             f"{label}: raw rate drift")
    _require(math.isclose(float(paired.get("rate")), rate, abs_tol=1e-12),
             f"{label}: paired rate drift")
    _require(paired.get("method") == "paired_colour_opening_cluster_bootstrap",
             f"{label}: paired method drift")
    _require(paired.get("n_openings") == openings and paired.get("games_per_opening") == 2,
             f"{label}: paired budget drift")
    _require(paired.get("bootstrap_samples") == bootstrap_samples,
             f"{label}: bootstrap sample drift")
    _require(paired.get("seed") == bootstrap_seed, f"{label}: bootstrap seed drift")
    _require(int(paired.get("error_draws", 0)) <= 120,
             f"{label}: error limit exceeded")
    _require(raw.get("pairs") == 1 and raw.get("nshards") == 12
             and raw.get("max_parallel") == 12,
             f"{label}: execution topology drift")
    _require(raw.get("jass_a") == raw.get("jass_b"), f"{label}: engine drift")
    _require(Path(str(raw.get("pattern_a"))).name == "B_C30.pjtw"
             and Path(str(raw.get("pattern_b"))).name == "B_NATIVE.pjtw",
             f"{label}: model assignment drift")
    _require(raw.get("search_params_a") == raw.get("search_params_b")
             and len(str(raw.get("search_params_a", "")).split(",")) == 63,
             f"{label}: search parameter drift")
    if view == "native":
        _require(raw.get("depth") is None
                 and math.isclose(float(raw.get("movetime")), 0.1),
                 f"{label}: native budget drift")
    elif view == "q00":
        _require(raw.get("depth") == 9 and raw.get("movetime") is None,
                 f"{label}: Q00 budget drift")
    else:
        raise ValueError(f"unknown view: {view}")

    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "games": games,
        "openings": openings,
        "rate": rate,
        "elo_indicative": _elo(rate),
        "ci_low": float(paired["ci_low"]),
        "ci_high": float(paired["ci_high"]),
        "probability_rate_gt_half": float(paired["probability_rate_gt_half"]),
        "error_draws": int(paired.get("error_draws", 0)),
        "raw_sha256": _sha256(path),
    }, scores


def combine(
    scores: list[np.ndarray], *, samples: int, seed: int, openings: int
) -> dict[str, Any]:
    _require(len(scores) == 2 and all(row.shape == (openings,) for row in scores),
             "two equal opening-score arrays required")
    means = [float(row.mean()) for row in scores]
    ses = [float(row.std(ddof=1) / math.sqrt(row.size)) for row in scores]
    denominator = math.sqrt(ses[0] ** 2 + ses[1] ** 2)
    if denominator == 0.0:
        z = 0.0 if means[0] == means[1] else math.inf
    else:
        z = (means[0] - means[1]) / denominator
    compatible = abs(z) <= 1.959963984540054

    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = max(1, min(500, 2_000_000 // openings))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        left = scores[0][rng.integers(0, openings, size=(stop - start, openings))].mean(axis=1)
        right = scores[1][rng.integers(0, openings, size=(stop - start, openings))].mean(axis=1)
        draws[start:stop] = 0.5 * (left + right)

    rate = float(np.concatenate(scores).mean())
    return {
        "pool_rates": means,
        "pool_standard_errors": ses,
        "inter_pool_z": float(z),
        "inter_pool_compatible_95": bool(compatible),
        "rate": rate,
        "elo_indicative": _elo(rate),
        "ci_low": float(np.quantile(draws, 0.025)),
        "ci_high": float(np.quantile(draws, 0.975)),
        "probability_rate_gt_half": float(np.mean(draws > 0.5)),
        "bootstrap_samples": samples,
        "bootstrap_seed": seed,
        "openings": 2 * openings,
        "games": 4 * openings,
    }


def classify(result: dict[str, Any]) -> str:
    positive = (
        all(rate > 0.5 for rate in result["pool_rates"])
        and result["inter_pool_compatible_95"]
        and result["ci_low"] > 0.5
        and result["probability_rate_gt_half"] >= 0.975
    )
    negative = (
        all(rate < 0.5 for rate in result["pool_rates"])
        and result["inter_pool_compatible_95"]
        and result["ci_high"] < 0.5
        and result["probability_rate_gt_half"] <= 0.025
    )
    if positive:
        return "ESTABLISHED_POSITIVE"
    if negative:
        return "ESTABLISHED_NEGATIVE"
    return "NOT_ESTABLISHED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for pool in (1, 2):
        for view in ("native", "q00"):
            parser.add_argument(f"--pool{pool}-{view}", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--pool-certificate", required=True)
    parser.add_argument("--model-certificate", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    protocol = _load(Path(args.protocol))
    pools = _load(Path(args.pool_certificate))
    models = _load(Path(args.model_certificate))
    openings = int(protocol.get("openings_per_pool", 0))
    samples = int(protocol.get("bootstrap_samples", 0))

    _require(protocol.get("schema") == "jass.l3_replay_context30_force_protocol.v1",
             "force protocol schema drift")
    _require(openings == 3000 and samples == 200000, "force budget drift")
    _require(protocol.get("issue") == 552, "tracking issue drift")
    _require(protocol.get("candidate") == "B_REPLAY25_CONTEXT30"
             and protocol.get("baseline") == "B_REPLAY25_NATIVE",
             "force assignment drift")
    _require(protocol.get("primary_view") == "native_movetime_0.1"
             and protocol.get("q00_can_override_native") is False,
             "primary/diagnostic role drift")
    _require(pools.get("schema") == "jass.l3_replay_context30_pools.v1"
             and pools.get("verdict") == "JASS_REPLAY_CONTEXT30_TWO_FRESH_POOLS_READY",
             "pool certificate verdict drift")
    _require(pools.get("mutually_disjoint") is True
             and pools.get("all_historical_overlaps_zero") is True,
             "pool disjointness drift")
    _require(pools.get("historical_exclusion_count") == 23,
             "historical exclusion count drift")
    pool_rows = pools.get("pools") or []
    _require(len(pool_rows) == 2 and all(row.get("openings") == openings for row in pool_rows),
             "pool certificate cardinality drift")

    _require(models.get("schema") == "jass.l3_replay_context30_models.v1"
             and models.get("verdict") == "JASS_REPLAY_CONTEXT30_MODELS_READY",
             "model certificate verdict drift")
    candidate = models.get("candidate") or {}
    baseline = models.get("baseline") or {}
    shared = models.get("shared_contract") or {}
    _require(candidate.get("label") == "B_REPLAY25_CONTEXT30"
             and baseline.get("label") == "B_REPLAY25_NATIVE",
             "model certificate assignment drift")
    _require(candidate.get("target") == "CONTEXT_30_ALIGNED_alpha_0.30"
             and baseline.get("target") == "native_JNNW_WDL",
             "target assignment drift")
    _require(candidate.get("model_raw_sha256") != baseline.get("model_raw_sha256"),
             "candidate and baseline unexpectedly identical")
    _require(shared.get("single_scientific_difference") == "training_target"
             and shared.get("same_data") is True
             and shared.get("same_metadata") is True
             and shared.get("same_sample_weights") is True
             and shared.get("same_prior") is True
             and shared.get("same_fit_recipe") is True,
             "target-only causal contract drift")
    _require(models.get("refits") == 1 and models.get("new_selfplay") == 0
             and models.get("frozen_cohorts_read") == 0,
             "model scope drift")

    evidence: dict[str, dict[str, Any]] = {"pool1": {}, "pool2": {}}
    score_arrays: dict[str, list[np.ndarray]] = {"native": [], "q00": []}
    for pool in (1, 2):
        for view in ("native", "q00"):
            path = Path(getattr(args, f"pool{pool}_{view}"))
            seed = int(protocol["gate_seeds"][f"pool{pool}"][view])
            row, array = audit_gate(
                path,
                view=view,
                pool_index=pool,
                openings=openings,
                bootstrap_samples=samples,
                bootstrap_seed=seed,
            )
            evidence[f"pool{pool}"][view] = row
            score_arrays[view].append(array)

    native = combine(
        score_arrays["native"],
        samples=samples,
        seed=int(protocol["combined_seeds"]["native"]),
        openings=openings,
    )
    q00 = combine(
        score_arrays["q00"],
        samples=samples,
        seed=int(protocol["combined_seeds"]["q00"]),
        openings=openings,
    )
    native_class = classify(native)
    q00_class = classify(q00)
    verdict = {
        "ESTABLISHED_POSITIVE": "JASS_REPLAY_CONTEXT30_TARGET_ESTABLISHED_POSITIVE",
        "ESTABLISHED_NEGATIVE": "JASS_REPLAY_CONTEXT30_TARGET_ESTABLISHED_NEGATIVE",
        "NOT_ESTABLISHED": "JASS_REPLAY_CONTEXT30_TARGET_NOT_ESTABLISHED",
    }[native_class]

    payload = {
        "schema": "jass.l3_replay_context30_target_readout.v1",
        "verdict": verdict,
        "contrast": "B_REPLAY25_CONTEXT30_vs_B_REPLAY25_NATIVE",
        "causal_factor": "training_target_only",
        "primary_view": "native_movetime_0.1",
        "diagnostic_view": "Q00_depth9",
        "native_classification": native_class,
        "q00_classification": q00_class,
        "next_stage_recommended": (
            "DIRECT_B_CONTEXT30_VS_CURRICULUM_GATE" if native_class == "ESTABLISHED_POSITIVE" else None
        ),
        "per_pool": evidence,
        "native": native,
        "q00_diagnostic": q00,
        "q00_can_override_native": False,
        "protocol": protocol,
        "pool_certificate": pools,
        "model_certificate": models,
        "games_total": 24000,
        "models_reused": 1,
        "refits": 1,
        "new_selfplay": 0,
        "frozen_cohorts_read": 0,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    out = Path(args.out)
    if out.exists():
        raise ValueError(f"refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
