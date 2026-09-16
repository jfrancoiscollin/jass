# L3 CLS-D bottleneck classification V1

Date: 2026-09-16. Status: **classification rule frozen before reading the detailed terminal production artefacts in this stage**.

## Purpose

The merged `L3_CLOSED_LOOP_STRENGTH_CAMPAIGN_V1_20260910.md` requires one terminal joint classification after the four descriptive CLS-D productions. This stage consumes only authenticated, already-completed diagnostic artefacts and publishes exactly one classification from the allowed vocabulary:

- `SEARCH`
- `DECISION-EVAL`
- `COST`
- `mixed`

This is a descriptive campaign diagnosis, not a confirmatory claim. It spends no alpha and launches no search, game, fit, target read, promotion or bake.

## Frozen source productions

- depth/growth: `cpx62-2000-l3-cls-depth-growth-full-production-v2`, attempt `20260916T083204Z-7a5f44ec`, receipt `3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42`;
- mirror-scale: `cpx62-2008-l3-cls-mirror-scale-production-v3`, attempt `20260916T161938Z-92984c1f`, receipt `2ac13b1e61dffc7d73217a8daba111aed9028b7a006020d081ebd6aa3480b004`;
- search-profile: `cpx62-2010-l3-cls-search-profile-production-v1`, attempt `20260916T170101Z-bd9e7ddd`, receipt `2c209ed6f618a1ca49c67f4224c2dbfaa680a53208e485b9689c7f885c184178`;
- draw/pentanomial/throughput: `cpx62-2013-l3-cls-draw-pentanomial-throughput-production-v1`, attempt `20260916T194330Z-1cd72e5a`, receipt `b8df0cc6f5ebf25f7e52c165e9c6b6c88e952b1d6882de5c6dd91d3c1402f450`.

All four must authenticate as completed production diagnostics with zero alpha, fit, fresh strength-game and target-read side effects. Any identity, receipt, terminal or effect drift is technical failure.

## Frozen classification rule

Use only the deepest **shared** Jass-vs-Scan node budget, `200000`, so no budget is selected after inspection.

Three axis-support indicators are frozen:

1. **SEARCH support**: the phase-stratified bootstrap 95% interval for `completed_depth_delta_jass_scan_200000` from search-profile is entirely below zero (`q975 < 0`). This means Jass completes significantly less nominal depth than Scan at the shared high budget.
2. **DECISION-EVAL support**: the mirror-scale bootstrap 95% interval for `mirror_excess_200000` is entirely above zero (`q025 > 0`). This means shallow Jass agrees significantly more with same-engine deep Jass than with Scan, supporting a persistent decision/evaluator-family component rather than pure shallow-budget noise.
3. **COST support**: the search-profile bootstrap 95% interval for `log_nps_ratio_jass_scan_200000` is entirely below zero (`q975 < 0`). This means Jass processes significantly fewer nodes per second than Scan at the shared high budget.

Classification is deterministic:

- exactly one supported axis -> that axis;
- two or three supported axes -> `mixed`;
- zero supported axes -> `mixed`, with reason `NO_SINGLE_AXIS_ISOLATED_UNDER_FROZEN_RULE` rather than inventing an unregistered fifth class.

The stage also reports evidence limitations but they do not change the rule: same-search nodes-to-depth is unavailable by design, and the legacy 2013 source lacks native search-wall telemetry. The draw/pentanomial evidence is carried forward for future strength-harness design, not repurposed to force a bottleneck label.

## Output and terminal

Required outputs:

- `classification.json`
- `source-authentication.json`
- `RESULTS.md`
- `manifest.json`
- `scientific-summary.json`

Successful production terminal: `CLS_DIAGNOSIS_COMPLETE_V1`.

The only authorized next action is to prospectively amend the next-candidate contract with a runtime catastrophe gate and immutable `CURRICULUM` anchor. This stage does **not** authorize CLS generation 1, promotion, bake or scale-up by itself.
