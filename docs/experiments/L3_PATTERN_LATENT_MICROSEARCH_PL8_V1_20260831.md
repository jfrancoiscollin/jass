# L3 PatternLatent-8 (PL8) — micro-search → cheap nonlinear PatternEval residual — preregistration v1

Date: 2026-08-31
Status: PREREGISTRATION ONLY. No PL8 fit, fresh deep holdout or strength game is authorized by the existence/merge of this document alone.

## 0. Scientific boundary

This is a new hypothesis generated **after** the terminal failures of the linear micro-search→PatternEval projection and of T3-A/F6 runtime transfer. It is therefore treated as a new experiment with a new fresh confirmation cohort.

The experiment tests exactly one architecture, `PL8`, with no architecture sweep, hidden-width sweep, temperature sweep, seed ensemble, feature-family selection, post-hoc phase tuning or retry with altered science.

Forbidden throughout this protocol:

- no F6, D1, Rich-D or micro-search at inference;
- no self-play compounding loop;
- no change to generic search, movegen, qsearch, pruning, ordering, TT or EGDB semantics;
- no retune/refit of T3-A or CURRICULUM;
- no use of M2/M5/F6/E2 fresh labels for PL8 fitting or hyperparameter selection;
- no automatic bake/promotion;
- no strength run before a separate post-transfer runtime preflight and explicit post-facts JFC GO.

Technical failures may be repaired with versioned code/jobs only if every scientific parameter below remains byte-for-byte/semantically unchanged.

## 1. Immutable upstream

### 1.1 Production baseline

`CURRICULUM` remains production champion.

```text
CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

### 1.2 Micro-search teacher is already established

Fresh M2 terminal:

```text
job     = cpx62-1598-l3-micro-search-m2-teacher-readout-v5
attempt = 20260827T160634Z-f6f96f42
verdict = MICRO_SEARCH_TEACHER_SIGNAL_ESTABLISHED
B*      = 1000 exact nodes / child
```

On the M2 fresh cohort:

```text
D1 pairwise       = 0.7282156110178234
micro1000 pairwise= 0.9350705214988644
micro1000 top-hit = 0.855790918897715
q5k pairwise      = 0.9568372335248535
q5k top-hit       = 0.8946994213984505
micro1000-D1 pairwise CI95 = [0.199982371710083 ; 0.2137252377015537]
micro1000-D1 top-hit  CI95 = [0.19633225458468176 ; 0.2290379523389232]
```

Therefore the short-search teacher signal is not reopened by PL8.

### 1.3 Frozen fit corpus available

M3 teacher/design:

```text
job     = cpx62-1607-l3-micro-search-m3-teacher-design-v6
attempt = 20260828T034908Z-458e74bf
verdict = MICRO_SEARCH_M3_TEACHER_DESIGN_READY
parents = 100000 (25000 / phase)
siblings= 928639
teacher = exact 1000-node CURRICULUM micro-search
```

The exact M3 artifacts may be reused as **training data only**. M3 contains no q50/q200/WDL source labels for the fit and no deep confirmation scores.

### 1.4 Linear projection failed at fresh M5

M4 produced one full linear PatternEval T1, then M5 fresh deep confirmation terminated:

```text
job     = cpx62-1610-l3-micro-search-m5-deep-transfer-v1
attempt = 20260828T062835Z-0bcf5e88
verdict = MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED
```

Fresh M5:

```text
T0 pairwise = 0.6002059979720586
T1 pairwise = 0.6025015119991486
delta pairwise mean = +0.00229551402708994
pairwise CI95 = [+0.0011948080533710711 ; +0.003375539622420759]

delta top-hit mean = +0.00021910604732690623
top-hit CI95 = [-0.003164865128055312 ; +0.0036274223390787806]

