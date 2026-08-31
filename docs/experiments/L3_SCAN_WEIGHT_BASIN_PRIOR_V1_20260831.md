# L3 Scan-weight basin prior (SB1) — preregistration v1

Date: 2026-08-31

Status: **PREREGISTRATION ONLY**. Merge is not a compute GO. No new fit, fresh strength pool, bake or promotion is authorized by this document alone.

## 0. Scientific question

Jass has already tested and largely falsified two broad explanations for the remaining evaluation gap:

1. **insufficient PatternEval capacity** — the exact 8cf fold has the same effective pattern degrees of freedom as Scan and itself produced a large causal gain;
2. **insufficient self-play volume alone** — MegaCorpus and later horizontal multi-seed work did not establish a gain from simply adding more of the same self-play distribution.

A third explanation remains directly testable and has not been isolated:

> the self-referential continuation prior used by the Jass lineage may keep the optimizer in a Jass-specific weight basin, even though the same 8cf function class can represent a much stronger Scan-like solution.

SB1 tests exactly this hypothesis. It changes **only the prior centre / starting basin** of one otherwise identical refit.

## 1. Immutable evidence motivating SB1

### 1.1 Exact-fold closed the gross architecture mismatch

`L3_EXACT_FOLD_20260801.md` established that the eight Jass top/bottom bands are the duplicated representation of Scan's four signed pattern tables. `--exact-fold` imposes the exact `rot180 + colour-swap` relation and reduces the effective pattern space to the Scan-sized class.

Historical causal result:

```text
EXACT vs CONTROL
n = 6000
score = 0.5246
Elo = +17.10
CI95 = [+9.2 ; +25.0]
```

No new capacity or data was added by that intervention.

### 1.2 Exact Scan weights are exploitable by the repaired Jass engine

`home-0957-l3-pure-m1-scan-gap-causal-v1` algebraically ported the frozen Scan 3.1 `data/eval` into Jass PJTW and established **static equality on 600/600 positions, max absolute difference 0**.

Before the later legality repair, identical Scan weights inside Jass converted only ~38–43% on the corrected conversion gauge while native Scan converted 100%.

`home-0961ter-l3-pure-m1-legality-root-order-causal-v1` then repaired the Jass legality/termination defect and, with the same exact Scan weights, obtained:

```text
p3_mince = 297 / 300 wins = 99.00%
p4_egal  = 294 / 300 wins = 98.00%
```

The prior values had been ~38.00% and ~35.33%. Therefore the Scan weight solution is not merely strong in Scan's own search: **the repaired Jass engine can exploit it directly**.

### 1.3 MegaCorpus did not establish a volume effect

The MegaCorpus A/B/C/D campaign held the 8cf/exact-fold fit architecture fixed while changing corpus source/volume/curriculum. Its high-N readout did not establish D>A or D>C. A later attribution found CURRENT+Context30 statistically indistinguishable from the curriculum arm, with the MegaCorpus stage contributing no measurable gain.

Therefore SB1 does **not** regenerate a giant WDL corpus and does not reopen MegaCorpus.

### 1.4 F6 and PL8 are separate

The F6 branch is terminal negative (`E2_F6_INFORMATION_VALUE_NOT_ESTABLISHED`, `delta_info=-65.375... Elo`, CI95 entirely below zero).

PL8 remains frozen before its first scientific fit. SB1 consumes no PL8 fresh cohort, label or force pool and does not reinterpret PL8.

## 2. Frozen artifacts

### 2.1 Production champion

```text
CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

Source:

```text
cpx62-1341-jass-megacorpus-arm-d-fit-v1
attempt 20260814T191555Z-18c38a33
artefact D-c-prior-then-current.pjtw.gz
```

### 2.2 Frozen CURRENT training corpus and target

Use the exact CURRENT_2M source/split already consumed by the MegaCorpus campaign:

```text
TURNOVER source:
home-0977-l3-pure-turnover1to1-train-v1
attempt 20260726T071254Z-336bb984

