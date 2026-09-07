# L3 Scan-oracle Gate 0 v1 — 2026-09-07

## Purpose

Create a permanent cheap screening layer before Elo/self-play. This is a benchmark-only diagnostic and cannot promote, bake, retune, or replace a later causal strength gate.

The first execution is deliberately retrospective: ask whether this Gate 0 would have rejected the already-terminal D3 runtime move-ordering treatment before its 1,500-game equal-node match. D3 game outcomes are **not read by the Gate 0 job**.

If the retrospective screen is useful, the same harness is the default first screen for D4 runtime and later search/eval candidates.

## Frozen external reference

Reuse the already-consumed, target-blind Scan-ceiling cohort and Scan scores; do not generate new Scan compute.

- cohort source: `home-1651-l3-scan-ceiling-selection-v1` / `20260829T133348Z-28e12fba`
- cohort: 2,000 parents, 500 each P0/P1/P2/P3, all siblings exported
- Scan source: `home-1657-l3-scan-ceiling-scan-base-v1` / `20260829T144418Z-46623b26`
- external deep reference for Gate 0: Scan 3.1 sibling scores at exactly requested 200,000 nodes
- Scan is an empirical external deep reference, not mathematical truth.

No current candidate may influence parent selection.

## Cheap subset

Select exactly 512 parents from the frozen 2,000-parent cohort:

- P0: 128
- P1: 128
- P2: 128
- P3: 128
- selector prefix: `SCAN-GATE0-2026090701:`
- within each phase sort by SHA256(prefix + parent_fingerprint) and take the first 128.

Selection reads only parent identity/phase metadata, never Scan/Jass scores or prior outcomes.

## Search contract

For every selected parent and every arm:

- value model: byte-authenticated `WDL_CONTROL`
- 20,000 exact nodes
- `NodeLimitMode::Exact`
- threads = 1
- book OFF
- fresh `Engine`, TT and search state per parent
- same production search parameters
- no games and no self-play.

The generic scorer records the selected semantic move, score, node count, completed/effective depth, eval calls, cutoffs, D3 feature calls and wall time.

## Retrospective arms

- `CONTROL`: WDL_CONTROL + legacy production ordering, all runtime treatment env vars absent.
- `D3`: exact sealed D3 relational adapter + the same WDL_CONTROL, move-ordering only.

D3 provenance is the same sealed runtime candidate used by the terminal equal-node experiment:

- adapter job: `cpx62-1854-l3-decision-math-d3-relational-action-fit-v1`
- attempt: `20260907T073241Z-1bea99d0`
- adapter SHA256: `03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3`
- WDL_CONTROL SHA256: `e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`

The Gate 0 readout must not read D3 match results, Elo, W/D/L, autopsy score, or D4 results.

## Primary metrics

For each parent, Scan200k defines `scan_best = max sibling parent score`.

For each Jass arm:

- `scan_regret = scan_best - Scan200k(score of the sibling selected by Jass)`
- exact Scan top-hit: regret == 0 (ties count as hit)
- mean / median / p95 regret
- fraction regret >= 50 centi-score units
- mean completed depth
- mean eval calls
- median wall time.

Paired candidate-minus-control diagnostics:

- regret improvement = CONTROL regret - candidate regret (positive is better)
- top-hit delta
- completed-depth delta
- eval-call delta
- median fixture wall ratio candidate/control.

Bootstrap the mean regret improvement over parents:

- repetitions: 20,000
- seed: `2026090702`
- percentile 95% CI.

## Cheap GO rule for future candidates

A future candidate is `GATE0_SUPPORTED` only if all hold on the frozen 512-parent screen:

1. mean Scan regret improvement > 0;
2. bootstrap 95% LCB of regret improvement > 0;
3. exact Scan top-hit is not lower than CONTROL;
4. median wall-time ratio <= 1.05;
5. integrity/provenance/exact-node checks pass.

Otherwise it is `GATE0_NOT_SUPPORTED` and does not earn a large Elo gate from this screen alone. A later hypothesis may use a different preregistered proxy, but may not retune this screen after seeing results.

For the retrospective D3 validation, the only question is whether this rule would have prevented D3 from reaching the expensive match. No D3 scientific conclusion is reopened.

## D4 continuation

The current D4 offline experiment remains independent and unchanged. If D4 reaches its existing offline ESTABLISHED gate and a runtime candidate is implemented, run the same 512-parent Gate 0 before any strength match. D4 does not get special thresholds or a new cohort.

## Side effects

This Gate 0 campaign permits:

- identity-only selection from existing cohort;
- read-only reuse of existing Scan scores;
- exact-node Jass searches on 512 frozen parents per arm;
- aggregate benchmark publication.

It permits exactly:

- fits = 0
- Scan searches = 0
- strength games = 0
- self-play games = 0
- promotions = 0
- bakes = 0
- calibrations = 0
- retunes = 0