P0 pairwise delta = -0.0017280072795350517
P1 = +0.0018482973660095396
P2 = +0.0037323638388122153
P3 = +0.006513026966090082
```

M5 labels/rows are permanently **holdout-consumed** and MUST NOT be read by PL8 fit, standardisation, shrink, architecture choice or optimizer diagnostics. Only these already-published aggregate terminal facts motivate the new hypothesis.

### 1.5 F6 branch is closed independently

E2 terminal metrics (`1714/1715/1716`) establish `E2_F6_INFORMATION_VALUE_NOT_ESTABLISHED`, with `delta_info=-65.375148015 Elo`, CI95 `[-89.821293148 ; -40.233502863]`; E3-F6 is closed. PL8 uses zero F6 feature/label.

## 2. Hypothesis

The established 1000-node teacher carries large decision information, but the previous projection was constrained to a single globally additive PatternEval scalar. The hypothesis is that the remaining transfer bottleneck is **interaction structure among already-cheap production PatternEval signals**, not absence of teacher information.

PL8 therefore keeps the exact CURRICULUM table lookup as base and adds one tiny nonlinear residual whose inputs are derived only from the already-computed/cheap static PatternEval representation.

The experiment is falsified if this fixed nonlinear bottleneck does not improve both fresh deep pairwise and fresh deep top-hit under the gates below.

## 3. Frozen runtime representation: PL8

### 3.1 Canonical POV

The residual input is canonicalised to side-to-move Black:

- if the input position has Black to move, use it unchanged;
- if White to move, apply the exact project-standard `rotate180 + colour-swap` board transform and set STM=Black;
- preserve all position information needed by the static evaluator; no search/history feature may enter PL8.

This makes the PL8 residual intrinsically STM-POV and enforces colour/rotation symmetry by construction.

### 3.2 Exact input vector (138 scalars)

Using byte-identical CURRICULUM and the exact production 8cf/120-extra architecture, form exactly:

1. **16 pattern-table scalars**: for each of the 8 active pattern buckets, the CURRICULUM `{mg,eg}` weight pair before phase interpolation, converted to cp units as `100 * weight / scale`, ordered pattern0_mg, pattern0_eg, ..., pattern7_mg, pattern7_eg;
2. **120 raw production dense extras** from `scan_eval::compute_extras()` on the canonical position, in the exact production order;
3. **1 production phase scalar** `phase_wmg` using the exact CURRICULUM tempo-stage contract;
4. **1 base scalar** `T0_cp`, the byte-identical CURRICULUM integer score of the original position in STM POV.

Total width = `16 + 120 + 1 + 1 = 138`.

No legal-move generation, F6 extraction, micro-search, D/D1/Rich-D, qscore, WDL, sibling count or teacher-side metadata is an input.

### 3.3 Target-free standardisation

Means and population standard deviations are computed exactly once over **all M3 training children**, in original M3 row order, before using teacher values in the optimizer.

For feature `j`:

```text
mu_j = mean(x_j)
sigma_j = sqrt(mean(x_j^2) - mu_j^2)
if sigma_j < 1e-6: sigma_j = 1
xhat_j = (x_j - mu_j) / sigma_j
```

The `(mu,sigma)` arrays are frozen into the PL8 artifact and cannot be recomputed from any confirmation/force cohort.

### 3.4 Nonlinear bottleneck — exactly one architecture

Exactly one hidden layer with eight latent units:

```text
z = tanh(W1 * xhat + b1)            # z width 8
residual_raw = dot(w2, z) + b2
score_pre_round = T0_cp + s * residual_raw
score_PL8 = clamp(llround(score_pre_round), -20000, +20000)
```

Shapes:

```text
W1: 8 x 138
b1: 8
w2: 8
b2: 1
```

Total learned head parameters = `1121`.

There is no second hidden layer, dropout, batch norm, attention, embedding table, mixture-of-experts, phase-specific network or residual feature selector.

The CURRICULUM bytes are not modified. The final candidate is a wrapper containing the exact CURRICULUM identity plus PL8 standardisation/head parameters and shrink scalar `s`.

## 4. Fit objective — M3 only

### 4.1 Teacher and student utilities

For each M3 parent with legal children `i`:

```text
u_i = - micro1000_score(child_i)     # parent POV teacher utility
v_i = - PL8_score(child_i)           # parent POV student utility
```

Exact terminal/TB precedence already frozen in the M3 micro-search teacher remains unchanged.

### 4.2 Listwise target

Use a single fixed softmax temperature of **100 cp** (one man-equivalent unit; no sweep):

```text
q_i = softmax(u_i / 100)
p_i = softmax(v_i / 100)
L_parent = -sum_i q_i * log(p_i)
```

This is deliberately listwise rather than the old top-vs-rest independent pairwise logistic objective.

### 4.3 Phase/colour balance

Parents are partitioned into the 8 strata `P0..P3 x {Black,White}` using the frozen parent phase and parent STM. Each stratum contributes exactly `1/8` of the data term; each parent within a stratum has equal weight.

This weighting is frozen before PL8 results and cannot be altered after observing any fit/holdout metric.

### 4.4 Regularisation and optimizer

Data loss plus one fixed head L2:

```text
L = balanced_listwise_CE + 1e-5 * (||W1||^2 + ||w2||^2)
```

Biases are not L2-penalised.

Initialization is single-seed deterministic NumPy PCG64, seed `2026103101`, Xavier-uniform separately for `W1` and `w2`; biases zero.

Optimizer: deterministic full-batch L-BFGS-B, `maxiter=300`, `maxcor=10`, `gtol=1e-6`, `ftol=1e-12`. No validation-set model selection and no seed retry. Convergence failure without a purely technical bug gives `PL8_FIT_TECHNICAL_FAILED`; it does not authorize optimizer retuning.

Exactly **one** PL8 fit is allowed under v1.

## 5. Target-blind anchor shrink

After the one fit, select exactly `500000` target-blind states using seed `2026103102`, excluding all M1/M2/M3/M5, DSSD/Rich-D, T3/F6/E2 and published force cohorts. No micro/deep/search/WDL label may be read.

After serialize/reload, choose the largest `s in [0,1]` by exactly 30 deterministic bisection iterations satisfying both inherited safety guards:

```text
RMS |PL8 - T0| <= 12 cp
p99 |PL8 - T0| <= 35 cp
```

The anchor is not a scientific confirmation set. It only freezes a safe residual amplitude. No alternative drift guard is allowed after results.

## 6. Fresh deep transfer confirmation

### 6.1 Fresh cohort

Before any PL8/deep metric, generate/select exactly `8000` new target-blind CURRICULUM parents:

```text
2000 P0 (30..40 pieces)
2000 P1 (20..29)
2000 P2 (12..19)
2000 P3 (9..11)
2..16 legal moves
selection_seed = 2026103120
```

Deduplicate exact board+STM and rotate180+colour-swap identity. Exclude all previously published teacher/fit/confirmation/force/F6/E2 identities, including M2/M3/M5.

### 6.2 Deep-label contract

For every sibling, from fresh engine/TT state, byte-identical CURRICULUM, book OFF, one thread:

```text
1000 nodes   diagnostic only
50000 nodes  stability screen
200000 nodes deep target
```

Stable-pair rule remains the previously established DSSD/micro-search contract:

- exact terminal/TB precedence;
- otherwise same sign at 50k and 200k;
- both nonzero;
- `|d50| >= 10 cp`;
- `|d200| >= 30 cp`;
- target relation = 200k parent-POV ranking.

The 1000-node diagnostic cannot rescue a failing PL8 deep-transfer gate.

### 6.3 Support gates

Before candidate metrics:

```text
selected parents = 8000
accepted parents >= 6000
accepted each phase >= 1200
accepted each parent colour >= 2400
```

Failure gives `PL8_FRESH_SUPPORT_NOT_ESTABLISHED` and STOP.

### 6.4 Primary bootstrap

Parent-cluster bootstrap `200000` samples, seed `2026103121`.

Publish T0, frozen old linear T1 (diagnostic only), and PL8 pairwise/top-hit; PL8-T0 deltas globally, by phase and by parent colour; micro1000 agreement; ties; saturation; serialize/reload equality.

### 6.5 Transfer verdict

`PL8_DEEP_TRANSFER_ESTABLISHED` iff ALL:

1. PL8-T0 pairwise CI95 lower bound > 0;
2. PL8-T0 top-hit CI95 lower bound > 0;
3. PL8-T0 pairwise point delta > 0 in every P0/P1/P2/P3;
4. PL8-T0 top-hit point delta >= 0 in every P0/P1/P2/P3;
5. PL8-T0 pairwise point delta > 0 for both parent colours;
6. anchor guards survive serialize/reload;
7. runtime PL8 scoring reads no micro-search, D/D1/Rich-D, F6 or deep label.

Otherwise, with healthy support/harness:

```text
PL8_DEEP_TRANSFER_NOT_ESTABLISHED
```

No refit, temperature/width change, phase reweighting or seed retry is authorized after this holdout.

The old linear M4 T1 is diagnostic only and cannot rescue PL8.

## 7. Runtime technical characterization after transfer PASS

Only if `PL8_DEEP_TRANSFER_ESTABLISHED`:

- CPX62 target-native build;
- 128 fresh/consumed technical roots, 32/phase, no strength result;
- depth-9 alternating T0/PL8 and exact 20k-node searches;
- threads=1, book OFF, Q00/search contract unchanged;
- publish leaf eval ns, NPS, wall, nodes/eval-calls, effective depth, and score/search determinism;
- verify no cross-host binary reuse and publish executable SHA, CPU/ISA/nproc/disk.

This characterization has no force verdict. It exists to size the actual strength run and to publish a measured comparable rate/ETA.

## 8. Strength protocol — frozen now, separate post-facts GO

A strength run is authorized only if deep transfer PASS **and** the runtime preflight is technically healthy **and** a distinct explicit post-facts JFC GO is given after machine/rate/ETA/disk facts are published.

### Pool1

```text
contrast = PL8 vs byte-identical CURRICULUM
fresh openings = 3000
paired reversed colours = 6000 games
PRIMARY = native 0.1 s/move
threads = 1
book = OFF
force seed = 2026103130
paired bootstrap = 200000, seed 2026103131
```

No teacher/D/F6/micro-search is present at inference.

If Pool1 PL8 point score `<= 0.5`:

```text
PL8_STRENGTH_NOT_SUPPORTED
```

and STOP.

If Pool1 point `>0.5`, exactly one unchanged Pool2 is allowed:

```text
fresh seed = 2026103140
6000 games
bootstrap seed = 2026103141
chained Pool1+Pool2 bootstrap seed = 2026103149
```

Final `PL8_STRENGTH_SUPPORTED` requires:

- PL8 point >0.5 in both pools;
- chained paired-bootstrap CI95 lower bound >0.5;
- byte-identical PL8/T0 artifacts across pools;
- no technical asymmetry or skipped games.

Both pools positive but chained low <=0.5 => `PL8_STRENGTH_INCONCLUSIVE`. Pool2 non-positive => `PL8_STRENGTH_NOT_SUPPORTED`.

No automatic promotion/bake follows any PL8 strength verdict.

## 9. Execution / GO boundaries

Merge of this preregistration is not a compute GO.

### Boundary A — implementation + preflight (allowed after merge, no scientific result)

May implement PL8, tests, exact input extraction, serializer, fit tool, fresh-selector/deep-readout tooling, and run technical CPX62 preflight/sizers on consumed data. Must publish machine facts, build/ISA, fit-iteration rate/ETA, deep-label rate/ETA, disk and runtime-eval cost estimate. No PL8 fit and no fresh confirmation labels before the post-facts GO.

### Boundary B — one PL8 fit + fresh deep confirmation

Requires one distinct explicit JFC GO **after Boundary-A facts**. That GO authorizes the single frozen M3 fit, anchor shrink and automatic fresh 8000-parent deep confirmation. No intermediate science change/GO is needed between fit and holdout.

### Boundary C — force

Only after transfer PASS and runtime preflight facts. Requires a new distinct post-facts JFC GO. Pool2, if Pool1 point >0.5, is already preregistered and may run automatically under that same force GO.

## 10. Terminal verdicts

```text
PL8_FIT_TECHNICAL_FAILED
PL8_FRESH_SUPPORT_NOT_ESTABLISHED
PL8_DEEP_TRANSFER_ESTABLISHED
PL8_DEEP_TRANSFER_NOT_ESTABLISHED
PL8_RUNTIME_TECHNICAL_FAILED
PL8_STRENGTH_NOT_SUPPORTED
PL8_STRENGTH_INCONCLUSIVE
PL8_STRENGTH_SUPPORTED
```

Every result must publish exact job/attempt/code/model/input identities, seeds, volume, support, bootstrap contract, runtime authority flags and `promotion=false` / `bake=false`.