CURRENT split:
records = 2,000,000
holdout split seed = 577215
```

The target sidecar MUST be the exact archived `current_2m-context30.npy.gz` from:

```text
cpx62-1340-jass-megacorpus-comparative-fit-v1
attempt = 20260814T123246Z-2ce07222
code    = 2ce07222f86c1468a1081fbdc53e9e17a0c5326e
```

No target is regenerated or altered in SB1.

### 2.3 Jass continuation prior C

Control prior is the certified `MEGA_FULL_4M` / arm-C PJTW published by `cpx62-1340`. Its raw SHA256 MUST be read from and match that job's immutable `JASS_CONTROL_SUMMARY.json` before fitting.

### 2.4 Scan prior

Intervention prior is the exact Scan 3.1 port already authenticated by:

```text
home-0957-l3-pure-m1-scan-gap-causal-v1
attempt = 20260725T104131Z-ebf919fe
```

Input Scan eval identity:

```text
Scan data/eval SHA256 = 0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba
```

SB1 MUST either fetch the immutable `scan-exact-8cf.pjtw.gz` from 0957 or deterministically recreate it with the already-versioned `jobs/tools/scan_exact_eval_port.py`, then authenticate exact static parity before use.

The port maps Scan's own feature weights exactly; Jass-only optional extra coefficients absent from Scan remain zero in the prior. This is part of the frozen treatment and MUST NOT be hand-filled or tuned.

## 3. Architecture and runtime are unchanged

Both fit arms use exactly the production static function class:

- 8cf 12-square ternary men patterns;
- exact `rot180 + colour-swap` fold;
- 120 production extras;
- tempo-stage MG/EG interpolation;
- same PJTW v3 format;
- same production search, qsearch, movegen, TT, EGDB and score convention.

No PL8 head, F6, D/D1/Rich-D, NNUE, FM term, new feature, search label or micro-search input is permitted.

## 4. One-factor fit experiment

Exactly two fits are allowed.

### Arm A — `SELF_BASIN`

Fit CURRENT_2M using arm C as prior centre.

### Arm B — `SCAN_BASIN`

Fit the **same rows in the same order** using `SCAN_EXACT` as prior centre.

Everything else is byte-for-byte/semantically identical:

```text
target             = archived CURRENT_2M Context30 sidecar
loss               = logistic
fold               = exact
phase              = tempo-stage
prior_decay        = 0
l2                 = 1e-5
max_iter           = 2000
lbfgs_maxcor        = 20
lbfgs_gtol          = 1e-4
chunk               = 20000
prune               = ON
numeric runtime     = identical between A/B
feature dump        = one shared dump
row order           = identical
```

No hyperparameter, data, target, phase, fold, seed, optimizer or architecture sweep is allowed.

The treatment is explicitly **the prior basin as a whole**: the prior centre and whatever deterministic optimizer initialization the certified trainer derives from that prior. SB1 does not attempt to decompose initialization versus regularization. If the treatment works, such decomposition requires a new preregistration.

## 5. Pre-fit read-only audit

Before any fit, a read-only audit may compare `C`, `CURRICULUM` and `SCAN_EXACT` in common PJTW coordinates and on the already-consumed CURRENT feature dump.

Publish, without any gate or tuning:

- family-wise parameter RMS and correlation for pattern MG/EG and dense MG/EG;
- visit-weighted pattern correlation by CURRENT bucket-frequency quantile;
- score correlation and RMS difference on consumed CURRENT holdout rows;
- decomposition of `SCAN_EXACT - C` score variance into patterns versus dense extras;
- nonzero/saturation/scale diagnostics;
- raw identities and SHAs.

These diagnostics cannot cancel, alter or retune the frozen A/B experiment. They are explanatory only.

## 6. Fit validity and technical terminals

Both optimizers must satisfy the same convergence verification used by the current champion recipe. Any one-sided runtime, missing artifact, target drift, row-order drift, feature-layout mismatch, nonfinite value, failed exact symmetry, or optimizer failure gives:

```text
SB1_TECHNICAL_FAILED
```

and STOP. Technical implementation faults may be repaired and requeued only if all frozen scientific fields above remain unchanged.

The fit output itself is not selected by holdout loss. Historical Jass evidence shows holdout CE is not a reliable force oracle.

After both healthy fits, publish parameter distance `A↔B`, prediction distance, holdout CE and conversion-gauge diagnostics, but **none is a strength verdict**.

## 7. Strength protocol — primary causal contrast B vs A

Strength is not authorized until both fits are healthy, a same-machine runtime preflight publishes nproc/ISA/disk/rate/ETA/timeouts, and JFC gives a distinct explicit post-facts GO.

### Pool 1

Fresh target-blind openings, disjoint from every published force pool.

```text
openings             = 3000
paired reversed side = yes
primary view          = native 0.1 s/move
secondary view        = Q00 depth 9
threads               = 1
book                  = OFF
EGDB                   = production contract
seed openings          = 2026110101
paired bootstrap       = 200000
bootstrap seed         = 2026110102
```

Each view therefore has 6000 games. Same executable, search parameters, openings and scheduling for A and B.

Primary causal verdict:

```text
SB1_SCAN_BASIN_ESTABLISHED
```

iff ALL are true:

1. native B score CI95 lower bound > 0.5;
2. Q00 B score point estimate > 0.5;
3. zero skipped/asymmetric games;
4. A/B target, data, architecture and optimizer contracts authenticated identical except prior basin;
5. no runtime Scan/search teacher or external evaluator is present during games.

Otherwise, with a healthy harness:

```text
SB1_SCAN_BASIN_NOT_ESTABLISHED
```

No threshold may be changed after seeing Pool 1.

## 8. Replication / champion comparison

If and only if `SB1_SCAN_BASIN_ESTABLISHED`, exactly one subsequent preregistered continuation is opened: compare frozen `SCAN_BASIN` directly with byte-identical production `CURRICULUM` on a new disjoint pool.

SB1 itself does **not** promote or bake the candidate and does not automatically run that continuation.

If Pool 1 fails, the Scan-prior hypothesis is closed for this exact recipe. No retry with another L2, target alpha, corpus, Scan/Jass blend, optimizer seed or partial family prior is authorized under v1.

## 9. Authorization boundaries

### Boundary A — after merge

Allowed without another scientific GO:

- implementation and tests;
- read-only prior/weight audit on consumed data;
- exact Scan-port authentication;
- CPX62/HOME technical fit sizer on a bounded consumed subset without running either full fit;
- machine/ISA/disk/rate/ETA publication.

Forbidden:

- either full A/B fit;
- any fresh strength opening;
- any strength game.

After Boundary-A facts are published, require distinct:

```text
GO SB1 FIT
```

### Boundary B — after healthy A/B fits

Allowed: technical runtime characterization/sizing only.

Before Pool 1 require distinct post-facts:

```text
GO SB1 FORCE
```

Advance authorization given before those facts does not satisfy either boundary.

## 10. Interpretation

SB1 is designed to answer one narrow question:

> Does the same Jass training objective converge to a stronger solution when its continuation prior is centred on the already-proven Scan weight basin rather than the Jass lineage basin?

A positive result would not prove that Scan's unpublished training recipe is recovered. It would establish that **weight-basin information**, not missing nonlinear capacity or more self-play volume, is causally useful under the current Jass objective.

A negative result would be equally informative: it would show that simply starting/regularizing toward Scan is erased or made unhelpful by the current Jass objective, moving the remaining search toward the target/loss/distribution semantics rather than model capacity.
