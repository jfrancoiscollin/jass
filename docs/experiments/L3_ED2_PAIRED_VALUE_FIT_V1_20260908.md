# ED2-P1 — One paired value-fit after the independent-data preflight

2026-09-08. User mandate: **« Allez on enchaîne »**. New prospective learning
protocol; not a rewrite of ED1, D1–D4 or J12. No TRAIN Scan labels or TEST Scan
labels may be generated until this protocol and its implementation are merged.
The prerequisite is ED2-P0 from PR #871, not a previous benchmark label file.

## Question, controls and scope

Does the ED1 partial-order label recipe improve a **value evaluator**, compared
both with strict point preferences and with its frozen starting evaluator?
There is exactly one pair of fits, POINT and PARTIAL. They share the same value
representation, starting model, WDL replay, optimizer, stopping rules and budget.
No search modifications, policy head, feature additions, hyperparameter sweep,
checkpoint selection, self-play, strength matches, promotion or bake are allowed.

The starting artifact is WDL_CONTROL from job 1849 / 20260906T222203Z-08fd187a,
SHA256 `e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`.
It is **not** substituted for champion CURRICULUM, which remains unchanged.
The whole PJTW v3 header and pattern-table byte prefix stay identical. Only the
240 existing extras coefficients (120 MG plus 120 EG) may change. Runtime uses
an ordinary PJTW v3, scale 1000, production 8cf men-only patterns and tempo stage.
No extra runtime computation is introduced by the representation; actual speed
and search benefit are **not established** by this offline experiment.

## Required P0 receipt, source and held-out barrier

Pinned P0: `cpx62-1875-l3-ed2-data-teacher-preflight-v1`, attempt
`20260908T171140Z-bc30d685`, code `bc30d6858c4d590625f8831c4995f055816b95c2`.
Require completed exit 0, `ED2_DATA_AND_TEACHER_PREFLIGHT_READY_V1`, its source
seal, all files matching that seal, and projected teacher-plus-fit time <=2700 s.
A missing receipt, a failed source, or COMPUTE_REVIEW_REQUIRED cannot be bypassed.

Use the exact reserved TRAIN512 and TEST256, 64 and 32 parents respectively in
each of eight phase/STM cells. Calibration16 remains excluded. Revalidate the
whole canonical parent/child footprint exclusion against BASE2000 and between
all P0 groups. No reseeding, resizing or replacing slow positions. This is the
P0 exclusion claim, not disjointness from all historical corpora ever generated.
Independent restarted random trajectories can still share opening prefixes.

TRAIN siblings receive Scan 5k/50k labels from the exact P0-authenticated official
Scan 3.1 binary, commit `7aae17e7b7bfc47744601afb1ee7655e18983ce5`; same data/ini,
book OFF, bb-size 0, threads 1, fresh new-game per sibling/budget, go analyze.
**Only after both quantized model files are SHA256-sealed** may TEST siblings be
searched at Scan200k. Neither TEST targets nor TEST candidate metrics can enter
fitting or label formation. No validation selection is needed for a single fixed
recipe. TEST decisions are read once; a failed test is not a retuning permission.
Stock Scan progressive snapshots are never described as exact node consumption.

## Targets and the common objective

For nonterminal training siblings a,b, POINT includes every strict Q50k inequality
and excludes exact ties. PARTIAL retains a>b only when
`min(Q5k(a),Q50k(a)) > max(Q5k(b),Q50k(b))`. Touching/overlapping ranges abstain;
no fitted margin or temperature. Empirical ranges are not certified bounds.
Comparisons involving a rule-terminal child are excluded from **both** losses:
the production exact-terminal decision is not something for a static residual to
learn. At TEST, any rule-terminal winning child has unchanged exact priority for
all three evaluators. Every parent still contributes to the final test population.

Let z0 be the unrounded black-POV native linear logit and x the native 120 extras
multiplied by the production double-precision MG/EG phase weights. Let
`z = z0 + x dot beta`. Parent utility has sign + for a black parent and - for a
white parent; this is exactly the negative of child-STM score. For either arm:

    L(beta) = (1/512) sum_parent mean_retained_pairs softplus(-(q_a-q_b))
            + mean_replay [softplus(z)-y*z] + 0.0005 * ||beta||^2.

A parent with zero pairs contributes zero to the pair term, not an implicit
resampling or division by the number of surviving parents. The two arms have the
same parent population and normalizer. This estimates the **entire abstention
recipe**, including dropping comparisons, not a pure quality effect at equal
label counts. Publish support and retained coverage before fitting.

Require PARTIAL support >=256 training parents, >=16 in each phase/STM cell,
and parent-average retained/POINT coverage >=0.25. Otherwise emit
`ED2_PARTIAL_ORDER_TRAIN_SUPPORT_INSUFFICIENT_V1`, zero fits, no TEST labels.

