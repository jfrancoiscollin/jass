# Jass-native fit identifiability & active learning (JFI) — preregistration draft v1

Date: 2026-09-01
Status: **DRAFT / PREREGISTRATION ONLY**. Merge is not a compute GO.

## 0. Goal

Build a stronger PatternEval **without depending on Scan** by learning how to control Jass' own optimization, regularization and data acquisition.

The Scan result is a historical positive control only: it proved that the current PatternEval class can represent a substantially stronger solution. It is not an acceptable production prior for this program.

The desired reproducibility contract is:

> Jass engine + Jass data + Jass learning rule + frozen Jass seeds.

## 1. Immutable starting evidence

Production champion:

```text
CURRICULUM SHA256
319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

SB1 terminal source:

```text
cpx62-1743-l3-sb1-scan-basin-force-pool1-recovery-v10
attempt 20260901T173344Z-e05fb469
Jass code e05fb4691bfe4877f7139c69be603c0d659f1ade
```

Readout:

```text
cpx62-1745-l3-sb1-terminal-readout-publish-v2
attempt 20260901T194028Z-e05fb469
verdict SB1_SCAN_BASIN_ESTABLISHED
```

Native 0.1 s/move, B=SCAN_BASIN:

```text
W/D/L = 3090/349/2561
score = 0.5440833333333334
Elo = +30.71
paired CI95 = [0.5351666666666667, 0.553]
P(score > .5) = 1.0
```

Q00 depth 9:

```text
W/D/L = 3156/330/2514
score = 0.5535
Elo = +37.32
paired CI95 = [0.5439166666666667, 0.5630833333333334]
P(score > .5) = 1.0
```

Frozen raw identities:

```text
SCAN_BASIN  b72a892c5f51468a55abe3ec9fd3f576a9a27c728458c271e0d9eee4d33eada8
SELF_BASIN  319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

Crucial observation: `SELF_BASIN` is byte-identical to `CURRICULUM`.

## 2. Correct interpretation of the "basin"

Do not assume a mysterious non-convex local minimum.

The PatternEval fit is logistic regression in the weights with L2/ridge. Under the historical trainer, `--prior-mean P --prior-decay 0 --l2 lambda` makes the L2 term a pull towards P, not towards zero.

The mechanism to test is therefore:

```text
L(w) = L_data(w) + lambda ||w - w_prior||^2
```

SB1 deliberately bundled optimizer initialization and prior center. JFI must separate them.

## 3. Absolute Scan independence

For all JFI scientific jobs and candidate production:

```text
SCAN_WEIGHT_READS = 0
SCAN_SCORE_READS = 0
SCAN_TARGET_READS = 0
```

Forbidden:

- Scan weights as prior or initialization;
- Scan scores as target or feature;
- model/data/hyperparameter selection using Scan;
- Scan-based scientific gate;
- distillation Scan -> Jass;
- promotion of SCAN_BASIN as the JFI solution.

The SB1 result may be cited only as historical motivation / positive control.

## 4. Supersede redundant SB2

PR #751 (`SCAN_BASIN vs CURRICULUM`) became redundant after the 1745 readout established that the SB1 control SHA is exactly CURRICULUM.

Before JFI compute:

- close or clearly mark #751 superseded;
- do not consume a new pool to repeat Scan-vs-CURRICULUM;
- disable any SB2 automation.

## 5. Program overview

```text
JFI-A  initialization x ridge-center decomposition
JFI-B  zero-centered L2 curve + identifiability map
JFI-C  retrospective Jass-only active selection
JFI-D  frozen Jass-native candidate
JFI-E  causal force vs CURRICULUM
```

No PL8, NNUE, FM, new feature search or new vertical self-play loop is part of JFI v1.

---

# JFI-A — separate initialization from ridge center

## 6. Data

Reuse exactly the consumed CURRENT source and archived Context30 target:

