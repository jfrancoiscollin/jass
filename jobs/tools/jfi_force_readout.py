#!/usr/bin/env python3
"""Audit the preregistered JFI-E Pool1 decision and optional two-pool verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


BOOTSTRAP_SAMPLES = 200_000
POOL_SEEDS = {1: 2026120111, 2: 2026120121}
CHAINED_SEED = 2026120199
SUPPORTED = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0])


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def audit_gate(path, *, pool, view, candidate_sha, curriculum_sha, executable_sha, search_params):
    raw = json.loads(Path(path).read_text())
    paired = raw.get("paired_opening") or {}
    scores = np.asarray(paired.get("per_opening_scores", []), dtype=np.float64)
    wins, draws, losses = (int(raw.get(key, -1)) for key in ("wins_a", "draws", "wins_b"))
    rate = (wins + 0.5 * draws) / 6000
    require(raw.get("complete") is True and raw.get("n") == 6000, f"pool{pool}/{view}: incomplete")
    require(wins + draws + losses == 6000 and scores.shape == (3000,), f"pool{pool}/{view}: count drift")
    require(np.all(np.isin(scores, SUPPORTED)) and math.isclose(scores.mean(), rate, abs_tol=1e-12)
            and math.isclose(float(raw.get("rate", -1)), rate, abs_tol=1e-12)
            and math.isclose(float(paired.get("rate", -1)), rate, abs_tol=1e-12),
            f"pool{pool}/{view}: paired scores drift")
    require((paired.get("wins_a"), paired.get("draws"), paired.get("wins_b")) ==
            (wins, draws, losses), f"pool{pool}/{view}: paired W/D/L drift")
    require(paired.get("method") == "paired_colour_opening_cluster_bootstrap",
            f"pool{pool}/{view}: bootstrap method drift")
    require(paired.get("bootstrap_samples") == BOOTSTRAP_SAMPLES and paired.get("seed") == POOL_SEEDS[pool],
            f"pool{pool}/{view}: bootstrap contract drift")
    require(paired.get("n_openings") == 3000 and paired.get("games_per_opening") == 2,
            f"pool{pool}/{view}: opening budget drift")
    require(raw.get("pairs") == 1 and raw.get("nshards") == 12 and raw.get("max_parallel") == 12,
            f"pool{pool}/{view}: topology drift")
    require(raw.get("max_plies") == 160 and raw.get("game_timeout") == 180,
            f"pool{pool}/{view}: timeout/plies drift")
    require(raw.get("fail_on_game_error") is True and raw.get("book_disabled") is True,
            f"pool{pool}/{view}: technical guard drift")
    require(raw.get("jass_a_sha256") == executable_sha == raw.get("jass_b_sha256"),
            f"pool{pool}/{view}: executable drift")
    require(raw.get("pattern_a_sha256") == candidate_sha and raw.get("pattern_b_sha256") == curriculum_sha,
            f"pool{pool}/{view}: model bytes drift")
    openings_sha = raw.get("openings_file_sha256")
    require(isinstance(openings_sha, str) and len(openings_sha) == 64
            and all(char in "0123456789abcdef" for char in openings_sha),
            f"pool{pool}/{view}: opening digest drift")
    require(raw.get("search_params_a") == search_params == raw.get("search_params_b")
            and len(search_params.split(",")) == 63,
            f"pool{pool}/{view}: search parameter drift")
    require(int(paired.get("error_draws", -1)) == 0, f"pool{pool}/{view}: technical error draws")
    errors_by_arm = paired.get("errors_by_arm") or {}
    errors_by_colour = paired.get("errors_by_candidate_colour") or {}
    require(set(errors_by_arm) == {"a", "b", "unknown"}
            and all(int(value) == 0 for value in errors_by_arm.values())
            and set(errors_by_colour) == {"white", "black"}
            and all(int(value) == 0 for value in errors_by_colour.values()),
            f"pool{pool}/{view}: arm asymmetry")
    colours = paired.get("score_by_candidate_colour") or {}
    require(set(colours) == {"white", "black"} and all(item.get("games") == 3000 for item in colours.values()),
            f"pool{pool}/{view}: colour balance drift")
    if view == "native":
        require(raw.get("depth") is None and math.isclose(float(raw.get("movetime")), 0.1),
                f"pool{pool}/native: budget drift")
    elif view == "q00":
        require(raw.get("depth") == 9 and raw.get("movetime") is None, f"pool{pool}/q00: budget drift")
    else:
        raise ValueError(f"unknown view {view}")
    return ({
        "wins": wins, "draws": draws, "losses": losses, "games": 6000,
        "openings": 3000, "rate": rate, "ci_low": float(paired["ci_low"]),
        "ci_high": float(paired["ci_high"]),
        "probability_rate_gt_half": float(paired["probability_rate_gt_half"]),
        "error_draws": 0, "raw_sha256": sha256_file(path),
        "openings_sha256": openings_sha,
    }, scores)


def chained_native(left, right, *, samples=BOOTSTRAP_SAMPLES, seed=CHAINED_SEED):
    require(left.shape == right.shape == (3000,), "chained bootstrap requires two 3000-opening pools")
    rng = np.random.default_rng(seed); draws = np.empty(samples, dtype=np.float64)
    for start in range(0, samples, 500):
        stop = min(start + 500, samples); take = stop - start
        a = left[rng.integers(0, 3000, size=(take, 3000))].mean(axis=1)
        b = right[rng.integers(0, 3000, size=(take, 3000))].mean(axis=1)
        draws[start:stop] = 0.5 * (a + b)
    low, high = np.quantile(draws, [0.025, 0.975])
    return {"method":"equal_pool_weight_chained_paired_opening_bootstrap",
            "rate": float(np.concatenate((left, right)).mean()), "ci_low": float(low),
            "ci_high": float(high), "probability_rate_gt_half": float(np.mean(draws > .5)),
            "bootstrap_samples": samples, "bootstrap_seed": seed, "openings": 6000, "games": 12000}


def build_pool1(native_path, q00_path, candidate_sha, curriculum_sha, executable_sha, search_params):
    native, _ = audit_gate(native_path, pool=1, view="native", candidate_sha=candidate_sha,
                           curriculum_sha=curriculum_sha, executable_sha=executable_sha,
                           search_params=search_params)
    q00, _ = audit_gate(q00_path, pool=1, view="q00", candidate_sha=candidate_sha,
                        curriculum_sha=curriculum_sha, executable_sha=executable_sha,
                        search_params=search_params)
    require(native["openings_sha256"] == q00["openings_sha256"], "Pool1 views use different openings")
    positive = native["rate"] > .5
    return {"schema":"jass.jfi.e_pool1_readout.v1",
            "verdict":"JFI_POOL1_NATIVE_POSITIVE" if positive else "JFI_JASS_NATIVE_STRENGTH_NOT_SUPPORTED",
            "primary_native":native,"secondary_q00":q00,"pool2_authorized":positive,
            "markers":{"SCAN_READS":0,"PROMOTION_AUTHORIZED":False}}


def build_final(paths, candidate_sha, curriculum_sha, executable_sha, search_params, *,
                chained_samples=BOOTSTRAP_SAMPLES, chained_seed=CHAINED_SEED):
    evidence = {}; scores = {}
    for pool in (1, 2):
        evidence[f"pool{pool}"] = {}
        for view in ("native", "q00"):
            item, values = audit_gate(paths[(pool, view)], pool=pool, view=view,
                                      candidate_sha=candidate_sha, curriculum_sha=curriculum_sha,
                                      executable_sha=executable_sha, search_params=search_params)
            evidence[f"pool{pool}"][view] = item; scores[(pool, view)] = values
        require(evidence[f"pool{pool}"]["native"]["openings_sha256"] ==
                evidence[f"pool{pool}"]["q00"]["openings_sha256"],
                f"Pool{pool} views use different openings")
    require(evidence["pool1"]["native"]["openings_sha256"] !=
            evidence["pool2"]["native"]["openings_sha256"],
            "Pool2 must use a fresh independent opening pool")
    require(evidence["pool1"]["native"]["rate"] > .5, "Pool2 was not authorized by Pool1")
    chained = chained_native(
        scores[(1,"native")], scores[(2,"native")],
        samples=chained_samples, seed=chained_seed,
    )
    pool2_positive = evidence["pool2"]["native"]["rate"] > .5
    established = pool2_positive and chained["ci_low"] > .5
    verdict = ("JFI_JASS_NATIVE_STRENGTH_ESTABLISHED" if established else
               "JFI_JASS_NATIVE_STRENGTH_NOT_SUPPORTED" if not pool2_positive else
               "JFI_JASS_NATIVE_STRENGTH_INCONCLUSIVE")
    return {"schema":"jass.jfi.e_two_pool_readout.v1","verdict":verdict,
            "primary_view":"native_0p1s","secondary_view":"q00_depth9",
            "per_pool":evidence,"chained_native":chained,
            "decision":{"pool1_native_gt_half":True,"pool2_native_gt_half":pool2_positive,
                        "chained_native_ci95_low_gt_half":chained["ci_low"]>.5,
                        "zero_technical_asymmetry":True},
            "markers":{"SCAN_READS":0,"PROMOTION_AUTHORIZED":False,"THIRD_POOL_AUTHORIZED":False}}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--mode",choices=("pool1","final"),required=True)
    for pool in (1,2):
        for view in ("native","q00"): ap.add_argument(f"--pool{pool}-{view}")
    ap.add_argument("--candidate-sha",required=True); ap.add_argument("--curriculum-sha",required=True)
    ap.add_argument("--executable-sha",required=True); ap.add_argument("--search-params",required=True)
    ap.add_argument("--out",required=True); args=ap.parse_args(argv)
    if args.mode=="pool1":
        if not args.pool1_native or not args.pool1_q00: raise SystemExit("Pool1 paths required")
        report=build_pool1(args.pool1_native,args.pool1_q00,args.candidate_sha,args.curriculum_sha,
                           args.executable_sha,args.search_params)
    else:
        raw_paths={(p,v):getattr(args,f"pool{p}_{v}") for p in (1,2) for v in ("native","q00")}
        if any(value is None for value in raw_paths.values()): raise SystemExit("four gate paths required")
        paths={key:Path(value) for key,value in raw_paths.items()}
        report=build_final(paths,args.candidate_sha,args.curriculum_sha,args.executable_sha,args.search_params)
    Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n"); return 0


if __name__=="__main__": raise SystemExit(main())
