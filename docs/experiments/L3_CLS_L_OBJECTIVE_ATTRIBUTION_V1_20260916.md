# L3 CLS-L — Learning-objective attribution V1

Date: 2026-09-16. Status: **DRAFT / prospective preregistration; no CLS-L fit is authorized until the CLS-G0 identity tooling preflight is authenticated green and pinned into the machine contract.**

## 1. Why this experiment is now justified

The terminal CLS diagnosis is fixed to:

- job `cpx62-2015-l3-cls-bottleneck-classification-production-v1`;
- attempt `20260916T205944Z-07fb94cc`;
- code `07fb94cc99798e1532abe276c287b7a3b19458ad`;
- launch receipt `779c3123983682e7ff1650286bd57f869bb513c0bc2aa74d0e6f8d5689bb133a`;
- terminal `CLS_DIAGNOSIS_COMPLETE_V1`;
- classification `mixed`;
- supported axes exactly `SEARCH` and `DECISION-EVAL`.

Therefore evaluation is a meaningful actionable lever and the master plan authorizes preregistration of CLS-L. Teacher fidelity remains a training/diagnostic signal, never the terminal strength judge.

Before any fit, the already-merged `L3_CLS_G0_RUNTIME_CATASTROPHE_CONTRACT_V1_20260916` remains binding. Every arm produced here must later pass that exact gate before a strength cohort may be opened.

## 2. Explicit amendment of the one-axis rule

The historical one-axis rule is amended **only** for this causal block:

- exactly one factor is deliberately varied: the data objective;
- exactly three arms are allowed: LOCAL, WDL and MIXED;
- architecture, source rows, train/holdout split, feature bytes, fold, phase representation, parent prior, regularization, optimizer family, iteration cap, pruning, runtime representation and serialization are identical;
- no fourth arm, lambda sweep, target-alpha sweep, corpus change, architecture change, search change or holdout-selected hyperparameter is allowed.

Thus this is still a one-factor causal experiment even though that factor has three preregistered levels. The amendment expires after this attribution block.

## 3. Fixed parent and runtime representation

Immutable direct parent and sentinel:

`CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

Authenticated production source:

- job `cpx62-1341-jass-megacorpus-arm-d-fit-v1`;
- attempt `20260814T191555Z-18c38a33`;
- code `18c38a33ae78c9c2e8e2df62fca266da28dacead`;
- artifact `D-c-prior-then-current.pjtw.gz`.

All three arms remain standard loadable PatternEval `.pjtw` evaluators. No auxiliary runtime head, teacher network, WDL head or search-specific feature is allowed at inference.

## 4. Fixed empirical distribution

CLS-L attributes the **learning objective on one fixed distribution**. It does not yet attribute a new self-play generator.

Raw row source is the authenticated TURNOVER corpus used by the production CURRICULUM path:

- job `home-0977-l3-pure-turnover1to1-train-v1`;
- attempt `20260726T071254Z-336bb984`;
- raw JNNW SHA256 `9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d`;
- raw JSM SHA256 `acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682`.

The exact CURRENT_2M split/CONTEXT_30 sidecar is authenticated from:

- job `cpx62-1340-jass-megacorpus-comparative-fit-v1`;
- attempt `20260814T123246Z-2ce07222`;
- code `2ce07222f86c1468a1081fbdc53e9e17a0c5326e`;
- terminal marker `JASS_MEGACORPUS_ABC_FITS_READY`;
- artifacts `current_2m-manifest.json`, `current_2m-context30.npy.gz`, `current_2m-conditional-targets.json`, and the authenticated raw TURNOVER source receipt.

The split is reproduced from raw TURNOVER with `holdout_mod=10`, seed `577215`; record count must be exactly 2,000,000 and the reproduced manifest must byte-match the 1340 certificate. Train rows precede holdout rows exactly as in the authenticated historical recipe.

No new self-play is generated in CLS-L V1. This removes generator-policy confounding from the objective contrast. Closed-loop teacher/self-play regeneration belongs to CLS-R only after a child earns continuation through runtime/search and strength-at-time gates.

## 5. Common architecture and optimizer contract

All three arms share the exact production-compatible geometry used by the CURRICULUM lineage:

- 8cf pattern geometry;
- exact rot180/colour-swap fold;
- tempo-stage phase representation;
- 120 production extras;
- lossless prune (`prune_min_visits=1`);
- logistic data loss;
- same CURRENT_2M FEAT bytes;
- same train/holdout boundaries;
- prior mean = byte-identical CURRICULUM;
- `prior_decay=0`;
- L2 `1e-5`;
- chunk `20000`;
- L-BFGS max iterations `2000`;
- L-BFGS `maxcor=20`;
- L-BFGS `gtol=1e-4`;
- no holdout-based early stopping;
- identical deterministic pruning/order and PJTW writer.

Every arm starts from the same projected CURRICULUM prior point. Regularization is centered on the same CURRICULUM projection and is not part of the varied factor.

## 6. Three frozen objective arms

### LOCAL

Teacher-local objective is the already-authenticated aligned CONTEXT_30 target carried by CURRENT_2M:

- target mode `external`;
- target sidecar = exact `current_2m-context30.npy` recovered from 1340;
- target contract = `CONTEXT_30_ALIGNED_alpha_0.30` from the source certificate.

This is the local/decision-sensitive arm referred to by the CLS master plan. It reuses the historical target; no alpha sweep or relabel is allowed.

### WDL

Global objective uses the WDL byte already present on the **same JNNW rows**:

- target mode `wdl`;
- black-POV logistic probability mapping exactly as implemented by `train_stream.py`;
- no external target sidecar and no outcome reweighting.

The historical generator provenance is common to all arms, so any causal claim is explicitly conditional on this fixed empirical distribution.

### MIXED

MIXED uses both data terms on the same rows. The common parent-centered regularization is added once, outside the objective normalization.

Let `w0` be the common projected CURRICULUM start, and let `g_LOCAL(w0)` and `g_WDL(w0)` be the **TRAIN-only unregularized data gradients** in the exact common pruned/folded coordinate system.

Before the mixed fit starts, compute and seal:

- `n_LOCAL = ||g_LOCAL(w0)||_2`;
- `n_WDL = ||g_WDL(w0)||_2`.

Both must be finite and strictly positive. They are computed from TRAIN only; holdout is forbidden. The receipt pins row count, feature/prune identity, parent SHA, target sidecar SHA, both norms and implementation SHA.

The frozen mixed data objective is:

`L_MIXED_data(w) = 0.5 * L_LOCAL(w)/n_LOCAL + 0.5 * L_WDL(w)/n_WDL`.

Then add the exact common CURRICULUM-centered regularization once:

`L_MIXED(w) = L_MIXED_data(w) + R_CURRICULUM(w)`.

Equivalently, its data gradient is `0.5*g_LOCAL/n_LOCAL + 0.5*g_WDL/n_WDL`. Lambda is exactly `0.5` in normalized gradient space. No lambda sweep or re-estimation after any holdout/readout is allowed.

## 7. Fit execution and sealing

The implementation must first prove on deterministic synthetic data that:

1. LOCAL mode reproduces native single-target LOCAL loss/gradient when mixed code is asked for LOCAL-only;
2. WDL mode reproduces native WDL loss/gradient when asked for WDL-only;
3. mixed gradient equals the preregistered algebra to numerical tolerance;
4. normalization is computed from TRAIN only;
5. common prior regularization is applied exactly once;
6. all three arms have identical trainable-coordinate identity and serialization geometry.

Then fit all three arms in one authenticated job or one three-job bundle with shared source receipts. Model bytes are sealed immediately after each fit. A failed optimization is technical; it does not authorize changing max iterations, lambda, L2, targets, corpus or architecture.

## 8. Readout and causal interpretation

The common untouched historical holdout may report, for every arm:

- LOCAL logistic loss;
- WDL logistic loss;
- normalized MIXED data loss using the pre-fit frozen norms;
- score drift versus CURRICULUM;
- finite/convergence diagnostics.

These are descriptive. No arm is declared externally stronger from holdout loss, teacher agreement or model drift.

All technically valid sealed arms proceed independently to the already-frozen CLS-G0 runtime catastrophe gate. A G0 failure is terminal for that exact arm. G0 PASS still does **not** establish strength.

Any later CLS-S / CLS-E comparison must use the exact sealed arm bytes, direct parent CURRICULUM, common paired cohorts/openings and prospectively frozen multiplicity accounting. No automatic promotion is allowed.

## 9. Preflight dependency

CLS-L V1 remains blocked until the tooling identity job:

`cpx62-2016-l3-cls-g0-runtime-tooling-preflight-v1`

returns `CLS_G0_RUNTIME_TOOLING_PREFLIGHT_READY_V1` with identity candidate PASS, zero trace-semantic mismatches, zero fit, zero strength game, zero alpha, zero promotion and zero bake.

Its exact attempt, code SHA and launch receipt must be pinned in the machine-readable CLS-L contract before this preregistration can become ACTIVE or merge as an execution authorization.

## 10. Explicit non-claims

CLS-L V1 does not by itself claim:

- that CONTEXT_30 is stronger than WDL;
- that MIXED is stronger than either single objective;
- that any arm beats CURRICULUM;
- that historical CURRENT_2M is the optimal future closed-loop data distribution;
- that a holdout metric authorizes promotion.

Only subsequent search-transfer and paired fixed-time strength evidence may support continuation.
