# L3 — Exploratory fresh-2M corpus and replay/anchor DOE

Date: 2026-08-20  
Tracking: issue #544

## 1. Scientific status

This is an **exploratory post-CTX4 campaign** requested after the terminal read-only screen.

The immutable result remains:

- job: `cpx62-1446-l3-context4-uncertainty-screen-v6`;
- attempt: `20260820T193737Z-f206a837`;
- verdict: `JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED`;
- next stage authorized: false.

Nothing in this campaign may be used to claim that CTX4 passed.  The purpose is narrower: test whether a second independent 2M corpus and explicit replay change the quality of an otherwise compatible WDL fit.

## 2. D1 and D2

### D1

The historical corpus is the immutable 1409 corpus:

- `cpx62-1409-l3-context2-intervention-corpus-v1`;
- attempt `20260818T184956Z-3465ec72`;
- exactly 2,000,000 JNNW/JSM2 records.

### D2

D2 reuses the certified 1409 generation recipe pinned by Git blob:

`3b52e23f2de4e526347a22fe68a280d48107be31`

The only scientific generation change is:

- old seed: `2026081805`;
- new seed: `2026082105`.

Everything else remains fixed: plan 1408, CURRICULUM 1341 and its raw hash, six cells and quotas, Q00, exploration rules, WDL labeling, pairing, split self-play RNGs, JSM2, producer count and audit.

Expected quotas:

| Cell | Records |
|---|---:|
| BASE | 300,000 |
| ROP16 | 600,000 |
| EPS16 | 500,000 |
| DECAY120 | 100,000 |
| TOPK3M30 | 100,000 |
| DEPTH10 | 400,000 |
| **Total** | **2,000,000** |

D2 acceptance requires exact cardinality, valid WDL, JNNW/JSM2 alignment, exact cell quotas, immutable hashes and provenance, no fit, no force game, no frozen read and no promotion.

## 3. Target compatibility

The fit DOE uses only the **native WDL target carried by JNNW**.  This target has the same semantics in D1 and D2.

Old CTX3 predictions and the failed CTX4 decision rule are not used as training labels.  This prevents mixed target semantics from confounding the replay comparison.

## 4. Splits

Splits are made by whole opening/game groups, never by isolated records.

- OLD train and OLD holdout are opening-disjoint.
- NEW train and NEW holdout are opening-disjoint.
- No holdout row is admitted to replay or full-history training.
- The split seed, replay seed and any balanced diagnostic sampling seed are fixed before model outcomes.

## 5. Four fit arms

All arms use the same architecture, exact-fold/tempo feature construction, exact-extras projection, optimizer limits, L2 setting, convergence gate and compute budget.

### A — CURRENT

All D2 train rows, native WDL target, and the current champion as `prior-mean`.

### B — REPLAY25

All D2 train rows plus a D1 replay selected by complete openings.  Sample weights impose exactly:

- 75% effective NEW loss mass;
- 25% effective OLD loss mass.

The champion prior is identical to A.

### C — REPLAY25_NO_PRIOR

Exactly the same mixed rows and sample weights as B, with no champion prior.

### D — FULL_HISTORY_NO_PRIOR

The complete compatible D1 and D2 training union, no champion prior.  Its explicit source weighting and physical compute cost must be reported.

## 6. Readouts

Before force games, every arm must publish:

- optimizer success and gradient norm;
- exact dense-extras residuals;
- OLD holdout loss;
- NEW holdout loss;
- a predeclared balanced OLD/NEW diagnostic loss;
- train rows, effective source mass and wall/CPU cost;
- model and input hashes.

Primary offline contrast: `B - A`.  Secondary contrasts: `B - C` and `C - D`.

## 7. Force protocol

Force evidence is staged only after all four fits pass technical and convergence gates.

- fresh mutually disjoint opening pools;
- explicit exclusion of all historical force pools;
- paired colours and identical topology;
- native budget primary;
- Q00 diagnostic only;
- fixed bootstrap/readout seeds;
- no automatic promotion.

The exact game allocation and terminal thresholds must be committed before the first force result is observed.  No arm, replay ratio, prior strength or pool may be selected post hoc.

## 8. Interpretation

- `B > A`, OLD stable, NEW stable/improved: retain explicit replay.
- `A ≈ B`: retain simpler CURRENT.
- B improves OLD but harms NEW: replay25 is over-constraining; no dose tuning on the same evidence.
- B is worse on OLD and NEW: close replay25 for this recipe.
- `B - C` estimates the value of the champion prior within the same mixed data.
- `C - D` compares compact replay with complete historical retraining without a prior.

## 9. Safety and scope

- `NO_FROZEN_READ=1`;
- `NO_AUTOMATIC_PROMOTION=1`;
- no implicit continuation or promotion;
- technical defects may be repaired, but the locked generation seed and DOE arms may not be changed after outcomes;
- all results remain exploratory and do not alter the negative CTX4 verdict.
