#!/usr/bin/env python3
"""Deterministic, low-variance strength proxy for an eval.

Game win-rates have binomial noise (std ~ sqrt(p(1-p)/N)); at the few-dozen-game
budget we can afford, that noise swamps the small differences between successive
self-play generations (cf. jobs 0203/0204). This proxy replaces noisy game play
with a DETERMINISTIC agreement metric on a FIXED test set: how well the eval's
static scores agree with a strong reference's scores.

It is NOT a substitute for game Elo (an eval can agree on quiet positions yet
blunder tactically) — it is the cheap, high-resolution metric for tracking a
LEARNING CURVE. Confirm milestones with game matches + SPRT/Elo (tools/sprt_elo.py).

Pipeline:
  1. `jass --rewrite-scores-with-nnue <testset> <tmp> --nnue <eval>` → the eval's
     STATIC score on every test position (pattern .pjtw or NNUE .bin).
  2. Read the reference scores (the test set's own `score` field) and the eval's
     scores; both are STM-POV centipawns (cf. master_loader).
  3. Report Spearman & Pearson correlation and sign-agreement, optionally after
     dropping near-decided positions (|ref| > clip) the way training does.

Usage:
  python3 tools/eval_proxy.py --jass build/jass --eval cand.pjtw \
      --testset master-clean-scan-d10.jnnw [--max 20000] [--offset 0] \
      [--score-drop 4900]
"""
import argparse, struct, subprocess, sys, tempfile, os
import numpy as np
from scipy.stats import spearmanr

REC = 38  # JNNW record: 32B bitboards + 1B stm + 4B int32 score + 1B int8 wdl


def read_scores(path, offset, maxn):
    raw = open(path, "rb").read()
    assert raw[:4] == b"JNNW", f"{path} not JNNW"
    n = struct.unpack("<I", raw[4:8])[0]
    a = np.frombuffer(raw[8:8 + n * REC], dtype=np.uint8).reshape(n, REC)
    sc = a[:, 33:37].copy().view("<i4").ravel().astype(np.float64)
    if offset:
        sc = sc[offset:]
    if maxn:
        sc = sc[:maxn]
    return sc


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--jass", required=True)
    p.add_argument("--eval", required=True, help="eval to score (.pjtw or .bin)")
    p.add_argument("--testset", required=True, help="fixed JNNW set with reference scores")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--max", type=int, default=0, help="0 = all")
    p.add_argument("--score-drop", type=float, default=4900,
                   help="drop positions with |ref| > this (won/lost sentinels); 0=keep all")
    args = p.parse_args()

    ref = read_scores(args.testset, args.offset, args.max)
    with tempfile.TemporaryDirectory() as td:
        scored = os.path.join(td, "scored.jnnw")
        # rewrite-scores-with-nnue processes the WHOLE file; subset after.
        r = subprocess.run([args.jass, "--rewrite-scores-with-nnue",
                            args.testset, scored, "--nnue", args.eval],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"rewrite failed: {r.stderr.strip() or r.stdout.strip()}")
        cand = read_scores(scored, args.offset, args.max)

    assert len(ref) == len(cand), f"length mismatch {len(ref)} vs {len(cand)}"
    keep = np.ones(len(ref), bool)
    if args.score_drop and args.score_drop > 0:
        keep = np.abs(ref) <= args.score_drop
    ref, cand = ref[keep], cand[keep]

    rho, _ = spearmanr(cand, ref)
    pear = np.corrcoef(cand, ref)[0, 1] if cand.std() > 0 else float("nan")
    # sign-agreement on non-near-zero refs (the meaningful decisions)
    mask = np.abs(ref) > 20
    sign = float(np.mean(np.sign(cand[mask]) == np.sign(ref[mask]))) if mask.any() else float("nan")

    print(f"eval={args.eval}")
    print(f"  n={len(ref)} (kept of test set; score-drop={int(args.score_drop)})")
    print(f"  spearman={rho:.4f}  pearson={pear:.4f}  sign_agreement={sign:.4f}")
    # one-line machine-readable
    print(f"PROXY spearman={rho:.4f} pearson={pear:.4f} sign={sign:.4f} n={len(ref)}")


if __name__ == "__main__":
    main()
