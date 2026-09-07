# L3 Decision Information — D2 separate decision-policy adapter preregistration

Date: 2026-09-07
Status: **PREREGISTRATION — ONE LOW-CAPACITY OFFLINE FIT; VALUE MODEL BYTE-IDENTICAL; NO STRENGTH / PROMOTION / BAKE**

## 1. Terminal prerequisite and immutable interpretation

D2 is a new scientific proposal after the terminal D1 treatment failed. D1 itself stays closed and is not retuned.

Immutable D1 terminal source:

```text
fit/readout job  cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1
attempt          20260906T222203Z-08fd187a
terminal verdict D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1
```

Immutable autopsy source:

```text
job              cpx62-1850-l3-decision-math-d1-terminal-autopsy-v1
attempt          20260907T052814Z-384c5d34
code             384c5d34039909a040c6927650201b9734572217
verdict          D1_TERMINAL_AUTOPSY_COMPLETE_V1
classification   TRAIN_FIT_WITH_HELDOUT_REVERSAL_AND_WDL_CONFLICT
```

The autopsy is motivation only. None of its parent-level outcomes may be used to choose D2 hyperparameters, filter parents, relabel actions, select features, select a model, or tune a runtime scale.

The terminal D1 facts motivating a mechanism change are:

```text
C train: control CE 2.1203775411 -> listwise CE 0.3078593677
         top1       0.180625     -> 0.9690625
         delta CE   +1.8125181735

C valid: control CE 2.1590752272 -> listwise CE 2.6292181675
         delta CE   -0.4701429403

C test:  control CE 2.1225711658 -> listwise CE 2.6636797464
         top1       0.220000     -> 0.185000
         delta CE   -0.5411085806
         catastrophic parent regressions delta<-1 = 0.3325

CURRENT holdout WDL:
         control logloss  0.4474049103
         listwise logloss 0.5782191090
         delta_wdl        +0.1308141987
         frozen tolerance +0.0020000000

A/B PJTW displacement:
         changed weights  462092 / 8503296
         extras MG changed 120 / 120
         extras EG changed 120 / 120
         all-weight sign flips among jointly nonzero = 0.1339681111
```

The causal interpretation frozen before D2 is therefore:

> Selected-action supervision is a policy/ranking signal. Injecting it directly into the high-capacity PatternEval value parameterization allowed near-complete teacher-train memorization, reversed on held-out parents, and materially damaged WDL. D2 tests the signal in a separate low-capacity policy channel while leaving the value model immutable.

This is not a claim that D2 will work. It is the single frozen hypothesis to test.

## 2. Scientific question

D2 asks exactly one question:

> With the successful D1 `WDL_CONTROL` value model held byte-identical and never refit, does a separate 240-parameter linear policy adapter trained only on the authenticated selected-action identities generalize to held-out sibling decisions?

The mechanism change relative to D1 is **channel + capacity**, not treatment weight.

D2 has:

```text
lambda sweep       = 0
temperature sweep  = 0
model search       = 0
feature search     = 0
new teacher search = 0
WDL fits/refits    = 0
strength games     = 0
```

## 3. Immutable data roles

D2 reuses exactly the authenticated Workstream-C sibling dataset:

```text
source job  cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1
attempt     20260906T191758Z-4ae3fca8
verdict     C_SIBLING_DATASET_V2_AUTHENTICATED_V1
parents     4000
actions     38053
split       train=3200 / valid=400 / test=400
```

Roles are immutable:

```text
C train = adapter fit only
C valid = preregistered held-out generalization gate/readout only
C test  = terminal readout exactly once after adapter bytes are sealed
```

No parent may move between splits. No parent/action may be dropped or reweighted from D1/autopsy outcomes. Every parent remains equal-weight in the listwise objective.

Forbidden as D2 fit inputs:

```text
q5/q50/q200 numeric scores
full-ladder 1843 values
search bounds
survivor margins
elapsed time/node cost
B3 audit outcome
WDL/Context targets
source identity
split identity
D1 listwise model scores
D1 autopsy deltas/tails
```

The selected action identity from authenticated C is the only teacher target.

## 4. Immutable value channel

The value/evaluation channel is the exact successful D1 control artifact:

```text
source job  cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1
attempt     20260906T222203Z-08fd187a
artifact    WDL_CONTROL.pjtw.gz
```

The D2 implementation must authenticate the exact result manifest and record the decompressed PJTW SHA256 before any adapter fit.

D2 MUST NOT modify, average, blend, rescale, refit, requantize, or rewrite `WDL_CONTROL`.

For every D2 stage:

```text
value_model_before_sha256 == value_model_after_sha256
```

is a hard contract.

## 5. Frozen policy input class

D2 deliberately removes the 8cf pattern coordinates from the decision learner.

For each child position it uses exactly the existing **120 production extras** already emitted by the C/D1 production feature path, with the existing tempo-stage interpolation:

```text
phi(child) = [w_mg(child) * extras_120(child),
              w_eg(child) * extras_120(child)]
width      = 240
```

No normalization is fit. No pattern bucket, move-local feature, parent context feature, q-score, WDL score, D1 score, source tag, or new observable is permitted.

The feature implementation must reuse the production `build_extras_phased`/tempo semantics and prove deterministic equality against the D1/C feature path before fitting.

## 6. Frozen adapter and objective

Exactly one adapter fit is allowed.

The adapter is a zero-initialized linear ranker:

```text
r_black(child) = phi(child) dot beta
beta shape     = (240,)
```

Parent-POV action score:

```text
r_parent(s,a) = +r_black(child(s,a))  if parent stm = black
              = -r_black(child(s,a))  if parent stm = white
```

The policy adapter is **not added to the value score**. It is a separate rank score.

