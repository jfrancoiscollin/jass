# L3 Decision Information — D1 WDL + selected-action listwise preregistration

Date: 2026-09-06
Status: **PREREGISTRATION — EXACTLY TWO OFFLINE FITS; NO STRENGTH / PROMOTION / BAKE**

## 1. Terminal prerequisite

D1 opens only because Workstream C terminated authenticated:

```text
job      cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1
attempt  20260906T191758Z-4ae3fca8
code     4ae3fca82f19338132911811978761b91bd39573
verdict  C_SIBLING_DATASET_V2_AUTHENTICATED_V1
parents  4000
actions  38053
split    train=3200 / valid=400 / test=400
full_ladder_reference_reads = 0
reference_backfill          = false
```

The C result is fetched through the exact runner-v3 job/attempt/code identity and its authenticated result manifest/checksums. No D stage may substitute another C artifact.

## 2. Question

D1 asks one causal question:

> Holding the PatternEval architecture, WDL corpus/targets, optimizer, prior, split and training budget fixed, does adding parent-level teacher-decision supervision improve static sibling decisions without material WDL regression?

D1 is an offline transfer screen. It does not measure playing strength.

## 3. Why D1 does not softmax raw q200 values

The authenticated C-v1 records intentionally contain:

```text
search_bounds       = null
certified_relations = null
stability           = null
```

Therefore D1 MUST NOT reinterpret q5/q50/q200 numeric observations as certified alpha-beta values or create a teacher softmax from them. No missing horizon may be backfilled from the B3 full-ladder audit.

The only decision target used by D1 is the already-authenticated **single action selected by the frozen real B3 teacher**. This yields a listwise categorical loss over the complete legal sibling set without fabricating numeric teacher values.

A later separately preregistered experiment may use score-softmax or certified pairwise relations only after the corresponding bound/certification contract exists.

## 4. Frozen WDL side

Both arms consume the same frozen CURRENT_2M training population and target already used by the established PatternEval continuation line.

### CURRENT source

```text
TURNOVER source job     home-0977-l3-pure-turnover1to1-train-v1
TURNOVER attempt        20260726T071254Z-336bb984
TURNOVER JNNW SHA256    9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d
TURNOVER JSM SHA256     acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682
CURRENT records         2000000
holdout split seed      577215
holdout mod             10
```

The split MUST reproduce the archived `current_2m-manifest.json` from:

```text
cpx62-1340-jass-megacorpus-comparative-fit-v1
attempt 20260814T123246Z-2ce07222
code    2ce07222f86c1468a1081fbdc53e9e17a0c5326e
```

### Frozen WDL target

Both arms consume the exact archived:

```text
current_2m-context30.npy.gz
```

from the same cpx62-1340 result. No WDL/Context target is regenerated.

### Common prior

Both arms use the production champion as the same Gaussian prior centre:

```text
CURRICULUM source   cpx62-1341-jass-megacorpus-arm-d-fit-v1
attempt             20260814T191555Z-18c38a33
artifact            D-c-prior-then-current.pjtw.gz
raw PJTW SHA256     319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

## 5. Frozen model class and common optimizer

Both arms use exactly the same production static class:

```text
8cf 12-square pattern geometry
exact rot180 + colour-swap fold
120 production extras
tempo-stage MG/EG interpolation
PJTW v3
```

The common WDL fit recipe is frozen to the already-used CURRENT continuation settings:

```text
target                = external (archived Context30 probability)
chunk                 = 20000
fold                  = exact
prune                 = true
l2                    = 1e-5
prior_mean            = CURRICULUM
prior_decay           = 0.0
loss                   = logistic
max_iter              = 2000
lbfgs_maxcor           = 20
lbfgs_gtol             = 1e-4
phase                  = tempo-stage
```

Both arms start from the same projected CURRICULUM prior and use the same feature dump, parameterization, pruning map, train rows and holdout rows.

## 6. D1 treatment

Exactly two full fits are allowed.

### Arm A — WDL_CONTROL

Objective:

```text
L_A(theta) = mean_CURRENT_train L_WDL(theta) + L2_prior(theta; CURRICULUM)
```

### Arm B — WDL_LISTWISE

Objective:

```text
L_B(theta) = mean_CURRENT_train L_WDL(theta)
           + lambda_decision * mean_C_train L_selected_action(theta)
           + L2_prior(theta; CURRICULUM)
