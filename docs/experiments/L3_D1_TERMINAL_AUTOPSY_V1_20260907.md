# L3 D1 Terminal Autopsy V1 — 2026-09-07

## Status

Diagnostic-only post-terminal autopsy after `D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1`.

Source terminal job:

- job: `cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1`
- attempt: `20260906T222203Z-08fd187a`
- code: `08fd187aa187f26bd7179df2c68056a74e28355d`
- verdict: `D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1`

This autopsy cannot reopen D1, authorize equal-node, retune lambda, search a model, fit a model, play a game, promote, or bake.

## Frozen question

Why did the frozen treatment `WDL + selected-action listwise CE, lambda_decision=1.0` degrade both held-out decision transfer and WDL calibration?

We distinguish four explanations without modifying the treatment:

1. **training-only teacher fit / held-out reversal** — the treatment learns the 3,200 C-train parent decisions but fails to generalize to C-valid/test;
2. **WDL/decision objective conflict** — the treatment moves the static evaluation in a direction that materially damages the immutable CURRENT_2M WDL objective;
3. **simple side-to-move/sign pathology** — degradation is concentrated in one STM orientation rather than appearing across both;
4. **static representation pressure / overconfidence** — selected-action probability may rise on average while CE worsens because the model becomes catastrophically wrong on a tail of parents.

These are diagnostic labels, not gates for choosing a new hyperparameter.

## Immutable inputs

Only already-sealed D1/C artefacts may be consumed:

- D1 terminal fit reports and models from job 1849;
- D1 terminal readout from job 1849;
- `D1_DECISION_GROUPS.json` from job 1849;
- authenticated C `SiblingDataset v2` from job 1845 only to reconstruct the exact decision-child JNNW and production eval features.

Forbidden:

- B3 full-ladder job 1843 values;
- q5/q50/q200 score values as learning targets;
- any new teacher search;
- any fresh self-play;
- any model fit or refit.

## Frozen diagnostics

### A. Train / valid / test decision transfer

For every parent in the exact C split, recompute under both sealed D1 models:

- selected-action cross entropy;
- selected-action probability;
- selected action rank;
- top-1/top-2;
- treatment delta `CE_control - CE_listwise` (positive means treatment better).

Publish per split:

- mean/median and 5/25/75/95 percentiles of treatment delta;
- fraction of parents improved;
- fraction with catastrophic regression (`delta < -1.0 nat`);
- fraction with large improvement (`delta > +1.0 nat`);
- top-1/top-2 deltas;
- selected-probability delta.

Also publish the same delta summary by the frozen 8 phase/STM cells and by legal-action-count bands `2-4`, `5-8`, `9-16`.

The recomputed C-train metrics must agree with the sealed fit reports to numerical tolerance.

### B. WDL damage

Consume the already-sealed terminal WDL readout only. No CURRENT_2M relabel or refit is allowed.

Publish:

- control and listwise holdout logloss/Brier;
- `delta_wdl`;
- frozen non-inferiority tolerance `0.002`;
- boolean `wdl_conflict = delta_wdl > 0.002`.

### C. Quantized model displacement

Read the two sealed PJTW v3 models and publish listwise-minus-control displacement for:

- all weights;
- pattern MG;
- pattern EG;
- extras MG;
- extras EG.

For each block publish changed fraction, mean absolute delta, RMS delta, p95 absolute delta, maximum absolute delta, sign-flip count/fraction, and the same magnitudes divided by the PJTW scale.

No coefficient is selected for a new model.

### D. Failure-shape classification

The autopsy may emit descriptive flags only:

- `teacher_train_fit` if C-train CE improves;
- `heldout_reversal` if train improves but both valid and test worsen;
- `wdl_conflict` if frozen WDL non-inferiority fails;
- `mean_probability_up_ce_worse` if selected probability rises while CE worsens on valid/test;
- `failure_across_both_stm` if both STM orientations contain negative treatment delta in all four phase cells.

If `teacher_train_fit && heldout_reversal && wdl_conflict`, the descriptive classification is:

`TRAIN_FIT_WITH_HELDOUT_REVERSAL_AND_WDL_CONFLICT`.

This classification authorizes **only a separately preregistered transfer-redesign hypothesis**, not a lambda sweep or strength test.

## Required terminal publication

`D1_TERMINAL_AUTOPSY_COMPLETE_V1` is a diagnostic completion label, not a success verdict for a model.

Required counters:

- fits = 0
- model_searches = 0
- teacher_searches = 0
- strength_games = 0
- promotions = 0
- bakes = 0
- equal_node_gate_authorized = false

The next stage is always `STOP_DIAGNOSTIC_REVIEW` until a new, separately preregistered scientific hypothesis is approved.
