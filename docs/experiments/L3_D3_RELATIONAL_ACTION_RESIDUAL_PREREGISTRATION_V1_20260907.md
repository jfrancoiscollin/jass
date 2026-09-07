# L3 Decision Information — D3 relational action residual preregistration

Date: 2026-09-07  
Status: **PREREGISTRATION — ONE LOW-CAPACITY OFFLINE POLICY FIT; WDL VALUE BYTE-IDENTICAL; NO STRENGTH / PROMOTION / BAKE**

## 1. Terminal prerequisite and immutable interpretation

D3 opens only after the separate D2 policy-adapter hypothesis terminated scientifically negative.

```text
job      cpx62-1852-l3-decision-math-d2-policy-adapter-fit-v1
attempt  20260907T063843Z-c72bc010
code     c72bc01080e94739e29b8a31c2fb9248eb994e1d
exit     0
verdict  D2_POLICY_TRANSFER_NOT_ESTABLISHED_V1
```

Frozen held-out facts motivating a new information hypothesis:

```text
C test WDL_CONTROL CE        = 2.122571165760423
C test D2 policy CE          = 2.1639151824437346
C test WDL_CONTROL top1      = 0.2200
C test D2 policy top1        = 0.1500
bootstrap mean delta         = -0.041344016683311356
bootstrap 95% CI             = [-0.07289001378117128, -0.009966458685240516]
value model before/after SHA = identical
```

D1 showed that injecting selected-action supervision into the value model corrupts WDL and overfits. D2 showed that a separate child-state-only 240D policy channel does not generalize, even when the value channel is perfectly isolated.

The single D3 hypothesis is therefore:

> The missing transferable information is primarily **action-relational**, not additional child-state capacity. A fixed WDL_CONTROL ranking may become more teacher-aligned if corrected by a low-capacity function of the actual move semantics and immediate child branching structure.

This is a new mechanism test, not D1/D2 retuning.

## 2. Scientific question

D3 asks exactly one question:

> With WDL_CONTROL held byte-identical and used as the fixed base ordering score, does one frozen low-capacity residual over authenticated move-local semantics improve selected-action ranking on held-out sibling parents?

No model/feature sweep is allowed. The single representation and single optimizer below are frozen prospectively.

## 3. Immutable data roles

Use only the authenticated C SiblingDataset v2:

```text
job      cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1
attempt  20260906T191758Z-4ae3fca8
parents  4000
actions  38053
split    train=3200 / valid=400 / test=400
```

Roles:

```text
C train = D3 fit only
C valid = fixed held-out gate/readout only
C test  = terminal readout once after model bytes are sealed
```

No parent moves between splits. Every parent has equal weight. No filtering by D1/D2/autopsy result is allowed.

Forbidden as fit inputs:

```text
q5/q50/q200 numeric scores
1843 full-ladder values
search bounds / stability / SearchDecisionTrace values
node counts / elapsed time
source row / source shard / split identity
D1 listwise scores
D2 policy-adapter scores
D1/D2 autopsy deltas
WDL targets / Context30 targets
```

The selected action identity is the only teacher target.

## 4. Immutable value/base-order channel

The exact base is the successful D1 `WDL_CONTROL` artifact:

```text
source job  cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1
attempt     20260906T222203Z-08fd187a
artifact    WDL_CONTROL.pjtw.gz
```

D3 MUST NOT refit, rewrite, quantize, blend, scale or otherwise mutate this PJTW.

For each parent/action, let `v_parent(s,a)` be the existing parent-POV WDL_CONTROL child logit already used in D1/D2 offline ranking.

The D3 policy ordering score is frozen as:

```text
score_D3(s,a) = v_parent(s,a) + phi_rel(s,a) dot beta
```

The coefficient on `v_parent` is exactly `1.0` and is not trainable. There is no temperature and no runtime scale.

D3 is a **policy/ranking score only**. It never changes leaf evaluation.

## 5. Frozen relational action representation

D3 deliberately excludes production PatternEval coordinates and the 120 child-state extras used by D2. It uses only action-local semantics already authenticated in C plus immediate child branching fields.

### 5.1 Canonical square orientation

Square indices are canonicalized to the parent side-to-move perspective before encoding:

```text
if parent_stm == black: sq_canon = sq
if parent_stm == white: sq_canon = 49 - sq
```

The same 180-degree mapping is applied to every bit set in `captured_square_bitboard`.

### 5.2 Base action vector — exactly 158 dimensions

For each action:

```text
from_square_onehot_50
+ to_square_onehot_50
+ captured_square_mask_50
+ num_captures / 20
+ promotes {0,1}
+ moving_king {0,1}
+ captured_kings / 20
+ material_count_delta_parent / 20
+ child_pieces / 40
+ child_legal_moves / 64
+ child_forced_capture {0,1}
= 158 dimensions
```

All denominators are fixed physical/schema maxima, not fitted normalizers.

No `static_baseline_parent`, q-score, WDL score, source identity or search-derived field enters `phi_rel`; WDL_CONTROL enters only as the fixed additive base score in Section 4.

