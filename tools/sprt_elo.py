#!/usr/bin/env python3
"""Elo + 95% CI and SPRT decision from W/D/L game counts.

Proper game-based confirmation for the experiment plan (the deterministic proxy
in eval_proxy.py tracks the learning curve; this confirms milestones in actual
games with controlled error). Standard computer-chess practice (fishtest).

  Elo:  python3 tools/sprt_elo.py --wdl W D L
  SPRT: python3 tools/sprt_elo.py --wdl W D L --elo0 0 --elo1 5 [--alpha .05 --beta .05]

SPRT decides "is the elo difference >= elo1" vs "<= elo0" while playing the
FEWEST games: accept H1, accept H0, or continue. Use it to stop a match as soon
as the result is significant instead of fixing N blindly.
"""
import argparse, math


def score_and_ci(W, D, L):
    N = W + D + L
    if N == 0:
        return 0.5, 0.0, 0.0
    s = (W + 0.5 * D) / N
    # variance of the per-game score (draws cut variance), then of the mean
    var = (W * (1 - s) ** 2 + D * (0.5 - s) ** 2 + L * (0 - s) ** 2) / N
    sem = math.sqrt(var / N) if N > 0 else 0.0
    return s, sem, N


def elo(s):
    s = min(max(s, 1e-9), 1 - 1e-9)
    return -400.0 * math.log10(1.0 / s - 1.0)


def llr_trinomial(W, D, L, elo0, elo1):
    """Classic trinomial SPRT log-likelihood ratio (draw ratio from the sample)."""
    N = W + D + L
    if N == 0:
        return 0.0
    d = D / N
    def probs(elo_diff):
        s = 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))
        pw, pl, pd = s - d / 2.0, 1.0 - s - d / 2.0, d
        eps = 1e-9
        pw, pl, pd = max(pw, eps), max(pl, eps), max(pd, eps)
        z = pw + pd + pl
        return pw / z, pd / z, pl / z
    pw0, pd0, pl0 = probs(elo0)
    pw1, pd1, pl1 = probs(elo1)
    return (W * math.log(pw1 / pw0) + D * math.log(pd1 / pd0) + L * math.log(pl1 / pl0))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--wdl", nargs=3, type=int, required=True, metavar=("W", "D", "L"))
    p.add_argument("--elo0", type=float, default=None, help="H0 elo bound (enables SPRT)")
    p.add_argument("--elo1", type=float, default=None, help="H1 elo bound")
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--beta", type=float, default=0.05)
    a = p.parse_args()
    W, D, L = a.wdl
    s, sem, N = score_and_ci(W, D, L)
    lo, hi = max(s - 1.96 * sem, 1e-9), min(s + 1.96 * sem, 1 - 1e-9)
    print(f"games={N}  W={W} D={D} L={L}")
    print(f"score={s:.4f}  95%CI=[{lo:.4f}, {hi:.4f}]")
    print(f"elo={elo(s):+.1f}  95%CI=[{elo(lo):+.1f}, {elo(hi):+.1f}]")
    if a.elo0 is not None and a.elo1 is not None:
        llr = llr_trinomial(W, D, L, a.elo0, a.elo1)
        lower = math.log(a.beta / (1 - a.alpha))
        upper = math.log((1 - a.beta) / a.alpha)
        if llr >= upper:
            decision = f"ACCEPT H1 (elo >= {a.elo1})"
        elif llr <= lower:
            decision = f"ACCEPT H0 (elo <= {a.elo0})"
        else:
            decision = "CONTINUE (not yet significant)"
        print(f"SPRT[{a.elo0},{a.elo1}] a={a.alpha} b={a.beta}: "
              f"LLR={llr:.3f}  bounds=[{lower:.3f}, {upper:.3f}]  → {decision}")


if __name__ == "__main__":
    main()
