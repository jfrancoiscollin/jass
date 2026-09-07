# L3 Decision Information — D2 constrained dense residual preregistration

Date: 2026-09-07
Status: **PREREGISTRATION — NEW TRANSFER HYPOTHESIS; NO RESULT READ / NO STRENGTH**

## 1. Motivation and immutable upstream facts

D1 is terminally negative and remains closed.

Terminal D1:

```text
job      cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1
attempt  20260906T222203Z-08fd187a
code     08fd187aa187f26bd7179df2c68056a74e28355d
verdict  D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1
```

D1 test facts:

```text
WDL_CONTROL decision CE        2.122571165760423
WDL_LISTWISE decision CE       2.663679746350313
WDL_CONTROL top1               0.2200
WDL_LISTWISE top1              0.1850
bootstrap delta CE mean       -0.5411085805898891
bootstrap CI95                [-0.6711978221237396,-0.41357982190054965]
WDL_CONTROL holdout logloss    0.4474049103356601
WDL_LISTWISE holdout logloss   0.5782191090486537
delta_wdl                      0.1308141987129936
WDL noninferiority tolerance   0.002
```

Terminal autopsy:

```text
job      cpx62-1850-l3-decision-math-d1-terminal-autopsy-v1
attempt  20260907T052814Z-384c5d34
code     384c5d34039909a040c6927650201b9734572217
verdict  D1_TERMINAL_AUTOPSY_COMPLETE_V1
class    TRAIN_FIT_WITH_HELDOUT_REVERSAL_AND_WDL_CONFLICT
```

The autopsy established all of:

```text
teacher_train_fit       = true
heldout_reversal        = true
wdl_conflict            = true
mean_probability_up_ce_worse = true
```

D2 does **not** reinterpret D1 as inconclusive and does not tune D1 lambda. It tests a new causal transfer hypothesis:

> the B3 teacher decision signal may generalize if it is restricted to a very small production-native residual subspace, trained only against genuinely ambiguous competitors, while WDL degradation is enforced as a hard feasibility constraint rather than checked only after fitting.

## 2. Immutable data inputs

SiblingDataset v2 remains the only decision dataset:

```text
job      cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1
attempt  20260906T191758Z-4ae3fca8
code     4ae3fca82f19338132911811978761b91bd39573
verdict  C_SIBLING_DATASET_V2_AUTHENTICATED_V1
parents  4000
actions  38053
train    3200
valid    400
test     400
```

The frozen C parent split is reused byte-for-byte. No resplit, drop-after-metric, top-up, new teacher search or full-ladder backfill is allowed.

The WDL base is the exact sealed `WDL_CONTROL.pjtw.gz` from D1 job 1849. D2 does not refit a baseline model.

The WDL corpus/targets are the same immutable CURRENT_2M inputs used by D1:

```text
records          2000000
train records    1800796
holdout records   199204
split seed        577215
holdout mod       10
```

Source provenance and bytes must be authenticated before the first D2 optimization step using the same immutable historical inputs/receipts as D1. The D1 job-1849 attempt identity is sufficient to identify the exact sealed base; the D2 preflight must publish its raw model SHA256 before optimization begins.

## 3. Hard information barrier

D2 may read from C only:

- parent/action identity and split;
- production child state / 120 production extras;
- allocation booleans `searched5/50/200`, `survived5/50`, `selected`;
- exactness fields for structural validation only.

D2 must **not** use as optimization targets or features:

```text
q5 score_parent
q50 score_parent
q200 score_parent
missing-horizon numeric substitution
1843 full-ladder reference values
1844 mismatch/value diagnostics
D1 valid/test metrics during fitting or scale selection
source identity
parent id/hash
move-local from/to/capture geometry
```

No numeric teacher value or softmax temperature is created.

## 4. Frozen model class

D2 preserves every PatternEval pattern coefficient from sealed WDL_CONTROL exactly.