Optimizer: float64, zero residual initialization, scipy L-BFGS-B, analytic gradient,
L2=0.001, maxiter=500, maxcor=10, gtol=1e-6, ftol=1e-12, maxls=30. WDL and pair
coefficients both 1.0. Exactly one optimizer invocation per arm, no restarts.
Both must converge with finite output; 300 s cap per fit. A failed optimizer is
an execution/numerical failure, not a scientific negative or license to retune.

## Frozen historical WDL replay and guard

Reproduce CURRENT_2M from turnover source `home-0977-l3-pure-turnover1to1-train-v1`
/ `20260726T071254Z-336bb984`, exactly as D1 did: opening-group split, modulus 10,
seed 577215, 1,800,796 train followed by 199,204 holdout rows. Raw JNNW SHA256
`9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d`; JSM SHA256
`acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682`.
Require byte-identical split manifest to `cpx62-1340-jass-megacorpus-comparative-fit-v1`
/ `20260814T123246Z-2ce07222`. Reuse its authenticated `current_2m-context30.npy.gz`
black-POV targets, without regenerating or fitting a mapper.

Select 8192 rows from each historical fold using numpy default_rng permutations,
seeds 202609081201 and 202609081202, in that order. Reject canonical duplicates,
all ED2 parent/child footprints and all benchmark exclusions before reading the
selected Context30 values. Freeze row IDs, opening IDs, zero-target JNNW and file
hashes. Selection sees identity/metadata only; transporting/hash-checking the raw
historic source and reproducing its existing split is allowed. At least 32 opening
clusters per subset; train/holdout opening IDs must be disjoint. No support extension.
Only replay targets are accessed during training. Holdout targets are accessed
only after both models are sealed. This is a **historical Context30 calibration
guard**, not an independently fresh WDL accuracy or gameplay result.

## Native artifact and decision readout

Quantize new extras with round-to-nearest/ties-to-even at scale 1000; reject int32
overflow/nonfinite values. Preserve every other file byte. Reopen each artifact
with the actual native loader. An isolated read-only probe obtains production
extras and native final integer scores; it independently checks unrounded linear
sum/phase/truncation/clamp parity on every row. A zero-residual serialization must
be byte-identical. No compiler flags altering the evaluator are introduced.
The primary results use **native integer post-quantization scores**, not Python
float surrogate predictions. TEST ties use original sibling row order; Scan best
sets include all exact score ties. Scan200k is a deeper-budget reference, not truth.

Primary: mean parent regret `max_sibling Q200k - Q200k(chosen)` on all TEST256.
Two required paired contrasts: BASE minus PARTIAL and POINT minus PARTIAL.
Bootstrap parents within all eight fixed phase/STM cells, 20,000 draws,
seeds 202609081301 and 202609081302, percentile two-sided 95% CIs.
Both lower endpoints must exceed zero. This is an intersection of two required
improvements, not selection of the favorable comparator. Conditional inference on
these cohorts does not remove all correlations due to common openings.

Additional mandatory gates:
- PARTIAL top-hit no lower than BASE and POINT.
- Versus BASE, number of strictly harmed parents <= strictly improved parents;
  publish unchanged, improved/harmed and total changed choices.
- Historical holdout logloss difference PARTIAL-BASE has upper 95% bound <=0.002,
  from paired opening-cluster bootstrap, 20,000 draws, seed 202609081303. Clusters
  are sampled uniformly and the ratio of their loss sums/counts preserves the
  sampled-row estimand. Do not treat correlated game positions as independent.
- PARTIAL holdout Brier <= BASE Brier+0.002. All metrics finite and complete.

All gates: `ED2_PARTIAL_ORDER_VALUE_SIGNAL_V1`, next `PREREG_NATIVE_GATE0`.
Otherwise: `ED2_PARTIAL_ORDER_VALUE_NOT_SUPPORTED_V1`, next `STOP_ED2`.
Neither authorizes Elo, promotion, bake, automatic runtime activation or a
self-play loop. This single fresh small-scale fit does not establish compounding.

## Cost, execution and failure behavior

Eight single-thread Scan workers, fixed row_index modulo 8; no more than the P0
planned child/budget grid. Worst-case 1,269,760,000 requested Scan nodes, actual
budget published from fixed child counts (terminal rows cost zero). No Jass search.
Per RPC 30 s. Each train/test batch cap = max(60, 2*slowest calibration per-row
budget cost*maximum shard row count+60) seconds; >1200 s requires compute review.
Both caps are checked before any training labels; an excess emits
`ED2_PAIRED_COMPUTE_REVIEW_REQUIRED_V1`, zero fits/labels, STOP_COMPUTE_REVIEW.
Stage hard cap 2700 s including setup and fits, not a promised duration. No partial
harvest, no dropping failed positions. Worker process groups are terminated on any
failure. This phase has no asynchronous follow-on; the runner executes only the
queued stage. Keep source/teacher/models/seals, native diagnostics and phase/error
logs. Preserve technical failures separately from completed scientific negatives.
