# L3 D4c rank-breaker micro V1 — preregistration

Date: 2026-09-08.

## Motivation fixed before D4c execution

D4b job `cpx62-1868-l3-d4b-search-utility-micro-screen-v1`, attempt `20260907T210728Z-34f48241`, code `34f48241a9e99338c31e02c6561a410de7d56745`, terminated `D4B_MICRO_GATE0_NOT_SUPPORTED_V1`.

The frozen observations used only to motivate this new hypothesis are:

- D4b offline was supported: TEST CE gain `+0.03890052053679449`, bootstrap 95% `[0.021751315401445804, 0.05629130125906997]`, top-1 `0.725 -> 0.726`;
- runtime activation was tiny: `216779` eligible internal nodes but only `71` stable hoists;
- Gate0 decisions were therefore identical to CONTROL on all 512 parents and regret improvement was exactly zero;
- median wall ratio was `1.0728213964126572`.

This is interpreted as an objective/runtime mismatch: multiclass cross-entropy plus the hard-coded baseline logit `-(legacy_rank-1)` can improve probability calibration without learning enough rank reversals to affect move ordering.

D4c is a new exploratory hypothesis, not a retune or continuation of D4/D4b.

## Frozen D4c hypothesis

Learn directly which candidate should outrank the others using pairwise ranking, while keeping the same cheap feature vocabulary and model size.

For every selected teacher event with label `y` and candidates `j != y`, fit one shared phase-blocked linear scorer by minimizing:

`softplus(-(score(y)-score(j)))`

across all label-versus-other pairs, plus L2 `1e-3`.

Runtime score is **only** `beta dot features`. There is no fixed `-(legacy_rank-1)` term. The existing `legacy_rank_norm` feature remains feature 0, so the fit is free to learn whatever legacy-rank prior the data support instead of inheriting a fixed one-unit gap.

Frozen model:

- same 24 D4 features;
- 4 phase blocks;
- 96 float64 coefficients total;
- one L-BFGS-B fit only;
- initialization all zeros;
- `max_iter=500`, `maxcor=10`, `gtol=1e-6`;
- no feature search, hyperparameter search, temperature search, runtime scale search, model selection or calibration.

## Frozen data and teacher

Reuse the already target-blind D4b 512-root identity manifest from 1868. This is exploratory reuse and cannot count as fresh confirmation.

- roots: 512 = train 384 / valid 64 / test 64;
- WDL_CONTROL bytes unchanged, SHA256 `e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`;
- regenerate teacher labels from scratch at exact 20,000 Jass nodes/root, threads=1, book off;
- 8 shards of 64 roots, max teacher compute 10.24M nodes;
- deterministic D4b example selection reused: train 8000 / valid 1000 / test 1000;
- canonical cross-split leakage removal unchanged;
- phase composition is diagnostic only, never a support gate.

## Offline metrics and gate

Baseline is legacy rank-1 prediction (`predicted_index=0`). D4c publishes, on VALID and TEST:

- overall top-1;
- label-vs-other pairwise accuracy;
- predicted-rank distribution;
- fraction of examples whose predicted top rank is not legacy rank 1 (`change_rate`);
- non-first label support and correct non-first override rate;
- false override rate on rank-1 labels;
- paired TEST top-1 delta bootstrap, 20,000 repetitions, seed `2026090803`.

`D4C_RANK_BREAKER_OFFLINE_SUPPORTED_V1` iff all are true:

1. VALID top-1 > VALID legacy baseline top-1;
2. TEST top-1 > TEST legacy baseline top-1;
3. TEST paired top-1 gain mean > 0;
4. TEST `change_rate >= 0.01` and `change_rate <= 0.35`;
5. among TEST events whose true label is non-first, D4c selects the true non-first label in at least `0.05` of cases;
6. provenance/integrity passes.

The bootstrap lower bound is reported but is not an exploratory offline gate. Gate0 remains the causal screen.

If offline is not supported, stop with zero Gate0 candidate searches.

## Runtime intervention

At eligible internal nodes only, D4c:

1. computes normal historical Jass ordering first;
2. leaves a legal TT move absolute;
3. takes the first up-to-four legacy non-TT siblings;
4. computes the exact same 24 features as the teacher;
5. scores them with `beta dot features`;
6. stable-hoists the highest-scoring candidate to the first non-TT slot;
7. preserves relative order of every other move;
8. leaves root ordering unchanged.

Eligibility remains: internal ply >=1, 9..40 pieces, depth >=3, legal move count 2..16.

Runtime diagnostics must publish eligible nodes, total hoists, and predicted-rank counts 1..4.

## Conditional Scan Gate0

Only after offline support:

- reuse the exact frozen Gate0 512 parent IDs and CONTROL from 1864;
- reuse existing Scan200k sibling oracle scores from 1657;
- exact 20k Jass nodes/parent, threads=1, book off, external EGDB off;
- candidate only, max another 10.24M Jass nodes;
- zero new Scan searches;
- permanent Gate0 rules unchanged: mean Scan regret improvement >0, bootstrap 95% LCB >0, top-hit non-worse, median wall ratio <=1.05, integrity pass.

A Gate0 pass is **survivor only**. It requires a fresh target-blind disjoint confirmation cohort before any strength games.

## Permanent guards

```text
strength_games=0
selfplay_games=0
new_scan_searches=0
fits<=1
promotions=0
bakes=0
strength_authorized=false
```

No Elo, no equal-node match, no promotion and no automatic runtime adoption are authorized by this experiment.