Only the 120 existing production dense extras may move, with the existing MG/EG phasing. The trainable residual is therefore exactly:

```text
120 extras MG coefficients
120 extras EG coefficients
--------------------------
240 scalar parameters total
```

No intercept. No new feature. No hidden layer. No phase-specific extra bank beyond the existing production MG/EG interpolation. No colour-specific bank. No architecture/model search.

For child `i`, residual score is the exact production dense-extra design:

```text
r_i = Xext_i @ delta
z_i = z_control_i + r_i
```

where `z_control_i` is the sealed WDL_CONTROL black-perspective logit and `delta` has length 240.

Parent-POV decision score remains:

```text
parent stm black: q_i = +z_i
parent stm white: q_i = -z_i
```

## 5. Frozen decision target — survived-5k hard competitors

D1 one-hot listwise over every legal sibling is retired for D2.

For each C parent, define the D2 competitor set structurally, before any model score is read:

```text
selected = the unique action with selected=true
hard competitors = all non-selected actions with survived5=true
```

A parent is D2 decision-eligible iff:

```text
selected action has survived5=true
hard competitor count >= 1
```

All other parents remain in the dataset/readout but contribute zero D2 decision gradient. Eligibility is determined only from authenticated allocation booleans, never from score magnitude or model performance.

No `survived50`, `searched200`, q-score magnitude or post-hoc difficulty threshold changes this definition.

For each eligible parent and hard competitor `j`, use pairwise logistic loss:

```text
ell_j = log(1 + exp(-(q_selected - q_j)))
```

Within a parent, challengers receive equal weight summing to one. Eligible parents receive equal weight. Thus large branching factors cannot dominate the objective.

## 6. Frozen optimization recipe

One D2 residual fit only. No arm sweep.

```text
initial delta     = zero[240]
loss              = mean parent pairwise logistic + 1e-5 * 0.5 * ||delta||^2
optimizer         = L-BFGS-B
max_iter          = 2000
maxcor            = 20
gtol              = 1e-4
normalization     = none; exact production raw dense-extra design
train parents     = C train only
valid/test reads  = forbidden until final candidate bytes are sealed
```

The `1e-5` regularizer is inherited from the frozen D1/WDL fitting recipe; it is not swept.

The unconstrained residual fit is not itself a candidate. It supplies a single direction/endpoint `delta_raw`.

## 7. Hard WDL feasibility projection

D2 converts `delta_raw` into the final production residual only by a scalar feasibility projection controlled exclusively by WDL **training** loss.

Let `alpha in [0,1]` and:

```text
delta(alpha) = alpha * delta_raw
candidate(alpha) = WDL_CONTROL with only its 120 MG + 120 EG extras changed by delta(alpha)
```

Pattern coefficients remain byte-identical to WDL_CONTROL for every alpha.

Define exact CURRENT_2M training logloss on the fixed 1,800,796 WDL training rows:

```text
DeltaWDL_train(alpha) = logloss_train(candidate(alpha)) - logloss_train(WDL_CONTROL)
```

Feasibility threshold is frozen to the existing D1 noninferiority tolerance:

```text
DeltaWDL_train <= 0.002000
```

Selection of alpha may use **only** this feasibility condition. Decision valid/test metrics are forbidden during projection.

Algorithm:

1. test alpha=1.0 using the exact production-quantized candidate;
2. if feasible, seal alpha=1.0;
3. otherwise run deterministic bisection on `[0,1]` for exactly 32 iterations;
4. each bisection point is serialized with the production PJTW v3 writer and evaluated after reload/quantization on WDL train;
5. retain the largest bisection lower endpoint observed feasible;
6. final serialized candidate must satisfy `DeltaWDL_train <= 0.002000`; otherwise D2 is invalid.

This is a feasibility projection, not a lambda/alpha performance sweep: no decision metric may influence alpha.

## 8. Candidate sealing and invariants

Before reading C valid/test:

