#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit and combine the three preregistered replay-DOE force contrasts."""

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


def _gate_assignment(raw: str) -> tuple[tuple[str, int, str], Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("expected CONTRAST:POOL:VIEW=PATH")
    lhs, path = raw.split("=", 1)
    parts = lhs.split(":")
    if len(parts) != 3 or parts[2] not in ("native", "q00"):
        raise argparse.ArgumentTypeError("expected CONTRAST:POOL:VIEW=PATH")
    try:
        pool = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("POOL must be 1 or 2") from exc
    if pool not in (1, 2):
        raise argparse.ArgumentTypeError("POOL must be 1 or 2")
    return (parts[0], pool, parts[2]), Path(path)


def audit_gate(
    path: Path,
    *,
    contrast: str,
    candidate: str,
    baseline: str,
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
    label = f"{contrast}/pool{pool_index}/{view}"

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
    _require(int(paired.get("error_draws", 0)) <= 120, f"{label}: error limit exceeded")
    _require(raw.get("pairs") == 1 and raw.get("nshards") == 12
             and raw.get("max_parallel") == 12, f"{label}: topology drift")
    _require(raw.get("jass_a") == raw.get("jass_b"), f"{label}: engine drift")
    _require(Path(str(raw.get("pattern_a"))).name == f"{candidate}.pjtw"
             and Path(str(raw.get("pattern_b"))).name == f"{baseline}.pjtw",
             f"{label}: arm identity drift")
    _require(raw.get("search_params_a") == raw.get("search_params_b")
             and len(str(raw.get("search_params_a", "")).split(",")) == 63,
             f"{label}: search parameter drift")
    if view == "native":
        _require(raw.get("depth") is None and math.isclose(float(raw.get("movetime")), 0.1),
                 f"{label}: native budget drift")
    else:
        _require(raw.get("depth") == 9 and raw.get("movetime") is None,
                 f"{label}: Q00 budget drift")
    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "games": games,
        "openings": openings,
        "rate": rate,
        "ci_low": float(paired["ci_low"]),
        "ci_high": float(paired["ci_high"]),
        "probability_rate_gt_half": float(paired["probability_rate_gt_half"]),
        "error_draws": int(paired.get("error_draws", 0)),
        "raw_sha256": _sha256(path),
    }, scores


def combine(
    scores: list[np.ndarray], *, samples: int, seed: int, openings: int
) -> dict[str, Any]:
    _require(len(scores) == 2 and all(x.shape == (openings,) for x in scores),
             "two equal opening-score arrays required")
    means = [float(x.mean()) for x in scores]
    ses = [float(x.std(ddof=1) / math.sqrt(x.size)) for x in scores]
    denom = math.sqrt(ses[0] ** 2 + ses[1] ** 2)
    z = 0.0 if denom == 0.0 and means[0] == means[1] else (
        math.inf if denom == 0.0 else (means[0] - means[1]) / denom
    )
    compatible = abs(z) <= 1.959963984540054
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = max(1, min(500, 2_000_000 // openings))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        left = scores[0][rng.integers(0, openings, size=(stop - start, openings))].mean(axis=1)
        right = scores[1][rng.integers(0, openings, size=(stop - start, openings))].mean(axis=1)
        draws[start:stop] = 0.5 * (left + right)
    return {
        "pool_rates": means,
        "pool_standard_errors": ses,
        "inter_pool_z": float(z),
        "inter_pool_compatible_95": bool(compatible),
        "rate": float(np.concatenate(scores).mean()),
        "ci_low": float(np.quantile(draws, 0.025)),
        "ci_high": float(np.quantile(draws, 0.975)),
        "probability_rate_gt_half": float(np.mean(draws > 0.5)),
        "bootstrap_samples": samples,
        "bootstrap_seed": seed,
        "openings": 2 * openings,
        "games": 4 * openings,
    }


def classify(native: dict[str, Any]) -> str:
    positive = (
        all(rate > 0.5 for rate in native["pool_rates"])
        and native["inter_pool_compatible_95"]
        and native["ci_low"] > 0.5
        and native["probability_rate_gt_half"] >= 0.975
    )
    negative = (
        all(rate < 0.5 for rate in native["pool_rates"])
        and native["inter_pool_compatible_95"]
        and native["ci_high"] < 0.5
        and native["probability_rate_gt_half"] <= 0.025
    )
    if positive:
        return "ESTABLISHED_POSITIVE"
    if negative:
        return "ESTABLISHED_NEGATIVE"
    return "NOT_ESTABLISHED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--pool-certificate", required=True)
    parser.add_argument("--model-certificate", required=True)
    parser.add_argument("--gate", action="append", type=_gate_assignment, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    protocol = _load(Path(args.protocol))
    pool_certificate = _load(Path(args.pool_certificate))
    model_certificate = _load(Path(args.model_certificate))
    openings = int(protocol.get("openings_per_pool", 0))
    samples = int(protocol.get("bootstrap_samples", 0))
    _require(protocol.get("schema") == "jass.l3_exploratory_replay_doe_force_protocol.v1",
             "force protocol schema drift")
    _require(openings == 1500 and samples == 100000, "force budget drift")
    _require(pool_certificate.get("verdict") == "JASS_EXPLORATORY_REPLAY_DOE_TWO_POOLS_READY",
             "pool certificate verdict drift")
    _require(pool_certificate.get("mutually_disjoint") is True,
             "force pools are not disjoint")
    _require(model_certificate.get("verdict") == "JASS_EXPLORATORY_REPLAY_FOUR_MODELS_READY",
             "model certificate verdict drift")
    _require(set((model_certificate.get("models") or {}).keys()) == {"A", "B", "C", "D"},
             "model certificate arm drift")

    gates = dict(args.gate)
    expected_keys = {
        (contrast, pool, view)
        for contrast in protocol["contrasts"]
        for pool in (1, 2)
        for view in ("native", "q00")
    }
    _require(set(gates) == expected_keys, "gate path set drift")

    reports: dict[str, Any] = {}
    for contrast, spec in protocol["contrasts"].items():
        evidence = {"pool1": {}, "pool2": {}}
        scores = {"native": [], "q00": []}
        for pool in (1, 2):
            for view in ("native", "q00"):
                item, array = audit_gate(
                    gates[(contrast, pool, view)], contrast=contrast,
                    candidate=spec["candidate"], baseline=spec["baseline"],
                    view=view, pool_index=pool, openings=openings,
                    bootstrap_samples=samples,
                    bootstrap_seed=int(spec["gate_seeds"][f"pool{pool}"][view]),
                )
                evidence[f"pool{pool}"][view] = item
                scores[view].append(array)
        native = combine(
            scores["native"], samples=samples,
            seed=int(spec["combined_seeds"]["native"]), openings=openings,
        )
        q00 = combine(
            scores["q00"], samples=samples,
            seed=int(spec["combined_seeds"]["q00"]), openings=openings,
        )
        reports[contrast] = {
            "candidate": spec["candidate"],
            "baseline": spec["baseline"],
            "primary_view": "native_movetime_0.1",
            "diagnostic_view": "Q00_depth9",
            "classification": classify(native),
            "per_pool": evidence,
            "native": native,
            "q00_diagnostic": q00,
            "q00_can_override_native": False,
        }

    primary = reports[protocol["primary_contrast"]]["classification"]
    verdict = {
        "ESTABLISHED_POSITIVE": "JASS_EXPLORATORY_REPLAY25_ESTABLISHED_POSITIVE",
        "ESTABLISHED_NEGATIVE": "JASS_EXPLORATORY_REPLAY25_ESTABLISHED_NEGATIVE",
        "NOT_ESTABLISHED": "JASS_EXPLORATORY_REPLAY25_NOT_ESTABLISHED",
    }[primary]
    payload = {
        "schema": "jass.l3_exploratory_replay_doe_force_readout.v1",
        "verdict": verdict,
        "experiment_class": "EXPLORATORY_POST_CTX4",
        "ctx4_verdict_unchanged": "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED",
        "primary_contrast": protocol["primary_contrast"],
        "contrasts": reports,
        "protocol": protocol,
        "pool_certificate": pool_certificate,
        "model_certificate": model_certificate,
        "fits_performed": 4,
        "new_selfplay_corpus_records": 2_000_000,
        "force_games_total": len(reports) * 2 * 2 * 2 * openings,
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
