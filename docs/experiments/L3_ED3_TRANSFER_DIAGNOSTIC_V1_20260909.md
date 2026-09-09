# ED3-T1 — fit-free ranking-transfer diagnostic on consumed data

Date: 2026-09-09. Explicit mandate: GO for one bounded, descriptive diagnostic
after the terminal ED3-P2 result. This document is the prospective freeze for
that diagnostic, written before any new metric is computed. The diagnostic may
read the already consumed TRAIN and confirmation artifacts named below. It is
therefore `EXPLORATORY_CONSUMED_DATA`, not a fresh confirmation, and cannot alter
the terminal `ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1` or its prescribed
`STOP_ED3`.

## Question and hard boundary

The sole question is where the frozen HARD-to-SOFT change actually altered
rankings, whether those alterations reached the frozen choices on consumed 1884,
and how the observed regret and WDL harm are distributed. This is a mechanism
description, not a new estimate of generalization or causality.

No fit, optimizer, label generation, Scan/Jass/native-engine invocation, search,
game, bootstrap, resampling, threshold selection, candidate selection, tau
change, sweep, calibration, promotion or bake is permitted. BASE, HARD and SOFT
remain the exact frozen bytes below. No diagnostic result opens another ED3
stage. `CURRICULUM` remains champion.

The TRAIN and confirmation pair populations are different estimands. TRAIN uses
the PARTIAL support retained by the joint Q5k/Q50k rule; confirmation uses every
strict Q200k sibling pair. Their matrices may be displayed in adjacent sections,
but the implementation must not subtract their entries, form a transfer rate,
normalize one by the other, test their difference, or describe the difference as
a causal effect. In particular, a realized TRAIN ranking change is not proof
that the same pair, position or mechanism transferred to confirmation.

## Frozen identities and positive input allowlist

Every source is fetched through its completed outer manifest, inventory and
checksums. Only the literal files below may be read; discovery from inventory
must not expand the allowlist.

* P0 source, 1875 / `20260908T171140Z-bc30d685`, code
  `bc30d6858c4d590625f8831c4995f055816b95c2`: `artefacts/source/groups.tsv`,
  `parents.tsv`, `children.jnnw`, `parents.jnnw`, `source.json`, and
  `artefacts/ed2-source-seal.json`.
* HARD/TRAIN, 1878 / `20260908T191343Z-d71679e9`, code
  `d71679e96d78609b6d32052be80ca78c0deaece0`: `artefacts/train-0.jsonl`
  through `train-7.jsonl`, `train-labels-sealed.json`, `label-support.json`,
  `native/train-native.tsv.gz`, `native/PARTIAL-train-native.tsv.gz`,
  `PARTIAL.pjtw`, and `work/train.jnnw`.
* SOFT, 1882 / `20260908T220255Z-20a5e4eb`, code
  `20a5e4ebebedbf9340eafd3750506c1aed851506`: `artefacts/SOFT.pjtw`,
  `candidate-seal.json`, `fit-report.json`, `native-roundtrip.json`,
  `train-contract.json`, and `work/train-soft.tsv`, `train-reloaded.tsv`,
  `train-base.tsv`, `train.jnnw`.
* Consumed confirmation, 1884 / `20260909T051901Z-0946f57d`, code
  `0946f57d5443c0507fd9210371396bdf1c49abd2`: artifacts
  `model-identities.json`, `cohort-seal.json`, `guard-plan.json`,
  `confirmation-readout.json`, `parent-readout.json`, `reference-0.jsonl`
  through `reference-7.jsonl`, and
  `source/{groups.tsv,parents.tsv,children.jnnw,parents.jnnw,source.json}`;
  work files `{BASE,HARD,SOFT}-decisions.tsv`,
  `{BASE,HARD,SOFT}-guard.tsv`, `BASE-repeat.tsv`, `decisions.jnnw` and
  `guard.jnnw`, plus `BASE.pjtw` for authenticated model reconstruction. Read
  the Context30 target array only from the already fetched and
  authenticated 1884 input path `inputs/n1/work/current-context30.npy`; do not
  fetch an alternate target copy or return to source job 1340.

