# L3 CLS-D draw / pentanomial / throughput diagnostic V1

Date: 2026-09-16. Status: **prospectively frozen before reading the detailed native paired-game payloads**.

## Purpose

The merged CLS master plan requires one final read-only diagnostic before the terminal bottleneck classification: draw rate, pentanomial outcome distribution and CPX62 paired-game throughput. This stage reuses already-completed paired colour-reversed force gates. It launches **no new game, engine search, fit or confirmation read**.

The historical gates are calibration evidence for the future CLS strength-at-time harness only. Their candidate-strength verdict is irrelevant here and must not be imported into CLS. The only consumed observables are native fixed-time W/D/L, paired-opening score distribution, error-free pairing contract and search telemetry/parallelism.

## Frozen historical sources

Primary fixed-time view only (`movetime=0.1s` per move, one colour-reversed pair per opening):

- pool 1: `cpx62-1568-l3-tb-policy-move-ordering-force-pool1-v1`, attempt `20260825T234756Z-146f3464`, Jass code `146f34647dae489c6d2817748fd767aa65b93d87`, `artefacts/force/force-native.json`, frozen size 36,739 bytes, source bootstrap seed `2026083011`;
- pool 2: `cpx62-1569-l3-tb-policy-move-ordering-force-pool2-v1`, attempt `20260826T061618Z-146f3464`, same Jass code, `artefacts/force/force-native.json`, frozen size 36,775 bytes, source bootstrap seed `2026083021`.

Both sources used byte-identical `CURRICULUM` SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`. The historical policy SHA is `f894bb12778c59d85e666163508c2ef51ad080c9eb37667719c2926f2404d3c4`. Each native pool has exactly 3,000 openings / 6,000 games, 8 shards, max parallelism 8, max 160 plies, game timeout 180s and zero technical error draws. The two historical stages together contain 24,000 strength games because each also ran a depth-9 q00 diagnostic; **only the 12,000 native fixed-time games / 6,000 paired openings are consumed here**.

Historical source games are not new CLS strength games. This stage records `strength_games=0` and `historical_native_games_consumed=12000` separately.

## Frozen readout

For each pool and for the equal-weight pooled native view publish:

- raw game W/D/L and draw rate;
- paired-opening score counts on the pentanomial support `{0, 0.5, 1, 1.5, 2}` points per two-game pair;
- normalized pair-score variance and pair-points variance;
- aggregate engine-search wall seconds from both arms;
- serial engine-search seconds per pair;
- CPX62 8-way search-capacity estimate in pairs/hour using the source telemetry and source max parallelism.

The pooled score-rate uncertainty uses a pool-stratified paired-opening bootstrap with 100,000 replicates and seed `2026091005`, preserving 3,000 openings from each historical pool per replicate.

A separate conservative context may report the two historical full-stage wall times (5,364s and 5,588s). Those full-stage durations include authentication, build, runtime profiling, native games, q00 games and readout, so they are not the primary native throughput estimator.

## Authenticated technical correction after 2011

Rehearsal `cpx62-2011-l3-cls-draw-pentanomial-throughput-rehearsal-v1` failed **TECHNICALLY** before producing a diagnostic verdict. Exact source-code inspection of the frozen producer `jobs/tools/run_jass_gate_bounded.py` at Jass `146f34647dae489c6d2817748fd767aa65b93d87` established that the invocation did use the frozen `max_plies=160`, `game_timeout=180`, CURRICULUM pattern and 8-way parallelism, but the historical `force-native.json` schema did **not** serialize `max_plies`, `game_timeout`, pattern SHA fields or engine-search wall telemetry.

This is a source-schema capability fact, not a scientific result and not permission to change the source population, time control, pair cardinality, bootstrap seed or any gate. The repair therefore:

- authenticates only fields that the frozen producer actually serialized, while keeping exact job/attempt/code, exact artifact sizes, scientific-summary CURRICULUM/policy identity and paired-opening cardinality fail-closed;
- continues to publish the frozen W/D/L, draw rate, pentanomial counts, pair variance and bootstrap exactly as preregistered;
- reports the primary native search-wall throughput as **unavailable**, rather than reconstructing, imputing or inventing telemetry that was never persisted;
- may publish the already-frozen combined historical full-stage wall-time context as explicitly non-primary context only;
- sets future SPRT sizing readiness to false until a future prospective harness records the required native search-wall telemetry.

The original three throughput bullets above are therefore unobservable from these immutable historical artifacts. They are retained as the preregistered intent; this correction records the fail-closed outcome after the technical source-schema defect was proven.

## Pentanomial boundary

The stage may report whether the existing harness provides valid pentanomial inputs for future CLS strength sizing. It **does not** freeze an SPRT H0/H1 boundary, alpha, beta, game count or continuation threshold. Those values belong to the later prospective CLS strength-at-time contract and must be frozen before that future experiment.

## Interpretation boundary

This is the last descriptive CLS-D evidence stage. It does **not** itself publish the final `SEARCH / DECISION-EVAL / COST / mixed` bottleneck classification. Production completion authorizes only the terminal joint classification over depth/growth, mirror-scale, search-profile and this draw/pentanomial/throughput evidence.

Historical candidate identity, historical force verdict and historical promotion decision are quarantined from the CLS classification.

## Launch contract

One Launch-V2 common profile covers rehearsal and production. Rehearsal and production execute identical read-only source authentication and aggregation. Production may be queued only after an authenticated green rehearsal receipt and may differ only by `LAUNCH_MODE=production`.

Technical failures are repaired mechanically under a new immutable job ID. Frozen source identities, fixed-time view, pair cardinality, bootstrap seed and zero-side-effect boundary must not be adapted around a result.

## Required outputs

- `draw-pentanomial-throughput.json`
- `bootstrap.json`
- `source-authentication.json`
- `manifest.json`
- `RESULTS.md`
- `scientific-summary.json`

Rehearsal terminal: `CLS_DRAW_PENTANOMIAL_THROUGHPUT_REHEARSAL_READY_V1`.
Production terminal: `CLS_DRAW_PENTANOMIAL_THROUGHPUT_DIAGNOSTIC_COMPLETE_V1`.
Technical terminal: `CLS_DRAW_PENTANOMIAL_THROUGHPUT_TECHNICAL_FAILURE_V1`.

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

Completion authorizes only the terminal CLS-D bottleneck classification. It does not authorize CLS generation 1, promotion, bake or scale-up.
