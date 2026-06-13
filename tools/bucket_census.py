#!/usr/bin/env python3
"""Build a collision-FREE dense remap of the pattern table (prune the phantom buckets).

Background (job 0210/0211 era): the 17,006,112-bucket table (32 patterns x 3^12) is
mostly phantom — realistic self-play only ever touches an *occurring* set of ~1M
buckets (cf tools/bucket_coverage.py). The other ~16M are pinned at 0 by lack of data
and contribute nothing. Pruning them is a pure efficiency win: the training design
matrix shrinks ~17x (34M -> ~2M columns) and the .pjtw shrinks 136MB -> ~16MB, WITHOUT
changing the eval, because we remap collision-FREELY (every kept bucket gets its own
dense slot). This is NOT the lossy bucket-hashing of job 0190 (which collided rare
configs onto common ones and broke depth stability) — there are no collisions here.

Output: a dense remap  bucket_index(0..17M-1) -> slot, where
    slot 0          = shared FALLBACK (buckets never seen at census time)
    slot 1..K       = one per kept (occurring) bucket, ordered by frequency desc
K = number of kept buckets (the dense table size). Train/eval apply the remap to the
pattern columns; new buckets that appear later (eval drift) hit slot 0 until re-census.

This tool also measures, on a HELD-OUT slice, the fallback rate = fraction of
activations that land on slot 0 (unseen) — the concrete cost of freezing the map.

Usage:
  python3 tools/bucket_census.py <selfplay.jnnw|glob> [more...] \
      [--min-visits 1] [--holdout-frac 0.1] [--out remap.npz]
"""
import numpy as np, struct, glob, sys, argparse
sys.path.insert(0, 'pattern_jass/tools')
import patterns as P

REC = 38
TB = P.TOTAL_BUCKETS


def load_cols(paths):
    """Return (D,32) bucket-column indices for every position in the inputs."""
    chunks = []
    for pat in paths:
        for f in sorted(glob.glob(pat)):
            b = open(f, 'rb').read()
            if b[:4] != b'JNNW':
                continue
            n = (len(b) - 8) // REC          # from size: header may be 0 mid-run
            if n == 0:
                continue
            a = np.frombuffer(b[8:8 + n * REC], dtype=np.uint8).reshape(n, REC)
            bb = a[:, 0:32].copy().view('<u8').reshape(n, 4)
            chunks.append(P.flat_feature_columns(
                P.extract_indices(bb[:, 2], bb[:, 0])))   # (n,32)
    if not chunks:
        sys.exit("no JNNW records found")
    return np.concatenate(chunks, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--min-visits", type=int, default=1,
                    help="keep a bucket only if it occurs >= this many times in the census")
    ap.add_argument("--holdout-frac", type=float, default=0.1,
                    help="fraction of positions held out to measure the fallback rate")
    ap.add_argument("--out", default="",
                    help="optional .npz to save the remap (int32[TB]) + metadata")
    a = ap.parse_args()

    cols = load_cols(a.inputs)
    D = len(cols)
    rng = np.random.default_rng(0)
    perm = rng.permutation(D)
    n_hold = int(D * a.holdout_frac)
    hold_idx, train_idx = perm[:n_hold], perm[n_hold:]

    # census on the TRAIN slice only (so the held-out fallback rate is honest)
    train_flat = cols[train_idx].ravel()
    counts = np.bincount(train_flat, minlength=TB)
    keep_mask = counts >= a.min_visits
    K = int(keep_mask.sum())
    kept_idx = np.flatnonzero(keep_mask)
    # order kept buckets by frequency desc -> common buckets get the low slot ids
    order = kept_idx[np.argsort(counts[kept_idx])[::-1]]

    remap = np.zeros(TB, dtype=np.int32)     # 0 = fallback
    remap[order] = np.arange(1, K + 1, dtype=np.int32)

    census_pos = len(train_idx)
    print(f"census positions = {census_pos:,}  (held out {n_hold:,} for fallback test)")
    print(f"TOTAL_BUCKETS = {TB:,}")
    print(f"kept (>= {a.min_visits} visits) = {K:,}  "
          f"-> dense table {100*K/TB:.3f}% of 17M  (~{TB/max(K,1):.1f}x smaller)")
    print(f".pjtw size  : {TB*2*4/1e6:.0f}MB -> {(K+1)*2*4/1e6:.1f}MB")
    print(f"train design columns : {2*TB:,} -> {2*(K+1):,}")

    # fallback rate on the HELD-OUT slice (drift cost if the map is frozen)
    if n_hold:
        hold_flat = cols[hold_idx].ravel()
        fb = float((remap[hold_flat] == 0).mean())
        # how many distinct held-out buckets are unseen
        hb = np.unique(hold_flat)
        hb_unseen = int((remap[hb] == 0).sum())
        print(f"held-out fallback rate = {100*fb:.3f}% of activations land on slot 0 "
              f"(unseen) ; {hb_unseen:,}/{len(hb):,} distinct held-out buckets unseen")
        print("  -> this is the cost of a FROZEN map; shrinks as census grows / re-census.")

    if a.out:
        np.savez_compressed(a.out, remap=remap, K=K, total_buckets=TB,
                            min_visits=a.min_visits, census_positions=census_pos)
        print(f"saved remap -> {a.out}  (apply: dense_cols = remap[cols])")

    # integration notes (printed so they live with the numbers)
    print("\nintegration (gated on the 0210/0211 volume verdict):")
    print("  * Python train.py: dense_cols = remap[cols]; build_sparse_X over K+1 columns.")
    print("  * C++ scan_eval.cpp: load remap; in evaluate(), slot = remap[offset + idx%HASH];")
    print("    pat_mg/pat_eg indexed by slot. Store remap compactly (per-pattern sorted")
    print("    occurring-index list + binary search ~4MB, or an MPHF ~0.5MB) to keep RAM low.")
    print("  * re-census every few generations (or size K with headroom) to absorb eval drift.")


if __name__ == "__main__":
    main()
