#!/usr/bin/env python3
"""Audit and combine the preregistered two-pool CTX3 force evidence."""

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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def audit_gate(
    path: Path,
    *,
    view: str,
    pool_index: int,
    bootstrap_seed: int,
) -> tuple[dict[str, Any], np.ndarray]:
    raw = _load(path)
    paired = raw.get("paired_opening") or {}
    scores = np.asarray(paired.get("per_opening_scores", []), dtype=np.float64)
    wins = int(raw.get("wins_a", -1))
    draws = int(raw.get("draws", -1))
    losses = int(raw.get("wins_b", -1))
    rate = (wins + 0.5 * draws) / 6000.0

    _require(raw.get("complete") is True, f"pool{pool_index}/{view}: incomplete gate")
    _require(raw.get("n") == 6000 and wins + draws + losses == 6000,
             f"pool{pool_index}/{view}: WDL/cardinality drift")
    _require(scores.shape == (3000,), f"pool{pool_index}/{view}: opening evidence drift")
    _require(bool(np.all(np.isin(scores, SUPPORTED_OPENING_SCORES))),
             f"pool{pool_index}/{view}: unsupported paired score")
    _require(math.isclose(float(scores.mean()), rate, abs_tol=1e-12),
             f"pool{pool_index}/{view}: score/WDL rate mismatch")
    _require(math.isclose(float(raw.get("rate")), rate, abs_tol=5e-7),
             f"pool{pool_index}/{view}: raw rate drift")
    _require(math.isclose(float(paired.get("rate")), rate, abs_tol=1e-12),
             f"pool{pool_index}/{view}: paired rate drift")
    _require(paired.get("method") == "paired_colour_opening_cluster_bootstrap",
             f"pool{pool_index}/{view}: paired method drift")
    _require(paired.get("n_openings") == 3000 and paired.get("games_per_opening") == 2,
             f"pool{pool_index}/{view}: paired budget drift")
    _require(paired.get("bootstrap_samples") == 200000,
             f"pool{pool_index}/{view}: bootstrap samples drift")
    _require(paired.get("seed") == bootstrap_seed,
             f"pool{pool_index}/{view}: bootstrap seed drift")
    _require(int(paired.get("error_draws", 0)) <= 120,
             f"pool{pool_index}/{view}: error limit exceeded")
    _require(raw.get("pairs") == 1 and raw.get("nshards") == 12
             and raw.get("max_parallel") == 12,
             f"pool{pool_index}/{view}: execution topology drift")
    _require(raw.get("jass_a") == raw.get("jass_b"),
             f"pool{pool_index}/{view}: engine identity drift")
    _require(Path(str(raw.get("pattern_a"))).name == "aligned.pjtw"
             and Path(str(raw.get("pattern_b"))).name == "shuffled.pjtw",
             f"pool{pool_index}/{view}: arm identity drift")
    _require(raw.get("search_params_a") == raw.get("search_params_b")
             and len(str(raw.get("search_params_a", "")).split(",")) == 63,
             f"pool{pool_index}/{view}: search parameter drift")
    if view == "native":
        _require(raw.get("depth") is None
                 and math.isclose(float(raw.get("movetime")), 0.1),
                 f"pool{pool_index}/native: budget drift")
    elif view == "q00":
        _require(raw.get("depth") == 9 and raw.get("movetime") is None,
                 f"pool{pool_index}/q00: budget drift")
    else:
        raise ValueError(f"unknown view: {view}")

    evidence = {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "games": 6000,
        "openings": 3000,
        "rate": rate,
        "ci_low": float(paired["ci_low"]),
        "ci_high": float(paired["ci_high"]),
        "probability_rate_gt_half": float(paired["probability_rate_gt_half"]),
        "error_draws": int(paired.get("error_draws", 0)),
        "raw_sha256": _sha256(path),
    }
    return evidence, scores


def combine_pools(
    scores: list[np.ndarray], *, bootstrap_samples: int, bootstrap_seed: int
) -> dict[str, Any]:
    _require(len(scores) == 2 and all(x.shape == (3000,) for x in scores),
             "two 3000-opening score arrays are required")
    means = [float(x.mean()) for x in scores]
    standard_errors = [float(x.std(ddof=1) / math.sqrt(x.size)) for x in scores]
    denominator = math.sqrt(standard_errors[0] ** 2 + standard_errors[1] ** 2)
    if denominator == 0.0:
        inter_pool_z = 0.0 if means[0] == means[1] else math.inf
    else:
        inter_pool_z = (means[0] - means[1]) / denominator
    compatible = abs(inter_pool_z) <= 1.959963984540054

    rng = np.random.default_rng(bootstrap_seed)
    bootstrap = np.empty(bootstrap_samples, dtype=np.float64)
    done = 0
    chunk = 500
    while done < bootstrap_samples:
        take = min(chunk, bootstrap_samples - done)
        left = scores[0][rng.integers(0, 3000, size=(take, 3000))].mean(axis=1)
        right = scores[1][rng.integers(0, 3000, size=(take, 3000))].mean(axis=1)
        bootstrap[done : done + take] = 0.5 * (left + right)
        done += take

    return {
        "pool_rates": means,
        "pool_standard_errors": standard_errors,
        "inter_pool_z": float(inter_pool_z),
        "inter_pool_compatible_95": bool(compatible),
        "rate": float(np.concatenate(scores).mean()),
        "ci_low": float(np.quantile(bootstrap, 0.025)),
        "ci_high": float(np.quantile(bootstrap, 0.975)),
        "probability_rate_gt_half": float(np.mean(bootstrap > 0.5)),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": bootstrap_seed,
        "openings": 6000,
        "games": 12000,
    }


