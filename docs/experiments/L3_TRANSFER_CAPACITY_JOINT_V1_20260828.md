# L3 — Transfer optimization, capacity and joint T+D v1

> Date: 28 août 2026
> Statut: preregistration avant tout nouveau screen/fit/holdout de cette campagne.
> Champion inchangé: `CURRICULUM`.

## 0. Motivation

La chaîne micro-search a établi que le teacher court produit beaucoup plus d'information décisionnelle que le scalar PatternEval, mais que la première distillation en absorbe presque rien.

Upstream immuable:

- `CURRICULUM` raw SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`;
- M1 `cpx62-1591-l3-micro-search-budget-curve-m1-v1`: `B*=1000`;
- M2 final `cpx62-1598-l3-micro-search-m2-teacher-readout-v5`: `MICRO_SEARCH_TEACHER_SIGNAL_ESTABLISHED`;
- M3 final design `cpx62-1607-l3-micro-search-m3-teacher-design-v6`: 100000 parents, 928639 siblings, 828639 top-vs-rest constraints, production PatternEval design exact;
- M4 `cpx62-1608-l3-micro-search-m4-pattern-distill-v1`: T1 frozen SHA256 `25aa82567f38b9e2ad5d792d478c9e98c09d4bff9beabaa367038f55a4a98306`;
- M5 `cpx62-1610-l3-micro-search-m5-deep-transfer-v1`: global pairwise T0 `0.60020599797`, T1 `0.60250151200`, delta `+0.00229551403`, but top-hit and P0 gates fail; verdict `MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED`;
- post-M5 diagnostic `cpx62-1612-l3-post-m5-transfer-diagnostic-v2`, attempt `20260828T082356Z-781a58fa`: on the exact M5 q200 cohort, T0 `0.60020599797`, D1 `0.73234193647`, micro1000 `0.93759456424`, T1 `0.60250151200`. Therefore `R_D≈0.01737` and `R_1000≈0.00680`.

Scientific conclusion motivating this preregistration:

```text
teacher information exists strongly;
first PatternEval transfer is real but absorbs ~0.7% of available micro1000 headroom.
```

The next task is to separate three hypotheses:

1. the M4 transfer recipe is poor;
2. production PatternEval representation/quantization/anchor cannot absorb the signal;
3. a joint static representation `T + D` can retain signal that cannot be compressed into PatternEval alone.

## 1. Non-negotiable anti-leakage rule

**M5 and job 1612 are forbidden as model-selection or hyperparameter-selection data.**

Their already observed headline metrics motivated this new experiment, but no M5/1612 labels, rows, parent identities, q200 scores, q1000 scores, D1 scores, per-phase metrics or disagreement rows may enter any fit, arm ranking or threshold adaptation in Stages A-C below.

All recipe selection in this campaign must use only the frozen M3 source and a newly frozen parent-cluster split defined here before the new screen runs.

A later fresh deep confirmation, if authorized by the screen, must use a completely new cohort disjoint from M1/M2/M3/M5 and all established force pools.

## 2. Frozen M3 development split

Source: exact immutable M3 artifacts from the final successful M3 teacher/design chain (`1599` selection + `1607` teacher/design), including the production-exact PatternEval design and exact micro1000 teacher ordering/scores needed to reconstruct ranking constraints.

Split unit: **parent cluster**, never sibling row.

Split seed: `2026090401`.

Method: deterministic SHA256 hash of canonical parent identity prefixed by the seed. First 80% buckets = TRAIN, last 20% = DEV. All siblings of a parent stay in one side.

Requirements before any fit:

- exactly one assignment per parent;
- zero parent overlap TRAIN/DEV;
- zero canonical overlap after rotate180/colour-swap equivalence;
- same phase/colour support reported for both partitions;
- M5/1612 files not fetched/read by the screen job;
- exact CURRICULUM and D1 source SHAs authenticated.

The DEV split is reusable for this preregistered arm comparison only. It is not a future fresh confirmation.

## 3. Stage A — PatternEval transfer DOE

### 3.1 Goal

Improve teacher-to-PatternEval transfer without using new deep q200 labels.

Primary offline target is agreement with the frozen micro1000 ranking on M3 DEV.

For each candidate C publish:

- pairwise agreement `A(C,q1000)` on DEV;
- top-hit agreement on DEV;
- phase/colour breakdown;
- delta versus T0 and versus exact M4/T1-replication arm;
- quantized production `.pjtw` agreement after serialize/reload;
- anchor drift diagnostics.

Define the DEV transfer proxy:

```text
P_1000(C) = (A(C,q1000) - A(T0,q1000)) / (1 - A(T0,q1000))
```

This is a development proxy only. The scientific `R_1000` remains defined against fresh q200 in the later confirmation.

### 3.2 Mandatory replication arm

`A0_M4_REPLICATION` must reproduce the M4 recipe on TRAIN only:

- objective: unweighted top-vs-rest pairwise logistic;
- residual L2 `1e-5`;
- production full PatternEval coordinate system;
- int32 production serialization;
- current conservative anchor family corresponding to M4 RMS<=12cp and p99<=35cp;
- no D feature/signal.

If A0 cannot reproduce the expected implementation semantics, the DOE is technically invalid and stops.

### 3.3 Frozen pure-T arm family

All arms use identical TRAIN/DEV and exact production PatternEval coordinates. No arm-specific data filtering is allowed except the preregistered pair weighting below.

L2 axis for unweighted top-vs-rest:

- A0: `1e-5` (replication);
- A1: `0`;
- A2: `1e-7`;
- A3: `1e-6`;
- A4: `1e-4`.

Margin-weighted top-vs-rest arms:

- A5: L2 `1e-6`;
- A6: L2 `1e-5`.

Margin weight is frozen before data read as:

```text
w = clip(abs(q1000_top - q1000_other) / 100cp, 0.25, 4.0)
```

Weights affect loss contribution only, never acceptance, split or target ordering.

Rank-density arm:

- A7: top-vs-rest plus adjacent-rank pairs, L2 `1e-6`.

For A7, within each parent sort siblings by exact frozen q1000 score with canonical sibling identity as deterministic tie-break. Add every top-vs-rest pair plus pairs `(rank_i, rank_{i+1})`. Pair labels follow q1000 ordering. No q200 signal.

Combined weighted dense arm:

- A8: A7 pair family with the same frozen margin weighting, L2 `1e-6`.

### 3.4 Anchor sensitivity, diagnostic not adaptive

Every fitted residual direction is evaluated at three preregistered production shrink regimes using the same target-blind anchor source/selection mechanics as M4:

- G0 conservative: RMS<=12cp, p99<=35cp;
- G1 medium diagnostic: RMS<=20cp, p99<=60cp;
- G2 relaxed diagnostic: RMS<=35cp, p99<=100cp.

No threshold may be moved after seeing arm results.

G1/G2 exist to determine whether the M4 anchor is the binding bottleneck. They do not automatically authorize deployment.

For each arm/regime publish residual scale, changed int32 coefficient count, DEV pairwise/top-hit and anchor statistics.

### 3.5 Selection/readout of Stage A

This stage is a **screen**, not a final scientific confirmation.

Publish the full matrix and identify:

- best G0 pure-T arm by DEV pairwise, top-hit as secondary tie-break;
- best G1 pure-T arm;
- best G2 diagnostic arm;
- whether improvement is mainly from objective/L2 or from relaxing anchor.

No Elo/strength and no promotion.

No new fresh q200 labels are generated in Stage A.

## 4. Stage B — PatternEval capacity probes

Purpose: distinguish bad transfer recipe from representational/production constraints.

Use exactly the same M3 TRAIN/DEV split and q1000 teacher. No M5 data.

### B0 — unanchored production-linear ceiling

Fit the best-performing pure PatternEval objective family from Stage A with:

- no anchor shrink (`s=1`);
- no residual drift constraint;
- float64 optimizer weights evaluated before quantization;
- then int32 production serialization evaluated separately.

Publish:

- FLOAT pairwise/top-hit to q1000 on DEV;
- INT32 pairwise/top-hit;
- quantization loss;
- RMS/p99 drift for information only.

This answers whether anchor/quantization alone are destroying transfer within the production-linear family.

### B1 — nonlinear same-observable probe

Implement one deterministic offline-only nonlinear probe that consumes **only observables already available to production PatternEval before search**, with no D score, q1000 score, q50/q200, WDL or search result as input.

The implementation may use the exact active PatternEval pattern identities plus the existing 120 dense extras/phase/side information, but may not add new board/search observables not already encoded by the production feature extractor.

Architecture must be fixed before DEV readout; default acceptable implementation:

- embeddings for active categorical pattern coordinates;
- dense extras normalized on TRAIN only;
- small MLP head;
- pairwise logistic target q1000;
- deterministic seed `2026090402`;
- no hyperparameter search inside B1.

The exact architecture/parameter count must be written to the job receipt before DEV metrics are emitted.

B1 is offline-only. It can never be promoted directly.

Interpretation:

- B1 high, B0/T low => architecture/linear/quantization bottleneck;
- B1 also low => existing production observables likely miss information.

## 5. Stage C — joint T+D capacity branch

This stage asks whether information should be represented jointly instead of forcing `D -> T` compression.

Use the exact same M3 TRAIN/DEV split and frozen micro1000 targets. D1 must be the already sealed DSSD model with **zero refit before the joint fit**.

The historical negative runtime move-ordering result does not constrain this experiment because this is a different causal mechanism: evaluator representation rather than move ordering.

### C0 — minimal two-score stack

Input per sibling:

- byte-identical T0/CURRICULUM scalar;
- sealed D1 scalar;
- parent phase one-hot;
- parent colour.

Fit deterministic pairwise logistic calibration on TRAIN. No other features.

This is the cheapest complementarity test.

### C1 — residual D-on-T

Model:

```text
J = T0 + Delta_D
```

`Delta_D` is fit from the exact 126 DSSD static features (120 production extras + six move-local features) to q1000 pairwise targets.

T0 stays fixed; D features learn only the residual preference.

### C2 — full linear joint static model

Fit a single pairwise model over:

- exact full production PatternEval sparse coordinates;
- exact 126 DSSD features;
- T0 as initialized baseline/prior.

No search score is an input at inference.

This model is a **capacity probe** first. If it later becomes a candidate runtime evaluator, that requires a separate preregistered implementation/cost/strength gate.

### Stage C readout

On M3 DEV publish C0/C1/C2 pairwise and top-hit against q1000, plus deltas versus:

- T0;
- D1 alone;
- best pure-T Stage A arm;
- B0/B1 capacity probes where comparable.

Also publish disagreement decomposition for best joint vs T0/D1.

No strength and no promotion.

## 6. Fixed interpretation matrix

After A/B/C, classify the bottleneck without post-hoc threshold invention.

### Case 1 — pure-T recipe materially improves

If the best G0/G1 pure-T arm recovers clearly more q1000 agreement than A0, the first priority remains transfer optimization. Freeze the best preregistered candidate recipe and move to new fresh deep confirmation.

### Case 2 — unanchored/nonlinear same-observable probe is high, pure production T low

The observables contain the signal but PatternEval linear/quantized/anchor representation is the bottleneck. Prioritize architecture/serialization changes before inventing new game features.

### Case 3 — joint T+D substantially exceeds both T and D

T and D carry complementary usable information. A joint evaluator becomes a first-class candidate architecture and gets a later runtime-cost + fresh-q200 + Elo protocol.

### Case 4 — B1 and joint both remain far below q1000

Static observables are insufficient. Proceed to targeted new-feature discovery from micro-search residual errors.

No arbitrary pass threshold is introduced in this screen; publish effect sizes and CIs. Decisions for a new candidate must be preregistered in the next confirmation document after the screen is complete.

## 7. Later fresh confirmation — reserved, not yet launched

No new fresh q200 cohort may be generated until Stages A/B/C and their immutable readout are complete.

When authorized, the future confirmation will use at minimum:

- exactly 4000 new target-blind parents, 1000/phase;
- selection seed `2026090420`;
- disjoint from M1/M2/M3/M5 and all force pools;
- exact q50/q200 stable-label contract unchanged;
- exact micro1000 diagnostic on same siblings;
- parent-cluster bootstrap 100000 seed `2026090421`;
- frozen candidate bytes before label readout.

The exact candidate(s), multiplicity handling and PASS gate must be written in a separate preregistration **after** the A/B/C screen and **before** this fresh cohort is labelled/read.

## 8. Compute/job policy

Expected next IDs begin at `cpx62-1613+`.

Preferred execution:

1. implementation/tests + prereg/preflight;
2. one batched Stage A/B/C screen job where practical, to avoid repeated runner/worktree overhead;
3. immutable readout;
4. stop and document before any fresh deep confirmation.

Technical failures may be repaired mechanically with new versioned IDs. They may not alter split seed, arm definitions, L2 values, weight function, anchor regimes, D1 artifact, teacher budget, objectives or forbidden-data rule.

Zero selfplay, zero force games, zero champion promotion in this entire preregistration.

## 9. Required final screen summary

The final A/B/C screen must publish at least:

- M3 TRAIN/DEV counts and overlap proof;
- A0-A8 × G0-G2 DEV pairwise/top-hit;
- anchor scale/drift and changed coefficient counts;
- B0 float/int32 ceiling;
- B1 same-observable nonlinear ceiling;
- C0/C1/C2 joint ceilings;
- T0, D1 and micro1000 baselines on the same DEV;
- bootstrap parent-cluster CIs for the principal deltas;
- exact artifact/model/config SHAs;
- zero M5/1612 data reads used for fitting/model selection;
- recommendation among transfer optimization, architecture change, joint evaluator, or new feature discovery.

The purpose is not to crown a champion. It is to identify **where the 99.3% lost teacher headroom is going** before the next expensive fresh campaign.
