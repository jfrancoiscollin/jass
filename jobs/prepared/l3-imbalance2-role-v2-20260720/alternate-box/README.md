# Alternate box — L3-IMBALANCE2 analysis jobs

Use this directory when **ccx33** is available before cpx62 for an analysis job
whose top-level prepared wrapper targets cpx62.

## Difficulty reference

```text
ccx33-l3-imbalance2-a64-b64-difficulty-reference.sh
```

This wrapper has the same scientific contract as the top-level cpx62 reference:

- identical immutable V2 P1 prefix and expected job identity;
- identical A64/B64 bytes, plateau seed `161803` and 64 positions per stratum;
- exact EGDB WDL for `1v3` and `2v4`;
- Scan d10 empirical reference for `3v5` through `18v20`;
- depth 10, 400-ply cap, eight shards and eight parallel workers;
- no training, weighting, promotion or automatic continuation.

## P2 consolidation

```text
ccx33-l3-imbalance2-p2-consolidate.sh
```

This wrapper is byte-for-byte equivalent in scientific parameters to the
cpx62 P2 consolidation wrapper. It reuses existing P1/P2 reports and therefore
replays **zero games**. It applies the same symmetric-exclusion cap, 10 000
bootstrap replicates, material-stratified G4→G8 comparison and P3 prohibition.

Run **one** wrapper for each initial analysis, depending on box availability.
Running both is only useful as an explicit hardware-replication check; outputs
must not be pooled as additional independent positions because both consume the
same A64/B64 corpus.