Frozen model SHA256 identities are BASE
`e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`,
HARD `3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e`,
and SOFT `d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a`.
Require the 1884 cohort seal
`f1ce4d2d8cdb947c1dbfc1bdccdfc588927a4299f661d58097b0507e28a5bb8b`
and 512 parents, 64 in each original phase/STM cell, 4,702 decision children,
8,192 guard rows and 2,394 opening groups. Require TRAIN 512 parents, 4,976
children, 17,622 PARTIAL-retained nonterminal pairs, its original eight
64-parent cells and source seal
`31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c`.
Any identity, schema, order, count or checksum mismatch is a technical failure.

All native tables have 124 columns: row id, unrounded black-POV logit, native
integer child-STM score, MG phase weight, and 120 native features. Require finite
values, consecutive row ids, phase in [0,1], identical features across arms and
the already frozen model-difference reconstruction at absolute tolerance 1e-9.
The native integer score is primary because it made the production choice.

## Common definitions

Original sibling order and row ids are immutable. Let `Q(r)` be the published
reference score for child row `r`. For native integer analyses define parent
utility `U_A(r) = -cp_A(r)`, because the child side to move is opposite its
parent. On confirmation, the actual frozen choice is the first rule-terminal
row, `min(terminals)`, whenever the parent has one; otherwise it is the row
maximizing `(U_A(r), -row_id)`. This exactly preserves 1884 `decision_rows` and
its first-sibling model-tie rule because original group order has monotonically
increasing row ids. A reference best set is
`B={r:Q(r)=max Q}` and retains all exact reference ties.

For an oriented strict reference pair `(w,l)` with `Q(w)>Q(l)`, classify an arm
as `correct` when `U_A(w)>U_A(l)`, `tie` when equal, and `wrong` when lower.
The HARD-to-SOFT transition matrix has HARD state on rows and SOFT state on
columns in the fixed order `correct,tie,wrong`. Publish both integer pair counts
and full-parent mass. For parent `p` with `k_p>0` eligible pairs, each pair has
mass `1/(512*k_p)`; a parent with `k_p=0` contributes zero. Thus matrix mass sums
to `supported_parents/512`, not silently to one. Publish supported and unsupported
parent counts, total eligible pairs and total mass alongside every matrix.
Conditional percentages may be added only with their denominator stated; counts
and full-parent mass remain primary.

For every parent with a nonempty reference-rest set `R=children minus B`, define the
best-versus-rest margin
`M_A=max_{b in B} U_A(b)-max_{r in R} U_A(r)`. Classify it positive, zero or
negative without epsilon. A parent whose children are all reference-best has a
null margin and remains in the full-parent denominator as `rest_unsupported`.
Publish the HARD-to-SOFT 3x3 margin-state matrix, the numeric `M_HARD`, `M_SOFT`
and `M_SOFT-M_HARD` distribution, and the unsupported count. This raw-score
margin is not policy-equivalent on a confirmation parent with a rule-terminal
child because terminal priority bypasses model scores. Publish
`terminal_priority_parent` on every parent row and its full-population count;
do not interpret the margin as explaining the choice for those parents.

Argmax propagation uses the actual fixed tie rule. Publish mutually exclusive
full-parent counts for: same row; changed row with both choices in `B`; HARD
outside `B` to SOFT in `B`; HARD in `B` to SOFT outside `B`; and changed row
with both outside `B`. Also publish the ordinary 2x2 HARD-hit to SOFT-hit matrix.
No row is dropped because its choice or regret is unchanged.

Every empirical distribution publishes `n`, finite check, mean, population
standard deviation, min, max, counts `<0`, `=0`, `>0`, and quantiles at
0, .05, .10, .25, .50, .75, .90, .95 and 1 using NumPy's linear quantile rule.
The complete row-level values are also published, so the summary is not a
post-hoc binning scheme.

## A. TRAIN ranking changes

Reconstruct exactly the 17,622 PARTIAL edges from the 1875 TRAIN ownership and
1878 Q5k/Q50k labels. Exclude rule-terminal children, orient by strict Q50k, and
retain `(w,l)` iff
`min(Q5k(w),Q50k(w)) > max(Q5k(l),Q50k(l))`, exactly as ED2-N1/ED3-P1.
Do not form POINT-only or alternative supports. Join HARD and SOFT native rows
by the sealed TRAIN row order and compute the transition matrix above.

