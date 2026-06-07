#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""SPSA tuner for jass search parameters (Phase 1 — search avancé).

Simultaneous Perturbation Stochastic Approximation over the search
constants exposed in src/search_params.hpp. Each iteration perturbs all
tuned parameters by ±c_k·Δ (Δ ∈ {-1,+1} per parameter), plays a single
head-to-head self-play match θ+ vs θ- via

    jass --benchmark-search-params <net> "<θ+ spec>" "<θ- spec>" depth pairs ...

and nudges θ toward whichever side won. The win rate of θ+ vs θ- is the
objective (0.5 = tie); the SPSA gradient estimate is

    g_i ≈ (rate - 0.5) / (c_k · Δ_i)

and the update θ_i += a_k · g_i (clamped to each parameter's range).

Output: the best spec found (written to --out) plus a running log. The
caller then validates the best spec against the default via a fresh,
larger match before shipping.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path


# name -> (default, lo, hi, perturbation magnitude c0, integer?)
TUNABLE = {
    "rfp_margin":      (100, 40, 200, 20, True),
    "nmp_r_base":      (2,   1,   4,   1, True),
    "nmp_r_div":       (4,   2,   8,   1, True),
    "singular_margin": (2,   1,   8,   1, True),
    "lmr_depth_div":   (6,   3,  12,   1, True),
    "lmr_idx_div":     (8,   3,  16,   1, True),
    "lmp_d1":          (4,   2,   8,   1, True),
    "lmp_d2":          (8,   4,  16,   2, True),
    "lmp_d3":          (14,  6,  28,   2, True),
    "aspiration_initial": (50, 15, 120, 10, True),
    # Phase-1 Tier-2 features — tuned ON/OFF + margins so the eval being
    # tuned (e.g. a pattern, whose score distribution differs from the
    # NNUE these were tried with in 0138) decides for ITSELF whether they
    # help, rather than inheriting the NNUE verdict. 0 = feature off.
    "razor_max_depth":   (0,  0,   4,   1, True),
    "razor_margin":      (200, 80, 400, 40, True),
    "probcut_min_depth": (0,  0,   8,   1, True),
    "probcut_margin":    (150, 80, 300, 40, True),
    "ext_promotion":     (0,  0,   1,   1, True),
    # 1b — raffinements search incrémentaux. Gated, neutres par défaut ; le
    # tuner décide ON/OFF + le seuil de profondeur POUR l'éval tunée (0 = off).
    # Les sous-knobs (iid_reduction, multicut_*) restent à leurs défauts
    # raisonnables, ajustables manuellement par spec si un run le motive —
    # les inclure ici diluerait le SPSA quand la feature est off.
    "use_improving":      (0,  0,   1,   1, True),
    "use_conthist":       (0,  0,   1,   1, True),
    "iid_min_depth":      (0,  0,   8,   1, True),
    "multicut_min_depth": (0,  0,  10,   1, True),
}


def spec(theta: dict[str, float], extra: dict[str, int] | None = None) -> str:
    parts = [f"{k}={int(round(v))}" for k, v in theta.items()]
    if extra:
        parts += [f"{k}={v}" for k, v in extra.items()]
    return ",".join(parts)


def clamp(theta: dict[str, float]) -> dict[str, float]:
    out = {}
    for k, v in theta.items():
        _, lo, hi, _, _ = TUNABLE[k]
        out[k] = min(hi, max(lo, v))
    return out


_RATE_RE = re.compile(r"A score rate:\s*([0-9.]+)")


def play(jass: str, net: str, spec_a: str, spec_b: str,
         depth: int, pairs: int, threads: int, movetime_ms: int) -> float:
    """Return A's score rate (θ+ vs θ-)."""
    cmd = [jass, "--benchmark-search-params", net, spec_a, spec_b,
           str(depth), str(pairs), str(threads), str(movetime_ms)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    m = _RATE_RE.search(out.stdout)
    if not m:
        sys.stderr.write(out.stdout + out.stderr)
        raise RuntimeError("could not parse score rate from jass output")
    return float(m.group(1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jass", required=True)
    ap.add_argument("--net", default="hc",
                    help="network path, or 'hc' for handcrafted eval")
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--pairs", type=int, default=6,
                    help="opening pairs per match (games = pairs*2*9)")
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--movetime-ms", type=int, default=0,
                    help=">0 tunes at fixed time (recommended once PVS is on)")
    ap.add_argument("--use-pvs", type=int, default=1,
                    help="hold use_pvs fixed at this value during tuning")
    ap.add_argument("--a0", type=float, default=2.0, help="SPSA learning-rate scale")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("spsa-best.json"))
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    theta = {k: float(v[0]) for k, v in TUNABLE.items()}
    held = {"use_pvs": args.use_pvs}

    # SPSA gain schedules (Spall's recommended forms).
    A = max(1, args.iters // 10)
    alpha, gamma = 0.602, 0.101

    print(f"SPSA: {len(TUNABLE)} params, {args.iters} iters, "
          f"{args.pairs*18} games/iter, net={args.net}, "
          f"depth={args.depth}, movetime_ms={args.movetime_ms}, "
          f"use_pvs={args.use_pvs}")

    for k in range(1, args.iters + 1):
        ak = args.a0 / (k + A) ** alpha
        ck = 1.0 / k ** gamma
        delta = {p: (1 if rng.random() < 0.5 else -1) for p in TUNABLE}

        theta_plus, theta_minus = {}, {}
        for p in TUNABLE:
            c0 = TUNABLE[p][3]
            step = ck * c0 * delta[p]
            theta_plus[p]  = theta[p] + step
            theta_minus[p] = theta[p] - step
        theta_plus  = clamp(theta_plus)
        theta_minus = clamp(theta_minus)

        rate = play(args.jass, args.net,
                    spec(theta_plus, held), spec(theta_minus, held),
                    args.depth, args.pairs, args.threads, args.movetime_ms)

        # SPSA ascent on win-rate: g_i = (rate-0.5)/(ck*c0*delta_i).
        for p in TUNABLE:
            c0 = TUNABLE[p][3]
            g = (rate - 0.5) / (ck * c0 * delta[p])
            theta[p] += ak * g * c0  # scale step by the param's natural magnitude
        theta = clamp(theta)

        print(f"  iter {k:3d}: θ+ rate={rate:.3f}  "
              f"spec={spec({p: theta[p] for p in TUNABLE})}")

    # SPSA output is the FINAL accumulated point (not the noisiest-iteration
    # one — that earlier heuristic just echoed the defaults when the match
    # signal was weak, cf 0136). The caller validates this vs the defaults.
    best = clamp(theta)
    out = {"params": {p: int(round(best[p])) for p in TUNABLE},
           "held": held,
           "spec": spec(best, held)}
    args.out.write_text(json.dumps(out, indent=2))
    print("\nBest spec (validate against default before shipping):")
    print("  " + out["spec"])
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