- seal candidate PJTW bytes and SHA256;
- publish alpha and projection trace;
- prove all pattern MG/EG coefficients are exactly identical to WDL_CONTROL;
- prove only the 240 dense-extra slots may differ;
- publish changed-slot count, RMS/max displacement and quantization receipt;
- publish exact WDL train delta;
- optimizer must converge successfully;
- C valid/test access counter remains zero.

If any invariant fails, verdict is `D2_CONSTRAINED_DENSE_RESIDUAL_INVALID_V1` and STOP.

## 9. Offline readout after seal

After candidate bytes are sealed, read C valid and test exactly once for terminal readout.

For CONTROL and D2 candidate publish on valid and test:

1. full legal selected-action cross entropy;
2. full legal selected-action probability;
3. full legal top1 and top2;
4. D2 survived-5k pairwise logistic loss on structurally eligible parents;
5. survived-5k pairwise accuracy;
6. all metrics by phase×STM cell and legal-action band;
7. eligible-parent counts globally and by cell.

WDL holdout is evaluated on the immutable 199,204 rows only after candidate seal.

No model selection, early stopping, refit or alpha change is permitted after valid/test/holdout reads.

## 10. Frozen bootstrap and support

Primary decision bootstrap is parent-cluster bootstrap on **test eligible parents**:

```text
replications = 200000
seed         = 2026111001
metric       = mean(pairwise_logistic_CONTROL - pairwise_logistic_D2)
```

Support requires:

```text
test eligible parents >= 300
each of the 8 phase×STM cells has >= 25 eligible test parents
valid/test parent split identities exactly C-v2
symmetry overlap remains zero
```

Support failure is terminal INVALID/STOP; no threshold relaxation is allowed.

## 11. Terminal gates

Define:

```text
delta_pairwise = pairwise_loss_CONTROL - pairwise_loss_D2  # positive is D2 better
delta_wdl_holdout = logloss_D2 - logloss_CONTROL
```

D2 PASS requires all:

```text
A. support PASS
B. bootstrap LCB95(delta_pairwise_test) > 0
C. full-legal selected CE on test: D2 <= CONTROL
D. full-legal top1 on test: D2 >= CONTROL
E. delta_wdl_holdout <= 0.002000
F. pattern bytes/coefficients unchanged and production replay/quantization guards PASS
```

Valid-set metrics are diagnostic and cannot rescue a test failure.

Terminal verdicts are exactly:

```text
D2_CONSTRAINED_DENSE_RESIDUAL_ESTABLISHED_V1
D2_CONSTRAINED_DENSE_RESIDUAL_NOT_ESTABLISHED_V1
D2_CONSTRAINED_DENSE_RESIDUAL_INVALID_V1
```

Only `ESTABLISHED` may authorize a separately preregistered equal-node causal strength gate. It does **not** authorize promotion or bake.

`NOT_ESTABLISHED` is terminal for this D2 recipe: no lambda/L2/alpha/competitor-definition retuning, no additional residual capacity and no same-dataset retry with changed science.

## 12. Explicit exclusions

D2 authorizes none of:

```text
D1 lambda retuning
lambda sweep
alpha decision sweep
temperature sweep
L2 sweep
feature/model search
pattern-weight updates
new architecture
new teacher search
new self-play
1843 full-ladder targets
qscore soft labels
valid/test gradient reads
strength games
equal-node/equal-time before D2 PASS
E/F workstreams
teacher-data scaling
promotion
bake
champion replacement
```

Technical failures may be repaired/requeued only if the preregistered science above remains byte-for-byte semantically unchanged.

## 13. Execution order

```text
preregistration merge
 -> implementation + deterministic tests
 -> preflight/source/base authentication
 -> one 240-parameter raw residual fit on C-train
 -> WDL-train-only feasibility projection
 -> seal production PJTW candidate
 -> one terminal valid/test + WDL-holdout readout
 -> terminal D2 verdict
 -> STOP
```