def build_report(
    *,
    gate_paths: dict[tuple[int, str], Path],
    pool_certificate: dict[str, Any],
    model_certificate: dict[str, Any],
    bootstrap_samples: int,
    native_seed: int,
    q00_seed: int,
    gate_bootstrap_seeds: dict[int, int],
) -> dict[str, Any]:
    _require(pool_certificate.get("verdict") == "JASS_CONTEXT3_TWO_FRESH_POOLS_READY",
             "pool certificate verdict drift")
    _require(pool_certificate.get("mutually_disjoint") is True,
             "opening pools are not mutually disjoint")
    pools = pool_certificate.get("pools") or []
    _require(len(pools) == 2 and all(x.get("openings") == 3000 for x in pools),
             "pool certificate cardinality drift")
    _require(pools[0].get("sha256") != pools[1].get("sha256"),
             "opening pool hashes are identical")
    _require(model_certificate.get("verdict") == "JASS_CONTEXT3_FORCE_MODELS_AUTHENTICATED",
             "model certificate verdict drift")
    _require(model_certificate.get("distinct") is True,
             "aligned and shuffled models are not distinct")

    evidence: dict[str, dict[str, Any]] = {"pool1": {}, "pool2": {}}
    scores_by_view: dict[str, list[np.ndarray]] = {"native": [], "q00": []}
    for pool_index in (1, 2):
        for view in ("native", "q00"):
            item, scores = audit_gate(
                gate_paths[(pool_index, view)],
                view=view,
                pool_index=pool_index,
                bootstrap_seed=gate_bootstrap_seeds[pool_index],
            )
            evidence[f"pool{pool_index}"][view] = item
            scores_by_view[view].append(scores)

    native = combine_pools(
        scores_by_view["native"],
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=native_seed,
    )
    q00 = combine_pools(
        scores_by_view["q00"],
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=q00_seed,
    )
    both_native_positive = all(rate > 0.5 for rate in native["pool_rates"])
    established = (
        both_native_positive
        and native["inter_pool_compatible_95"]
        and native["ci_low"] > 0.5
        and native["probability_rate_gt_half"] >= 0.975
    )
    verdict = (
        "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_ESTABLISHED_POSITIVE"
        if established
        else "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED"
    )
    return {
        "schema": "jass.l3_context3_two_pool_force_readout.v1",
        "verdict": verdict,
        "scientific_status": verdict,
        "contrast": "CTX3_ALIGNED_vs_CTX3_SHUFFLED",
        "primary_view": "native_movetime_0.1",
        "diagnostic_view": "Q00_depth9",
        "per_pool_evidence": evidence,
        "native": native,
        "q00_d9_diagnostic": q00,
        "decision": {
            "both_native_pool_points_positive": both_native_positive,
            "native_inter_pool_compatible_95": native["inter_pool_compatible_95"],
            "combined_native_ci_excludes_half": native["ci_low"] > 0.5,
            "combined_native_probability_ge_0_975": (
                native["probability_rate_gt_half"] >= 0.975
            ),
            "primary_established_positive": established,
            "q00_can_override_primary": False,
        },
        "protocol": {
            "two_fresh_disjoint_pools": True,
            "openings_total": 6000,
            "native_games_total": 12000,
            "q00_diagnostic_games_total": 12000,
            "games_total": 24000,
            "paired_colours": True,
            "models_reused": True,
            "refits": 0,
            "new_selfplay": 0,
            "frozen_cohorts_read": 0,
        },
        "pool_certificate": pool_certificate,
        "model_certificate": model_certificate,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for pool_index in (1, 2):
        for view in ("native", "q00"):
            parser.add_argument(f"--pool{pool_index}-{view}", required=True)
    parser.add_argument("--pool-certificate", required=True)
    parser.add_argument("--model-certificate", required=True)
    parser.add_argument("--gate-bootstrap-seed-pool1", type=int, required=True)
    parser.add_argument("--gate-bootstrap-seed-pool2", type=int, required=True)
    parser.add_argument("--combined-native-seed", type=int, required=True)
    parser.add_argument("--combined-q00-seed", type=int, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200000)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gate_paths = {
        (pool_index, view): Path(getattr(args, f"pool{pool_index}_{view}"))
        for pool_index in (1, 2)
        for view in ("native", "q00")
    }
    report = build_report(
        gate_paths=gate_paths,
        pool_certificate=_load(Path(args.pool_certificate)),
        model_certificate=_load(Path(args.model_certificate)),
        bootstrap_samples=args.bootstrap_samples,
        native_seed=args.combined_native_seed,
        q00_seed=args.combined_q00_seed,
        gate_bootstrap_seeds={
            1: args.gate_bootstrap_seed_pool1,
            2: args.gate_bootstrap_seed_pool2,
        },
    )
    out = Path(args.out)
    if out.exists():
        raise ValueError(f"refusing to overwrite {out}")
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