For each C-train parent:

```text
p_beta(a|s) = softmax_a r_parent(s,a)
L_policy(s) = -log p_beta(a_selected|s)
```

Frozen training objective:

```text
L_D2(beta) = mean_C_train L_policy(beta) + 0.5 * 1e-3 * ||beta||^2
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

`L2=1e-3` is fixed prospectively as the established pairwise/ranking regularization scale used in prior sibling-ranking work. It is not selected from D1/autopsy outcomes and cannot be varied inside D2.

No early stopping, validation-based checkpoint choice, line-search recipe change, seed/model ensemble, restart selection, temperature, or post-fit calibration is allowed.

## 7. Why this is a redesign rather than D1 retuning

D1 optimized millions of value parameters under a joint WDL + selected-action objective. D2 instead:

```text
changes WDL/value parameters     = 0
adapter parameters               = 240
shares D1 lambda                 = no
uses D1 listwise model           = no
uses a decision/value blend      = no
uses a runtime scale             = no
```

The policy channel can therefore fail without corrupting value evaluation.

This preregistration does not assert that reduced capacity is sufficient; held-out testing decides that.

## 8. Frozen readout

Before fitting, implementation must freeze the terminal readout code and test it on synthetic fixtures.

For `WDL_CONTROL`, use its parent-POV child value score exactly as the offline control decision ranking.

For `D2_POLICY_ADAPTER`, use `r_parent` alone. Do not add or scale the WDL score.

On C train/valid/test publish parent-equal:

```text
selected-action cross-entropy
selected-action probability mean
top1 agreement
top2 containment
fraction with CE improvement vs WDL_CONTROL
median and mean paired CE delta
CE delta q05/q25/q75/q95
catastrophic regression rate: delta_ce < -1 nat
large improvement rate:       delta_ce > +1 nat
```

Publish the same metrics by:

```text
phase x stm cell: P0_stm0 ... P3_stm1
action-count band: 2-4 / 5-8 / 9-16
```

Also publish:

```text
optimizer convergence/status/gradient
beta L2 norm / max abs / nonzero count
value-model SHA before/after
feature replay equality
forbidden-input counters
```

CURRENT WDL is not re-evaluated as a candidate metric because candidate D2 cannot alter the value model. Byte identity is the stronger invariant.

## 9. Frozen terminal statistics and gates

Primary paired statistic on C test:

```text
delta_decision = CE_WDL_CONTROL - CE_D2_POLICY_ADAPTER
```

Positive means the adapter is better.

Parent bootstrap:

```text
replications = 200000
seed         = 2026111001
CI           = percentile 95%
```

D2 support/contract PASS requires all of:

```text
exact parents/actions/splits = 4000 / 38053 / 3200-400-400
adapter fit count            = 1
optimizer success            = true
feature replay equality      = true
forbidden fit inputs read    = 0
WDL/value model byte drift   = 0
model searches               = 0
hyperparameter sweeps        = 0
new teacher searches         = 0
```

D2 transfer PASS requires support/contract PASS and all of:

```text
valid point delta_decision > 0
C-test bootstrap LCB95(delta_decision) > 0
C-test top1_adapter >= top1_control
C-test point delta_decision > 0 in each P0/P1/P2/P3
C-test point delta_decision > 0 for both parent STM values
```

The action-count bands and catastrophic-tail rates are mandatory diagnostics but are not additional gates.

The valid split is a fixed preregistered gate, not a tuning surface. No parameter or model choice follows from valid metrics.

## 10. Terminal verdicts

Exact terminal classifications:

```text
D2_POLICY_TRANSFER_ESTABLISHED_V1
D2_POLICY_TRANSFER_NOT_ESTABLISHED_V1
D2_POLICY_TRANSFER_INVALID_V1
```

`ESTABLISHED` requires every gate in Section 9.

`NOT_ESTABLISHED` is a scientific STOP for this exact separate-policy hypothesis. It does not authorize widening the adapter, adding patterns, adding move-local features, changing L2, blending the value score, changing temperature, filtering parents, or replacing the selected-action target.

`INVALID` is technical/provenance/contract failure only.

## 11. Authorization boundary

Even a D2 offline PASS does **not** directly authorize games.

A D2 PASS may authorize only preparation of a **new, separately preregistered runtime move-ordering experiment** in which:

```text
WDL_CONTROL remains the only leaf/value evaluator
policy adapter may affect ordering only
TT/root-priority semantics remain authoritative
no value blending or scaling is introduced
```

That later preregistration must independently freeze integration semantics, support, baseline, equal-node/equal-time protocol, pools, seeds, gates and stopping rules before any strength result is read.

D2 itself authorizes none of:

```text
equal-node games
equal-time games
force pools
scaling/blending
promotion
bake
champion replacement
```

## 12. Explicit exclusions

D2 excludes:

```text
D1 retuning or reopening
lambda/tau/temperature sweep
q-score soft targets
full-ladder target reads
new teacher search
new self-play
WDL fit/refit
PatternEval fit/refit
pattern-coordinate decision learning
move-local feature expansion
feature/model search
adapter-width search
regularization search
value/policy blending
runtime scale tuning
strength games
promotion/bake
```

Fisher/JFI constraints are not part of D2. They remain a distinct future hypothesis and cannot be combined post hoc with this test.

## 13. Execution order

```text
D2 preregistration frozen + CI
 -> implementation + deterministic synthetic tests
 -> source/value/feature authentication preflight (zero fit)
 -> exactly one 240-parameter adapter fit on C train
 -> seal adapter bytes
 -> read valid + terminal C test once under frozen readout
 -> D2 verdict
 -> STOP
```

No implementation or fit is authorized by this document until the preregistration itself is merged/frozen.