```text
CURRENT_2M
home-0977-l3-pure-turnover1to1-train-v1
attempt 20260726T071254Z-336bb984
records = 2,000,000

Context30 target sidecar
cpx62-1340-jass-megacorpus-comparative-fit-v1
attempt 20260814T123246Z-2ce07222
current_2m-context30.npy.gz

holdout split seed = 577215
```

One shared feature dump, identical rows/order for all arms.

## 7. Trainer implementation

Add backward-compatible control of optimizer initialization independently from L2 center.

Suggested interface (exact names may change):

```text
--init-mode legacy|zero|file
--init-file <pjtw>
--prior-mean <pjtw>   # remains historical ridge center
```

Absence of `--prior-mean` means zero-centered L2 as today.

Mandatory invariant:

```text
legacy CLI => historical behavior / serialization unchanged
```

## 8. Frozen 2x2 experiment

At fixed `l2=1e-5`:

| arm | init | L2 center |
|---|---|---|
| A | CURRICULUM | CURRICULUM |
| B | ZERO | CURRICULUM |
| C | CURRICULUM | ZERO |
| D | ZERO | ZERO |

Common contract:

```text
loss = logistic
exact-fold = ON
tempo-stage = ON
prior_decay = 0
l2 = 1e-5
max_iter = 2000
lbfgs_maxcor = 20
lbfgs_gtol = 1e-4
chunk = 20000
prune = ON
same rows/order/targets/features/numeric env
```

No force in JFI-A.

## 9. JFI-A metrics

For every arm publish:

- optimizer success/status, iterations, final objective, gradient inf norm;
- serialized PJTW SHA and exact reload;
- train and holdout CE;
- score/prediction RMS;
- raw and quantized parameter displacement;
- number/fraction of coefficients changed;
- family RMS for pattern MG/EG and dense MG/EG.

Contrasts:

```text
A vs B: init effect at CURRICULUM center
C vs D: init effect at ZERO center
A vs C: center effect at CURRICULUM init
B vs D: center effect at ZERO init
```

### Path-independence gate

If same-center healthy converged fits differ materially, STOP.

Material difference if any:

```text
holdout score RMS > 0.5 cp
OR serialized score max_abs > 2 cp on frozen consumed replay set
OR objective difference incompatible with optimizer tolerance
```

Verdict:

```text
JFI_OPTIMIZER_PATH_DEPENDENCE_DETECTED
```

Diagnose stopping criterion, pruning, numerical conditioning, quantization/statefulness or hidden coupling before proceeding.

Otherwise:

```text
JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED
```

Interpretation: SB1's "basin" is primarily prior/identifiability, not an optimizer local-minimum effect.

---

# JFI-B — choose zero-centered L2 and quantify identifiability

## 10. Frozen L2 grid

Use ZERO init + ZERO center on the same CURRENT_2M/Context30 setup.

Exactly:

```text
l2 in {0, 1e-6, 1e-5, 1e-4}
```

No other point may be added after metrics are read.

The `l2=0` arm is diagnostic-only. It measures the unregularized endpoint but is
not eligible for selection or reuse in JFI-C/D. The one-standard-error rule is
applied only to the strictly positive lambdas. This guarantees that the frozen
lambda used by every downstream information formula is positive.

### L2 selection rule

Use historical Context30 holdout only, clustered by opening/game identity.

Bootstrap:

```text
100000 samples
seed 2026120101
```

One-standard-error rule:

1. find minimum holdout CE;
2. compute its cluster-bootstrap SE;
3. among lambdas within one SE of best CE, select the **largest lambda**.

The selected lambda is frozen for JFI-C/D.

No Elo/force is used to choose lambda.

## 11. Identifiability tool

Add e.g.:

```text
jobs/tools/patterneval_identifiability.py
```

Streaming over the real exact-fold/tempo-stage design.

Minimum per-coordinate outputs:

- visit count;
- squared-design accumulation;
- diagonal Fisher / curvature approximation F_j;
- data gradient magnitude;
- selected L2 precision;
- ratio data_precision / l2_precision.