### 5.3 Phase-specific block — exactly 632 trainable parameters

The parent phase is one of `P0/P1/P2/P3`. The 158D action vector is placed into exactly one of four disjoint phase blocks:

```text
phi_rel width = 4 * 158 = 632
```

There is no standalone phase bias because any parent-constant additive term cancels inside sibling ranking.

No STM-specific block is used after canonical orientation.

## 6. Frozen objective and optimizer

Exactly one fit is allowed.

For each C-train parent:

```text
p_beta(a|s) = softmax_a score_D3(s,a)
L_parent    = -log p_beta(a_selected|s)
```

Frozen objective:

```text
L_D3(beta) = mean_C_train L_parent + 0.5 * 1e-3 * ||beta||^2
```

Frozen optimizer:

```text
method        = L-BFGS-B
initial beta  = all zeros
max_iter      = 500
maxcor        = 10
gtol          = 1e-6
float         = float64
parent weight = equal
```

At beta=0, D3 ordering is exactly WDL_CONTROL. This identity must be unit-tested.

No early stopping, validation-based checkpoint selection, restart selection, L2 sweep, feature ablation, temperature, calibration or post-fit scaling is allowed.

## 7. Mandatory preflight before fit

A zero-fit preflight must prove on the real C artifact:

```text
parents/actions/splits = 4000 / 38053 / 3200-400-400
all required action-semantic fields present and valid
canonical orientation deterministic
feature width exactly 632
feature bytes deterministic across two independent constructions
beta=0 predictions exactly equal WDL_CONTROL ordering logits
value-model SHA authenticated
qscore/full-ladder/SearchDecisionTrace reads = 0
valid/test metrics read = 0
fits = 0
```

Any mismatch is technical/contract INVALID and must be repaired without changing the preregistration.

## 8. Frozen held-out readout

After exactly one fit and adapter seal, publish on train/valid/test:

```text
selected-action cross-entropy
selected-action probability mean
top1 agreement
top2 containment
fraction CE improved vs WDL_CONTROL
mean / median paired delta CE
q05/q25/q75/q95 paired delta CE
catastrophic regression rate delta_ce < -1 nat
large improvement rate delta_ce > +1 nat
```

Publish the same readout by:

```text
phase P0/P1/P2/P3
parent STM black/white
action-count band 2-4 / 5-8 / 9-16
```

Also publish:

```text
optimizer status / iterations / gradient_inf_norm
beta L2 norm / max abs / nonzero count
value model SHA before/after
feature hash / width
forbidden-input counters
```

## 9. Terminal statistic and gates

Primary paired statistic on C test:

```text
delta_decision = CE_WDL_CONTROL - CE_D3
```

Parent bootstrap:

```text
replications = 200000
seed         = 2026111201
CI           = percentile 95%
```

Support/contract PASS requires:

```text
exact parents/actions/splits
fit count = 1
optimizer success = true
feature width = 632
feature determinism = true
beta=0 base identity = true
forbidden fit inputs read = 0
WDL/value model byte drift = 0
model searches = 0
hyperparameter sweeps = 0
teacher searches = 0
```

Transfer PASS requires all support gates plus:

```text
valid point delta_decision > 0
C-test bootstrap LCB95(delta_decision) > 0
C-test top1_D3 >= top1_WDL_CONTROL
C-test point delta_decision > 0 in each phase P0/P1/P2/P3
C-test point delta_decision > 0 for both parent STM values
```

Action-count bands and tail rates are diagnostics, not extra gates.

## 10. Terminal verdicts

```text
D3_RELATIONAL_ACTION_TRANSFER_ESTABLISHED_V1
D3_RELATIONAL_ACTION_TRANSFER_NOT_ESTABLISHED_V1
D3_RELATIONAL_ACTION_TRANSFER_INVALID_V1
```

`NOT_ESTABLISHED` is a scientific STOP for this exact representation. It does not authorize adding/removing features, changing phase blocks, changing L2, changing baseline coefficient, adding SearchDecisionTrace, blending scores or tuning a runtime scale.

## 11. Authorization boundary

Even a D3 offline PASS authorizes only preparation of a new separately preregistered **runtime move-ordering-only** experiment.

In that later experiment:

```text
WDL_CONTROL remains the only value/leaf evaluator
D3 may affect ordering only
no value blending/scaling
TT/root-priority semantics remain authoritative
```

D3 itself authorizes no equal-node/equal-time games, force pool, promotion, bake or champion replacement.

## 12. Explicit exclusions

```text
D1/D2 reopening or retuning
SearchDecisionTrace as fit input
q-score targets or q-score features
1843 reference values
WDL/PatternEval refit
child production extras
pattern coordinates
feature/model search
feature ablation
adapter-width search
L2/temperature/scale search
new teacher search
new self-play
strength games
promotion/bake
```

## 13. Execution order

```text
D3 preregistration frozen + CI
 -> implementation + synthetic tests
 -> real-data zero-fit preflight
 -> exactly one 632-parameter fit on C train
 -> seal adapter bytes
 -> read fixed valid + terminal test once
 -> D3 verdict
 -> STOP
```
