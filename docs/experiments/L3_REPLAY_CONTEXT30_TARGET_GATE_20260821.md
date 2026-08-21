# L3 — REPLAY25 native WDL vs historical CONTEXT_30 target gate

Date: 2026-08-21  
Tracking: issue #552

## 1. Question

The exploratory four-arm replay DOE trained arm B with the native WDL carried by
JNNW.  Its context-aware behaviour came only indirectly from the immutable
CURRICULUM prior; CTX3 predictions and the failed CTX4 decision rule were not
used as labels.

This experiment asks one narrower causal question:

> On the exact REPLAY25 rows, weights, prior and fit recipe, does replacing
> native WDL with the historical aligned `context30` target improve force?

The experiment does **not** reopen the terminal CTX4 verdict.  It tests the
historical scalar target recipe that produced CURRICULUM, not the CTX4
conditional decision channel.

## 2. Arms

### Baseline — `B_NATIVE`

Immutable model B from:

- job `cpx62-1449-l3-exploratory-replay-four-arm-doe-v1`;
- attempt `20260820T224246Z-7b22be6f`;
- source code `7b22be6f4a8898035505d010f872066ac987888a`.

Its recipe is:

- all D2 train rows;
- deterministic whole-opening D1 replay;
- effective loss mass `NEW=0.75`, `OLD=0.25`;
- native JNNW WDL target;
- prior mean CURRICULUM, prior decay zero;
- exact-fold, tempo-stage, exact dense extras;
- L2 `1e-5`, L-BFGS gtol `1e-4`, max iterations `2000`, maxcor `20`.

The model is reused byte for byte.  It is not refit.

### Treatment — `B_C30`

`B_C30` uses byte-identical:

- JNNW rows and order;
- JSM metadata and source namespaces;
- float32 sample weights;
- effective 75/25 source mass;
- CURRICULUM prior and prior decay;
- architecture, feature dump, exact constraints, optimizer and budget.

The only scientific change is the target:

```text
context30 = 0.70 × terminal_WDL_black
          + 0.30 × conditional_WDL_black
```

The output is converted to black-POV probability in `[0,1]` and consumed as an
external target by the otherwise identical PatternEval fit.

## 3. Target reconstruction

The exact historical target builder is pinned by Git blob:

`968b253084e272d69f61f952e47ec71471aaadf5`

Its fixed recipe is:

- legacy `ctx1-legacy-120` context matrix, 11 components derived from the
  120 production extras;
- five folds;
- fold seed `20260811`;
- folds grouped by complete `game_id`;
- uniform row weighting;
- ridge `1e-4`;
- 50 mapper iterations;
- tolerance `1e-8`;
- 20 line-search steps;
- alpha `0.30`.

The replay corpus contains training rows only.  A small adapter appends one
unique synthetic holdout row in memory solely to satisfy the historical
builder's non-empty-holdout API.  That row is excluded from every OOF mapper
training fold, every fold-local RMS estimate, every emitted target and the
PatternEval fit.  A regression test requires the real train-prefix predictions
and float32 targets to be exactly identical to the historical builder supplied
with an ordinary disjoint holdout.

## 4. Input identity gate

Before any target construction or fit, the job must reproduce the D1/D2 opening
splits and the REPLAY25 mix using the original seeds:

- split seed `577215`;
- holdout modulus `10`;
- replay seed `2026082106`.

The reconstructed mix must match the immutable 1449 manifest in:

- data SHA-256;
- metadata SHA-256;
- sample-weight SHA-256;
- row counts and ordering;
- whole-opening selection;
- realised OLD/NEW mass;
- source metadata and holdout exclusion.

A mismatch aborts before the fit.

## 5. Model gate

Exactly one new model may be produced.  `B_C30` must:

- converge under the same optimizer contract as B_NATIVE;
- satisfy exact-fold and exact dense-extras residual zero;
- consume the certified target SHA;
- consume the certified replay weight SHA;
- use the immutable CURRICULUM raw model SHA;
- load successfully in the common engine.

Engine and training semantics under `src/` and `pattern_jass/tools/` must not
drift from the 1449 fit commit.  The target adapter and readout are the only new
scientific tooling.

## 6. Force protocol

The causal contrast is:

```text
B_C30 (candidate) vs B_NATIVE (baseline)
```

Two new, mutually disjoint pools are generated:

- 3,000 openings per pool;
- candidate pool size 40,000;
- pool seeds `2026082211` and `2026082212`;
- all 23 historical pools excluded, including both 1451 selection pools and
  both 1454 B-vs-CURRICULUM promotion pools.

Each pool is played in two views:

- native move time `0.1 s` — primary;
- Q00 depth 9 — diagnostic only.

Other fixed settings:

- paired colours, one pair per opening;
- 160-ply cap;
- 12 shards, maximum parallelism 12;
- 200,000 paired bootstrap draws;
- gate seeds `2026082213` to `2026082216`;
- combined bootstrap seeds `2026082217` and `2026082218`;
- 24,000 games total.

## 7. Classification

Native is `ESTABLISHED_POSITIVE` only if all conditions pass:

1. both pool point estimates exceed 50%;
2. the two effects are compatible at 95%;
3. the combined paired-bootstrap CI95 lower bound exceeds 50%;
4. combined `P(score > 50%) >= 97.5%`.

`ESTABLISHED_NEGATIVE` uses the symmetric conditions below 50%.  Every other
outcome is `NOT_ESTABLISHED`.  Q00 is reported but cannot override native.

Terminal verdicts:

- `JASS_REPLAY_CONTEXT30_TARGET_ESTABLISHED_POSITIVE`;
- `JASS_REPLAY_CONTEXT30_TARGET_ESTABLISHED_NEGATIVE`;
- `JASS_REPLAY_CONTEXT30_TARGET_NOT_ESTABLISHED`.

A positive result authorizes only a later, separately preregistered direct gate
of `B_C30` against CURRICULUM.  It does not promote a model automatically.

## 8. Safety and scope

- refits: exactly 1;
- models reused: exactly 1;
- new self-play: 0;
- frozen cohorts read: 0;
- automatic continuation: disabled;
- automatic promotion: disabled;
- CTX4 verdict remains `JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED`.

Technical defects may be repaired without changing data identities, target
recipe, seeds, budgets, pool exclusions or decision thresholds.