Classify coordinates:

```text
UNSEEN
PRIOR_DOMINATED
MIXED
DATA_DOMINATED
```

Global outputs:

- unseen / weakly observed / data-dominated fractions;
- Fisher quantiles;
- quantiles of `1/(F_j + lambda)` as posterior-variance proxy;
- effective degrees of freedom approximation:

```text
sum_j F_j/(F_j + lambda)
```

For the diagnostic-only `l2=0` arm, report an UNSEEN coordinate (`F_j=0`) as
infinite posterior-variance proxy and zero effective-df contribution; never
evaluate `0/0`. These conventions are reporting-only and cannot enter model,
lambda or row selection.

- data-gradient norm;
- ridge-gradient norm;
- data/ridge ratio;
- summaries by pattern/dense and MG/EG.

Optional, non-blocking v1 extension: streaming HVP + Lanczos/randomized spectrum + Hutchinson trace. Do not require a dense Hessian.

## 12. Primary JFI hypothesis

A substantial subspace of PatternEval is under-identified by the current Jass corpus, so ridge determines those coordinates. To become prior-independent, Jass must acquire rows that increase information in those coordinates.

This hypothesis must be tested without any Scan read.

---

# JFI-C — retrospective target-blind active selection

## 13. Source universe

Reuse existing Jass-only MegaCorpus/UNIFORM material. Codex must authenticate exact R2 URIs, counts, hashes and game/opening identities from the 1340 campaign and related manifests.

Do not regenerate self-play in JFI-C.

## 14. Split before target read

Frozen seeds:

```text
split seed = 2026120102
selection tie seed = 2026120103
```

Cluster by game/opening; all rows of a cluster stay in one role:

```text
TRAIN_CANDIDATES
DEV_EVAL
```

The selector must not read:

- Context30 target;
- WDL/outcome;
- deep/search score;
- Scan artifact/weights/scores;
- force results.

## 15. Information score v1

With Fisher diagonal F from the base corpus and selected lambda:

```text
leverage_diag(x) = sum_j x_j^2/(F_j + lambda)
```

Use this simple target-blind v1. Do not add `p(1-p)` or another term post hoc.

## 16. Frozen candidate and arms

First freeze an exact 10,000,000-row Jass-only candidate universe by deterministic hash, before target read.

Select:

```text
ACTIVE_2M  = 2,000,000 rows
UNIFORM_2M = 2,000,000 rows
```

ACTIVE selection:

- descending information score;
- canonical exact-state dedup;
- phase balance;
- original parent-colour balance;
- frozen piece-count bins/quotas to prevent monoculture;
- deterministic SHA tie-break.

UNIFORM control:

- same count;
- volume matched;
- stratified on phase, colour, source and piece-count bins;
- same DEV exclusions.

Publish row-ID manifests + SHA before target access.

## 17. Target reconstruction only after selection freeze

Only after ACTIVE/UNIFORM row-ID manifests are immutable, reconstruct/read Context30 using the exact historical recipe and same code path for both arms.

## 18. ACTIVE vs UNIFORM fits

Both arms:

```text
ZERO init
ZERO L2 center
lambda = frozen JFI-B value
exact-fold
tempo-stage
logistic
same optimizer/runtime/row count/split semantics
```

No parent prior. No Scan.

## 19. JFI-C gate

Primary clustered DEV statistic:

```text
DeltaCE = CE_ACTIVE - CE_UNIFORM
```

Bootstrap CI95, 100000 fixed replicates with a preregistered implementation seed.

PASS iff:

```text
CI95_high(DeltaCE) < 0
```

and at least one information diagnostic improves in the predicted direction:

```text
effective_df ACTIVE > UNIFORM
OR fraction DATA_DOMINATED ACTIVE > UNIFORM
OR posterior_variance_proxy ACTIVE < UNIFORM
```

PASS:

```text
JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED
```

Else:

```text
JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED
```

