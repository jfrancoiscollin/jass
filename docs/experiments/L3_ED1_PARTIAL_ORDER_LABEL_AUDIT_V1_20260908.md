# ED1 — Partial-order label reliability screen (2026-09-08)

Status: NEW SCIENTIFIC HYPOTHESIS; diagnostic-only authorization under the user's
2026-09-08 instruction to start a new evaluation/data hypothesis. Not a D4 or J12
recovery, not a reopening of a frozen strength experiment.

## Motivation and distinction

D1 injected one selected-action identity into the value loss; D2 and D3 isolated
policy learning but still explicitly excluded numeric sibling values, bounds and
stability from the target. D4b/c subsequently tested cutoff ordering, not value
learning. D4c `1871` ended `D4C_RANK_BREAKER_OFFLINE_NOT_SUPPORTED_V1`. J12 `1872`
ended `J12_FACTORIAL_GATE0_NOT_SUPPORTED_V1`. Those verdicts remain immutable.

ED1 asks a different, narrower question: are hard pairwise preference labels too
categorical when search values are budget-sensitive, and can a fixed abstention
rule reduce their subsequent contradictions without deleting almost all labels?
It is not established that this caused D1/D3's failures. Their Jass-selected
training labels are not the Scan labels audited here.

A possible next learning objective would supervise only reliable ordinal
inequalities, leaving unresolved comparisons unconstrained. ED1 does not train
that objective, distill Scan weights, fit a score transformation, retune a loss,
add runtime features, or alter search. It first tests the proposed label recipe.
This is not a claim that partial-order learning is novel in the literature.

## Immutable sources and information roles

Use the same sealed BASE2000 sibling metadata and Scan ladder already used by
Gate0, authenticated by `fetch_result_files.py`:

- selection `home-1651-l3-scan-ceiling-selection-v1`, attempt
  `20260829T133348Z-28e12fba`, `artefacts/siblings.tsv`;
- official Scan ladder `home-1657-l3-scan-ceiling-scan-base-v1`, attempt
  `20260829T144418Z-46623b26`, sixteen `scan-base-shard-00..15-scores.tsv.gz`;
- cohort A: `1864`, attempt `20260907T195559Z-8782aed3`, original Gate0 ids,
  SHA256 `ac33eac505c1bbf316718d2976d151fa51f8e87de5ce96e6d0ecf00a97a5357c`;
- cohort B: `1872`, attempt `20260908T111609Z-f4a438fd`, J12 ids,
  SHA256 `e0befc1c5ad0ad1e8d4f396a6162bfd3d3ec7378a80e099f31e60252df1112ba`.

Exactly 512 parents per cohort, 128 per phase, zero common canonical parent.
These are **previously exposed diagnostic cohorts**, not new independent final
tests. No model is selected on them. The other 976 parents' score fields are not
accessed; all BASE2000 data remains prohibited for training. Shared trajectory
origins may still induce correlation despite canonical-parent disjointness.

The script freezes rule-generated labels from the **5k and 50k** scores, writes
and SHA256-seals that manifest, and only then accesses **200k** numerical values.
Transport, CSV routing by row/budget, and whole-file hashing are allowed before
this boundary; accessing the `parent_score_centi` field at 200k is not. Neither
audit values nor any Jass candidate outcomes are inputs to label construction.

## Single frozen recipe (no gap/temperature sweep)

For each sibling a, define the empirical range:

    I(a) = [min(Q5k(a), Q50k(a)), max(Q5k(a), Q50k(a))].

Baseline labels contain every strict Q50k pairwise preference. Equal Q50k scores
produce no arbitrary tie-break label. The proposed labels retain a > b only if
`min I(a) > max I(b)`. Overlapping or exactly touching ranges abstain. This gives
a partial order, not a requirement to imitate a single winner.

The ranges are **not statistical confidence intervals, certified search bounds,
or minimax proofs**. Scan200k is a stronger-budget reference, not exact truth.
No centipawn-margin threshold, probability calibration or terminal-score remap is
introduced. Existing exact/terminal lines keep their original scores; their
agreement does not turn all other labels into ground truth.

## Metrics, uncertainty and stopping (frozen before execution)

A label a > b contradicts the reference only when Q200k(a) < Q200k(b). Audit ties
are reported separately, never mislabeled as strict reversals. Report pair
coverage, per-parent contradiction and tie rates, 50k best-set tie frequency,
and disjointness of the 50k/200k best sets. No parent is resampled.

For the primary contrast use **the identical set of parents with at least one
retained pair** for both baseline and proposed-label rates. Each parent has equal
weight; do not treat sibling pairs as independent observations. Bootstrap parents
within each phase, preserving phase counts: 20,000 draws, seeds 2026090804 (A) and
2026090805 (B), percentile two-sided 95% intervals. Results remain exploratory,
conditional on these cohorts and the reference budget.

For **each** cohort require all of:

1. at least 256 parents with retained pairs, and at least 32 in every phase;
2. average retained-pair fraction across all 512 parents at least 0.25;
3. baseline strict-contradiction rate on the matched supported parents at least
   0.02 (otherwise the claimed source of label damage is not material here);
4. retained-label contradiction rate at most half the baseline rate;
5. positive 95% lower bound for baseline minus retained contradiction rate;
6. retained-label audit-tie rate no greater than baseline audit-tie rate.

All gates pass on both: `ED1_PARTIAL_ORDER_LABEL_SIGNAL_V1`. This supports only
preregistering independent-data generation and one paired learning experiment;
`fit_authorized=false`, `strength_authorized=false` remain mandatory.
Insufficient parent/phase support: `ED1_PARTIAL_ORDER_SUPPORT_INSUFFICIENT_V1`.
Otherwise: `ED1_PARTIAL_ORDER_NOT_SUPPORTED_V1`; stop and review. Missing source
files, bad identity/coverage, nonfinite values or seal corruption are technical
failures, not scientific negatives. No post-result threshold adjustment.

## Compute and deliverables

0 new Scan searches, 0 Jass nodes, 0 teacher searches, 0 fits, 0 games, 0 self-play,
0 promotions and 0 bakes. Single-process readout, numeric libraries limited to one
thread, 600-second analysis timeout, 1800-second stage cap. No runtime inference
cost claim is measured because no new evaluator is deployed.

Publish source receipts, sealed **audit-only** low-budget labels, parent-level
diagnostics, compact `scientific-summary.json`, and terminal verdict. Tests cover
production-shaped TSV/gzip round-trip, exact cohort hashes, no audit-score access
before freeze, abstention, ties, missing/duplicate/nonfinite data and seal failure.

A positive label screen is NOT evidence of improved evaluation, Elo, a virtuous
self-play loop or Scan-equivalent strength. A future learning experiment must use
new non-benchmark training data, an unchanged evaluation/search baseline, equal
fit budgets, WDL non-inferiority, held-out decision metrics and then runtime.
