#!/usr/bin/env python3
"""How much self-play data to densely fill the pattern table?

Reverse-engineers, from a self-play JNNW sample, the bucket-frequency structure of
the 17,006,112-bucket pattern table (32 patterns x 3^12). Reports: distinct coverage,
Chao1 estimate of the *occurring* bucket set (the 17M is mostly phantom — most ternary
configs never occur), Good-Turing mass coverage, the species-accumulation curve, and
the data needed for >=N visits on >=95% of occurring buckets (Poisson scaling).

Used to establish (job 0210/0211 era) that the effective table is ~1M buckets, that
95% coverage needs ~3M positions, and dense (>=8) needs ~10-20M — i.e. the flat WDL
loop (0205b) is data-starved, curable with realistic volume, not a model-class change.

Usage:  python3 tools/bucket_coverage.py <file_or_glob.jnnw> [more.jnnw ...]
        (reads record count from file SIZE, so mid-run shards with a 0 header work)
"""
import numpy as np, struct, glob, sys, math
sys.path.insert(0, 'pattern_jass/tools')
import patterns as P

REC = 38
TB = P.TOTAL_BUCKETS


def load(paths):
    bbs = []
    for pat in paths:
        for f in sorted(glob.glob(pat)):
            b = open(f, 'rb').read()
            if b[:4] != b'JNNW':
                continue
            n = (len(b) - 8) // REC          # from size: header count may be 0 mid-run
            if n == 0:
                continue
            a = np.frombuffer(b[8:8 + n * REC], dtype=np.uint8).reshape(n, REC)
            bbs.append(a[:, 0:32].copy().view('<u8').reshape(n, 4))
    if not bbs:
        sys.exit("no JNNW records found")
    return np.concatenate(bbs, 0)


def main():
    argv = sys.argv[1:]
    king = '--king' in argv                      # king-aware occupancy (men|kings)
    paths = [a for a in argv if a != '--king']
    if not paths:
        sys.exit(__doc__)
    bb = load(paths)
    D = len(bb)
    if king:
        # cols: 0=white_men 1=white_kings 2=black_men 3=black_kings (piece-presence)
        idx = P.extract_indices(bb[:, 2] | bb[:, 3], bb[:, 0] | bb[:, 1])
        print("MODE: KING-AWARE (occupancy = men|kings, Scan-style)")
    else:
        idx = P.extract_indices(bb[:, 2], bb[:, 0])
        print("MODE: men-only")
    cols = P.flat_feature_columns(idx)   # (D,32)
    flat = cols.ravel()
    print(f"positions D = {D:,}   activations = {flat.size:,} (= D x {P.NUM_PATTERNS})")

    counts = np.bincount(flat, minlength=TB)
    S_obs = int((counts > 0).sum())
    f1 = int((counts == 1).sum()); f2 = int((counts == 2).sum())
    print(f"TOTAL_BUCKETS = {TB:,}")
    print(f"distinct touched S_obs = {S_obs:,}  ({100*S_obs/TB:.3f}% of {TB/1e6:.1f}M)")
    print(f"singletons f1={f1:,}  doubletons f2={f2:,}")

    chao1 = S_obs + (f1 * (f1 - 1)) / (2 * (f2 + 1))
    print(f"Chao1 occurring-richness R_hat = {chao1:,.0f}  "
          f"(observed = {100*S_obs/chao1:.1f}% of it; rises with sample => lower bound)")
    print(f"Good-Turing mass coverage = {100*(1 - f1/flat.size):.4f}%")

    print("\nspecies accumulation (distinct vs positions):")
    rng = np.random.default_rng(0); perm = rng.permutation(D)
    ks, ds = [], []
    for frac in (0.01, 0.03, 0.1, 0.3, 0.6, 1.0):
        k = max(1, int(D * frac))
        d = int((np.bincount(cols[perm[:k]].ravel(), minlength=TB) > 0).sum())
        ks.append(k); ds.append(d)
        print(f"  {k:>10,} pos -> {d:>10,} distinct ({100*d/TB:.3f}% of {TB/1e6:.1f}M)")

    ks, ds = np.array(ks[1:], float), np.array(ds[1:], float)
    y = np.log(np.clip(1 - ds / chao1, 1e-9, 1))
    slope = np.polyfit(ks, y, 1)[0]
    tau = -1 / slope if slope < 0 else float('inf')
    k95 = -tau * math.log(0.05) if np.isfinite(tau) else float('inf')
    print(f"\ncoverage model distinct(k)=R(1-e^-k/tau): tau~{tau:,.0f}")
    print(f"  -> observe 95% of occurring set at ~{k95:,.0f} positions")
    print("  -> for >=N visits on 95%, scale that anchor by ~N "
          "(skew makes it the upper end of [N*D/27k , N*k95]):")
    for N in (1, 8, 30, 50):
        print(f"       N>={N:<3}: ~{N*k95:,.0f} positions")


if __name__ == "__main__":
    main()