On scientific FAIL: STOP. No force, no post-hoc selector/size/score tweak.

---

# JFI-D — frozen Jass-native candidate

## 20. Candidate construction

Only if JFI-C passes.

Use the exact same active-information algorithm unchanged over all authenticated Jass-only TRAIN-eligible rows.

Freeze:

```text
ACTIVE_4M = 4,000,000 rows
```

Selection is target-blind. Context30 reconstruction happens after row-ID freeze.

Fit:

```text
ZERO init
ZERO L2 center
lambda frozen in JFI-B
exact-fold
tempo-stage
logistic
same frozen optimizer/pruning
```

Candidate name:

```text
JASS_NATIVE_ACTIVE_V1
```

Publish source/row/target/feature manifests and SHAs, convergence, float/serialized weight SHAs, identifiability diagnostics and DEV CE.

No Scan comparison is part of selection.

---

# Compute boundaries

## 21. Boundary A — before JFI-A/B full fits

Allowed before GO: implementation, deterministic tests, source auth, bounded sizer/preflight only.

Publish on CPX62:

```text
code SHA / branch
host / nproc / CPU / ISA AVX2-BMI2-native
free disk + scratch path/free disk
numeric env
CURRENT_2M auth
Context30 auth
feature-dump timing
gradient/iteration rate
projected fit ETA and timeout
FULL_FITS=0
FRESH_OPENINGS=0
STRENGTH_GAMES=0
SCIENTIFIC_DECISION=FALSE
SCAN_WEIGHT_READS=0
SCAN_SCORE_READS=0
```

Then STOP at:

```text
NEXT_BOUNDARY = GO JFI FIT
```

The authorization must be explicit and post-facts.

## 22. Boundary B — before JFI-C heavy active fits

After JFI-A/B publish:

- optimizer path verdict;
- frozen lambda;
- identifiability summary;
- candidate-universe auth;
- selector rate and fit ETA;
- disk/timeouts;
- zero target reads before selection;
- zero Scan reads.

Then STOP at:

```text
NEXT_BOUNDARY = GO JFI ACTIVE
```

## 23. Boundary C — before final force

After JASS_NATIVE_ACTIVE_V1 is frozen, publish same-machine force preflight:

```text
candidate SHA
CURRICULUM SHA
same executable SHA
host/nproc/ISA/disk
native 0.1s consumed-root rate
Q00 d9 rate
shards / parallelism / per-game and view timeout
Pool1 ETA
FRESH_OPENINGS=0
STRENGTH_GAMES=0
SCAN_READS=0
PROMOTION_AUTHORIZED=FALSE
```

Then STOP at:

```text
NEXT_BOUNDARY = GO JFI FORCE
```

---

# JFI-E — final causal force

## 24. Pool1

Only after `GO JFI FORCE`.

```text
JASS_NATIVE_ACTIVE_V1 vs CURRICULUM
3000 fresh target-blind openings
paired reversed colours = 6000 games/view
native 0.1 s/move PRIMARY
Q00 depth9 SECONDARY
threads=1
book=OFF
production EGDB
same executable
maxplies=160
```

Pool must be disjoint from every published force pool, including SB1 1743.

Frozen seeds:

```text
Pool1 opening seed = 2026120110
Pool1 bootstrap seed = 2026120111
bootstrap samples = 200000
```

Pool1 rule:

```text
native <= 0.5 => JFI_JASS_NATIVE_STRENGTH_NOT_SUPPORTED, terminal
native > 0.5  => exactly one unchanged Pool2 authorized
```

Q00 never rescues native.

## 25. Pool2 and chained verdict

```text
Pool2 opening seed = 2026120120
Pool2 bootstrap seed = 2026120121
chained bootstrap = 200000
chained seed = 2026120199
```

Final PASS iff:

```text
Pool1 native > .5
AND Pool2 native > .5
AND chained native CI95 lower > .5
AND zero technical asymmetry
AND candidate/CURRICULUM bytes unchanged
AND same executable contract
AND SCAN_READS=0
```

