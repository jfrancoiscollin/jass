# L3 CLS-D search-profile diagnostic V1

Date: 2026-09-16. Status: **prospectively frozen before reading detailed search-profile payloads from the completed mirror production**.

## Purpose

The merged CLS master plan requires a search-profile diagnostic after depth/growth and mirror-scale. This stage localizes runtime/search pressure without changing evaluator bytes or launching a new scientific search. It reuses the exact authenticated FULL-512 depth/growth production and the exact authenticated mirror-scale production.

This diagnostic is `DIAGNOSTIC_ONLY`. It cannot select, fit, tune, promote, bake, consume confirmation targets, spend alpha, or authorize CLS generation 1.

## Frozen sources

- FULL-512 depth/growth source: `cpx62-2000-l3-cls-depth-growth-full-production-v2`, attempt `20260916T083204Z-7a5f44ec`, Jass `7a5f44ec1681c2471b1815f8767b4008b11e3a54`, Launch-V2 receipt SHA256 `3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42`.
- Mirror-scale source: `cpx62-2008-l3-cls-mirror-scale-production-v3`, attempt `20260916T161938Z-92984c1f`, Jass `92984c1f8ac9563225f930c1c3d77b80e581e05d`, Launch-V2 receipt SHA256 `2ac13b1e61dffc7d73217a8daba111aed9028b7a006020d081ebd6aa3480b004`.
- Frozen DEEP512 cohort SHA256 `478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e`, 512 roots / 128 per phase, exact source order.
- CURRICULUM SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.
- Shallow exact-node budgets `{5k, 50k, 200k}` from source 2000 and the same-current-Jass exact-node `1M` mirror reference from source 2008.
- Bootstrap: paired phase-stratified root bootstrap, 100,000 replicates, seed `2026091004`.

No new Jass or Scan search is authorized by this stage.

## Frozen readout

For JASS_PARITY at each shallow budget publish:

- mean/median NPS and completed nominal depth;
- qnodes / observed-node ratio;
- eval-calls / observed-node ratio;
- mean per-root TT hit rate;
- cutoffs / observed-node ratio;
- first-move cutoffs / total cutoffs;
- PVS researches / moves searched;
- moves searched / observed node;
- total wall time.

For pinned Scan at each shallow budget publish the available comparable observables: NPS, completed nominal depth and wall time. Scan-internal qnodes/eval/TT/cutoff fields remain unavailable rather than being imputed.

For JASS_PROFILE publish instrumentation overhead as PROFILE/PARITY wall-time ratio while requiring the already-authenticated semantic identity from source 2000.

For the Jass1M source publish the same available Jass search counters and completed-depth/NPS descriptives.

Phase-localized summaries use P0-P3 from the authenticated 2000 rows. The paired bootstrap reports uncertainty for Jass-vs-Scan log-NPS ratio, completed-depth delta, and the frozen Jass internal search-profile ratios at each shallow budget.

## Nodes-to-depth boundary

True same-search nodes-to-depth snapshots are still unavailable. This diagnostic therefore publishes only the observed fixed-node completed-depth frontier at 5k/50k/200k/1M. It must publish:

`nodes_to_depth_available=false`

Fresh depth-N searches, interpolated pseudo-snapshots, or any replacement search are forbidden. This keeps the earlier CLS-D no-surrogate rule intact.

## Interpretation

The output is descriptive evidence for the later terminal bottleneck classification. It does **not** independently classify SEARCH, DECISION-EVAL, COST or mixed. Search-profile evidence is interpreted jointly with depth/growth, mirror-scale and the later draw/pentanomial-throughput diagnostic.

## Launch contract

One Launch-V2 common profile covers rehearsal and production. Rehearsal and production execute the same read-only source-authentication and aggregation logic. Production may be queued only after an authenticated green rehearsal receipt and differs only by `LAUNCH_MODE`.

Technical failures are repaired mechanically under a new immutable job ID; the frozen source identities, metrics, bootstrap seed and zero-side-effect boundary are not changed after readout.

## Required outputs

- `search-profile.json`
- `bootstrap.json`
- `source-authentication.json`
- `manifest.json`
- `RESULTS.md`
- `scientific-summary.json`

Rehearsal terminal: `CLS_SEARCH_PROFILE_REHEARSAL_READY_V1`.
Production terminal: `CLS_SEARCH_PROFILE_DIAGNOSTIC_COMPLETE_V1`.
Technical terminal: `CLS_SEARCH_PROFILE_TECHNICAL_FAILURE_V1`.

## Quarantine

```text
DIAGNOSTIC_ONLY=true
target_reads=0
candidate_reads=0
control_evaluations=0
new_jass_searches=0
new_scan_searches=0
fits=0
strength_games=0
selfplay_games=0
alpha_spent=0
promotions=0
bakes=0
```

Completion authorizes only continuation to the draw/pentanomial-throughput CLS-D diagnostic.