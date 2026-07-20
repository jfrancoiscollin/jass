# Alternate box — L3-IMBALANCE2 difficulty reference

Use this directory when **ccx33** is available before cpx62 for the A64/B64 material-difficulty reference.

The wrapper:

```text
ccx33-l3-imbalance2-a64-b64-difficulty-reference.sh
```

has the same scientific contract as the top-level cpx62 wrapper:

- identical immutable V2 P1 prefix and expected job identity;
- identical A64/B64 bytes, plateau seed `161803` and 64 positions per stratum;
- exact EGDB WDL for `1v3` and `2v4`;
- Scan d10 empirical reference for `3v5` through `18v20`;
- depth 10, 400-ply cap, eight shards and eight parallel workers;
- no training, weighting, promotion or automatic continuation.

Run **one** of the ccx33 or cpx62 wrappers for the initial reference, depending on box availability. Running both is only useful as an explicit hardware-replication check; their outputs must not be pooled as additional independent positions because both consume the same A64/B64 corpus.