Verdicts:

```text
JFI_JASS_NATIVE_STRENGTH_ESTABLISHED
JFI_JASS_NATIVE_STRENGTH_INCONCLUSIVE
JFI_JASS_NATIVE_STRENGTH_NOT_SUPPORTED
```

No third pool.

## 26. Promotion

No automatic promotion.

Even on `JFI_JASS_NATIVE_STRENGTH_ESTABLISHED`, STOP and request a separate bake/promotion authorization.

---

# Tests and leakage guards

## 27. Mandatory tests

Trainer:

- legacy prior behavior backward compatible;
- zero/file init;
- init independent of L2 center;
- zero center independent of init;
- same-center convergence replay;
- exact-fold/pruning unchanged;
- serialization replay;
- no hidden zero-center fallback to parent.

Identifiability:

- synthetic logistic system with known Fisher diagonal;
- exact visit/squared-design counts;
- MG/EG weighting;
- exact-fold coordinate mapping;
- effective-df formula;
- feature-only mode reads no target.

Active selector:

- deterministic repeatability;
- canonical dedup;
- exact quotas/strata;
- deterministic tie-break;
- ACTIVE/UNIFORM disjoint from DEV;
- same row count;
- source-manifest auth.

Hard leakage guards: fail if selector opens any Context30, WDL, outcome, score, deep teacher or Scan artifact before row-ID manifest freeze.

## 28. Required machine-readable artifacts

Suggested names:

```text
JFI_A_FACTORIAL_SUMMARY.json
JFI_A_PATH_INDEPENDENCE.json
JFI_B_L2_CURVE.json
JFI_B_IDENTIFIABILITY.json
JFI_B_SELECTED_L2.txt
JFI_C_SELECTION_MANIFEST.json
JFI_C_ACTIVE_VS_UNIFORM.json
JFI_D_CANDIDATE_MANIFEST.json
JFI_FORCE_POOL1.json
JFI_FORCE_POOL2.json
JFI_FORCE_CHAINED.json
JFI_TERMINAL.json
```

Every stage publishes code/source/artifact SHAs, counts, seeds, numeric runtime, forbidden-read counters, fit count, Scan-read counters, strength games and promotion authorization.

## 29. No post-hoc magic

After results are read, do not:

- add/change lambda grid points;
- alter ACTIVE size/quotas/leverage formula;
- change target;
- add parent prior;
- introduce Scan;
- replace a seed/cohort;
- add a third force pool;
- select a variant based on force.

A new idea after readout requires a new preregistration.

## 30. Technical repairs

Technical-only repair/requeue is allowed if frozen scientific fields, seeds and cohorts are unchanged. Always separate `TECHNICAL_FAILED` from a scientific `NOT_ESTABLISHED` verdict.

## 31. Priority

JFI becomes the priority. Do not start large concurrent CPX62 science for PL8, Scan promotion, redundant SB2, new feature search, NNUE/FM or vertical self-play.

## 32. First Codex delivery

Before any full JFI fit:

1. mark/close #751 as superseded;
2. finalize/review this prereg;
3. merge prereg only after CI/review clean;
4. implement init/ridge-center separation + tests;
5. implement identifiability tool and target-blind selector skeleton;
6. implement bounded sizer/preflight;
7. merge implementation only after tests green;
8. run CPX62 Boundary-A preflight **without full fit**;
9. publish facts and stop at:

```text
NEXT_BOUNDARY = GO JFI FIT
```

Do not infer that GO from this draft PR or from any earlier Jass authorization.

## 33. Scientific success criteria

Maximum success:

```text
JFI_JASS_NATIVE_STRENGTH_ESTABLISHED
```

Important intermediate success:

```text
JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED
+
quantitative evidence of a large under-identified subspace
+
JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED
```

The objective is not to copy a strong external solution. It is to make Jass data sufficiently informative that an arbitrary external prior stops being the dominant determinant of the learned weights.