Also report, separately and descriptively, TRAIN parent argmax propagation and
best-versus-rest margins with `Q=Q50k` over nonterminal children. Pair support,
choice support and margin support have separate denominators: zero retained
pairs sets `pair_support=false` but does not drop a parent with valid
nonterminal choice or margin data. Choice is null only when the nonterminal child
set is empty; margin is null only when its reference-rest set is empty. Publish
each unsupported count separately. These are nonterminal-only TRAIN diagnostics,
not reconstruction of a terminal-priority production policy. No quantity in
this section is compared numerically to section B as if the rows or pair
definitions matched.

## B. Choice propagation and regret on consumed 1884

Reconstruct the 1884 reference map from all eight published reference JSONL
files and require exact agreement with the published parent readout and reference
coverage. For the confirmation pair matrix, take every unordered sibling pair
with unequal Q200k, orient the higher child as `w`, and exclude only exact Q200k
ties. This is the fixed `all_strict_Q200` support; it is not the TRAIN retained
support. Publish the pair transition, best-versus-rest margin transition and
argmax propagation definitions above.

The primary includes every 1884 child, including published rule-terminal rows.
Disaggregate the primary pair matrix into the two exhaustive factual components
`terminal_involving` and `nonterminal_only`, using only the existing boolean
`terminal` field, and require their elementwise sum to equal the primary matrix.
Each component inherits the primary pair mass `1/(512*k_p)`, where `k_p` is the
parent's count across all strict Q200 pairs; never renormalize within a component.
Report each component's pair count, number of parents contributing at least one
pair and inherited mass sum. A component mass sum therefore need not equal its
contributing-parent count divided by 512. This is a reconciliation, not a
filtered alternative estimand. Do not infer or name mate, tablebase, forced-win
or other semantic score families from raw score magnitude. Exact Q200 score ties
remain excluded from pair matrices and included in the reference best set.
Margin and argmax summaries retain all children and are not recomputed on a
selected score family; actual argmax summaries retain the terminal-priority
choice rule above.

For each arm retain the original regret
`R_A=max_r Q200k(r)-Q200k(choice_A)`. Publish one record for every parent with
cell, choices, hit flags, margins and both fixed deltas
`D_BASE=R_BASE-R_SOFT` and `D_HARD=R_HARD-R_SOFT`; positive means SOFT improves,
negative means SOFT harms. For each contrast publish the complete empirical
distribution globally and separately in each of the eight original cells, using
all 64 parents per cell. Include choice-changed counts within every cell. The
previous 1884 results are an identity check: recompute the means and
improved/harmed counts exactly, but authenticate and echo the already published
CI fields from `confirmation-readout.json`. Do not invoke a bootstrap or claim
the CIs were recalculated, and do not interpret them anew.

## C. WDL row and opening contributions

Use exactly the 8,192 guarded indices and their 2,394 existing opening ids in
their sealed order. Decode each target only after all source/model/guard
identities pass. With the existing child-STM sign convention, reproduce each
arm's published logloss and Brier exactly. For each guard row publish logloss
and Brier deltas `SOFT-BASE` and `SOFT-HARD`; positive means higher loss for
SOFT. Publish the complete row-level empirical distributions for both contrasts
and both losses.

For each opening `g`, publish its row count, sum and mean of each delta, plus its
additive contribution to the global row mean, `sum_delta_g/8192`. Require sums
of opening contributions to equal the corresponding global deltas within a
declared binary64 tolerance of 1e-15 absolute. Publish the complete opening-level
distributions of sums, means and contributions. Opening size is descriptive;
do not equal-weight openings, create size strata, rerun the cluster bootstrap or
select influential openings. The existing 1884 SOFT-minus-BASE logloss delta and
its already published CI are reproduced as identity evidence only.

## Fixed score-representation sensitivity

Repeat only the TRAIN/confirmation transition, margin and argmax summaries with
the authenticated unrounded native logit. Convert logit to parent POV with the
same parent-STM sign used by the ED2/ED3 objective, and use exact binary64
comparison plus original row order for ties. On confirmation, the logit
sensitivity choice still selects `min(terminals)` whenever a terminal exists;
only nonterminal parents use the logit argmax. Label this
`quantized_model_unrounded_logit_sensitivity`; it tests whether final native
integer conversion changes the descriptive ranking. It does not isolate model
weight quantization: no authenticated pre-quantization SOFT beta is available,
and none may be reconstructed or refit. Native integer results remain primary.