```

Frozen treatment weight:

```text
lambda_decision = 1.0
```

There is no lambda sweep and no temperature parameter in D1.

## 7. Selected-action listwise loss

For each C training parent `s` with legal actions `a_1..a_k`, exactly one action is marked `selected=true` by the authenticated real B3 teacher.

Let `z_black(child)` be the raw black-POV linear PatternEval logit before PJTW quantization. Define the parent-POV action logit:

```text
q_theta(s,a) = +z_black(child(s,a))  if parent stm = black
             = -z_black(child(s,a))  if parent stm = white
```

Then:

```text
p_theta(a|s) = softmax_a q_theta(s,a)
L_selected_action(s) = -log p_theta(a_selected|s)
```

Every parent has equal weight irrespective of legal-action count, phase, node cost, exactness, survivor count or B3 audit outcome.

D1 uses:

```text
C train = 3200 parents
C valid =  400 parents (readout only)
C test  =  400 parents (terminal readout only)
```

No C valid/test parent contributes gradient, early stopping, hyperparameter choice or candidate selection.

The D1 loss consumes only action identity, child position, parent stm and `selected`. q5/q50/q200 numeric scores, elapsed times, survivor margins and B3 full-ladder diagnostics are not loss inputs.

## 8. Convexity / one-factor requirement

For the linear PatternEval parameterization, the selected-action term is multinomial logistic cross-entropy (log-sum-exp minus selected logit), hence convex. Combined with the existing WDL logistic loss and positive quadratic prior, D1 remains a convex/strongly-convex continuation problem on the active parameter subspace.

The normalized science commands for A/B must be byte-identical after replacing only:

```text
arm/output name
lambda_decision: 0.0 vs 1.0
C decision dataset enabled: false vs true
```

No other treatment difference is allowed.

## 9. Terminal offline readout

Before either fit executes, the implementation must freeze a deterministic terminal readout.

On CURRENT holdout, publish for each arm:

```text
WDL log-loss
Brier score
prediction mean / calibration summary
```

On C valid and C test, publish parent-equal:

```text
selected-action listwise cross-entropy
selected-action top-1 agreement
top-2 containment
mean selected-action probability
phase/stm cell breakdown
```

Also publish parameter displacement from CURRICULUM and A-vs-B fit/optimizer health.

The C **test** partition is read exactly once by the terminal D1 readout after both model bytes are sealed.

## 10. Frozen transfer verdict

The primary paired test is per-parent test-set selected-action cross-entropy.

Compute a deterministic 200,000-replication parent bootstrap with seed:

```text
2026110901
```

for:

```text
delta_decision = CE_A - CE_B
```

Positive means WDL_LISTWISE is better.

WDL non-inferiority is measured as:

```text
delta_wdl = holdout_logloss_B - holdout_logloss_A
```

with frozen tolerance:

```text
delta_wdl <= 0.002000
```

D1 terminal outcomes:

```text
D1_DECISION_TRANSFER_ESTABLISHED_V1
D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1
D1_INVALID_V1
```

`D1_DECISION_TRANSFER_ESTABLISHED_V1` requires all of:

```text
bootstrap LCB95(delta_decision) > 0
selected-action top1_B >= selected-action top1_A on C test
delta_wdl <= 0.002000
all fit/input/split/optimizer contracts valid
```

`NOT_ESTABLISHED` is a scientific STOP for this frozen D1 treatment. It does not authorize lambda tuning, temperature tuning, score-softmax substitution, data dropping or relabeling.

`INVALID` is reserved for technical/provenance/contract failure.

## 11. Authorization boundary

If and only if D1 establishes transfer, the terminal publication may authorize a **separately preregistered equal-node causal strength gate** for Arm B.

D1 never authorizes automatically:

```text
equal-node games
equal-time games
promotion
bake
champion replacement
```

If D1 does not establish transfer, CURRICULUM remains unchanged and the campaign stops at D1 pending a new scientific proposal.

## 12. Explicit exclusions

D1 excludes:

```text
Fisher/JFI anchoring
JFI-coordinate penalties
lambda sweeps
temperature sweeps
new self-play
new teacher search
full-ladder backfill
q200 softmax targets
feature/model search
new architecture
strength games
promotion/bake
```

Fisher-aware anchoring remains a separate later factor and requires its own authenticated JFI prerequisite and preregistration.

## 13. Execution order

```text
D1 implementation + synthetic/native objective tests
 -> input/authentication preflight
 -> exactly two frozen fits A/B
 -> seal both model bytes
 -> terminal CURRENT-holdout + C-test readout
 -> D1 verdict
 -> STOP
```