## Execution, rehearsal and publication contract

Use a dedicated launch-profile V2 contract with zero engine or training side
effects. The rehearsal runs the complete diagnostic on the same entire historical
dataset, as ED3-P0 permitted, and is explicitly development-only. Production may
run only after authenticating that same-code/profile/normalized-spec/runtime
rehearsal and then repeats the deterministic reads and calculations. Rehearsal
and production are not independent evidence; only `LAUNCH_MODE` may differ and
no result may change a definition or parameter.

Run on CPX62 with 16 available CPUs, one thread for each numeric library, at
least 3 GB free disk, a 900-second stage cap and a 1,500-second outer admission
cap. These are ceilings, not ETAs. The read-only inventory observed about 603 GB
free; the full 1884 production previously took about 60 seconds and the current
four-source metadata inventory about 6.3 seconds. Those historical observations
only establish bounded feasibility for this no-engine diagnostic and do not
relax any cap or identity check.

Per invocation, record exactly 4,702 existing Q200 decision-score reads plus
8,192 existing WDL target reads, hence
`existing_heldout_target_reads=12894`, `new_confirmation_target_reads=0`.
Also record 9,952 archived TRAIN score cells (4,976 rows at Q5k and Q50k) as
`existing_train_label_reads=9952`, separate from heldout reads. If both rehearsal
and production complete, the outer ledger maximum is 25,788 existing heldout
reads and 19,904 existing TRAIN label reads. Reads of native predictions are
reported separately and are not target reads. Set fits, optimizer calls, new
Scan searches, new Jass searches, new positions, self-play/strength games,
promotions, bakes and automatic continuations all to zero.

Publish atomically, with schemas and SHA256 in a manifest:

* `ed3-transfer-diagnostic.json` — identities, counts, all summary matrices and
  distributions, exact old-result reproduction, boundaries and effect ledger;
* `train-pair-transitions.jsonl` and `confirmation-pair-transitions.jsonl` — one
  record per fixed eligible pair, including parent/cell, reference gap, terminal
  family, HARD/SOFT states, integer margins, full-parent mass, and logit
  sensitivity states;
* `parent-transfer.jsonl` — all TRAIN and confirmation parent records, explicitly
  tagged by population, including support, choices, best-set membership, margins
  and confirmation regret deltas where applicable;
* `wdl-row-contributions.jsonl` and `wdl-opening-contributions.jsonl` — all fixed
  rows and all fixed openings with the loss contributions above;
* `source-authentication.json`, `execution-evidence.json`,
  `publication-manifest.json`, and `scientific-summary.json`.

The inner `publication-manifest.json` hashes only the immutable diagnostic
payloads, row tables, opening table and `source-authentication.json`. It excludes
itself, `execution-evidence.json` and `scientific-summary.json`: StageEvidence
finalizes timestamps after the publish phase, and generic launch-gate V2 adds
launch provenance to the scientific summary. The outer runner inventory,
checksums and launch receipt authenticate those final mutable-envelope files.
No circular or knowingly stale inner hash is permitted.

Require deterministic byte identity across two local calculations before
publication, nonempty expected supports, complete 512/4,702/8,192 coverage,
eight confirmation cells of exactly 64, exact source/model hashes, finite values,
and additive reconciliation. Missing support, corruption, native-table mismatch,
old-result mismatch or incomplete coverage fails closed as technical failure;
it is not a scientific result.

Rehearsal terminal: `ED3_TRANSFER_DIAGNOSTIC_REHEARSAL_COMPLETE_V1`.
Production terminal: `ED3_TRANSFER_DIAGNOSTIC_COMPLETE_V1`, classification
`EXPLORATORY_CONSUMED_DATA`, `scientific_verdict=null`, `next_stage=STOP_ED3`,
`runtime_authorized=false`, `automatic_continuation=false`. No favorable pattern,
including a large TRAIN transition or a concentrated harm distribution, changes
the terminal ED3 decision or authorizes a new candidate, threshold, rerun,
confirmation or runtime gate.
