# L3 CLS-G0 — Runtime catastrophe + CURRICULUM anchor contract V1

Date: 2026-09-16. Status: **prospectively frozen before the first CLS generation-1 candidate is trained, selected, runtime-scored or strength-tested**.

## 1. Upstream and purpose

This contract implements step 5 of `L3_CLOSED_LOOP_STRENGTH_CAMPAIGN_V1_20260910.md` after the terminal CLS-D bottleneck classification. The authenticated upstream production is fixed to:

- job: `cpx62-2015-l3-cls-bottleneck-classification-production-v1`;
- attempt: `20260916T205944Z-07fb94cc`;
- code SHA: `07fb94cc99798e1532abe276c287b7a3b19458ad`;
- launch receipt SHA256: `779c3123983682e7ff1650286bd57f869bb513c0bc2aa74d0e6f8d5689bb133a`;
- terminal: `CLS_DIAGNOSIS_COMPLETE_V1`;
- classification: `mixed`;
- supported axes: exactly `SEARCH` and `DECISION-EVAL`;
- scientific side effects: zero fits, zero target reads, zero strength games, zero alpha, zero promotion and zero bake.

Any upstream identity, receipt, terminal, classification, supported-axis or side-effect drift is a technical failure and invalidates admission under this contract.

The purpose of CLS-G0 is not to prove strength. It is a hard engineering/scientific screen that prevents a candidate with attractive offline fidelity from entering a fresh strength cohort if it catastrophically degrades runtime/search behavior.

## 2. Immutable anchor and parent rules

The immutable production anchor remains the exact `CURRICULUM` evaluator:

`SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

Rules:

1. CLS generation 1 direct parent is exactly this CURRICULUM byte identity.
2. Every later generation compares a child to its direct parent, but the exact CURRICULUM bytes above remain present in every strength gauntlet as the fixed drift sentinel.
3. No runtime, offline, teacher-fidelity or search-transfer result can replace, mutate, recalibrate or silently alias the CURRICULUM anchor.
4. Runtime G0 PASS authorizes only the next preregistered strength stage for that exact candidate; it never promotes or bakes a candidate.

## 3. Frozen runtime cohort and deep reference

G0 reuses only already-authenticated target-blind diagnostic roots; it does not create a candidate-dependent root selection.

Primary roots:

- exact FULL-512 DEEP512 root set/order from `cpx62-2000-l3-cls-depth-growth-full-production-v2`;
- 512 roots, exactly 128 per phase P0/P1/P2/P3;
- same board+STM identities and order; no post-candidate filtering.

Deep decision reference:

- exact same-current-Jass CURRICULUM 1,000,000-node reference from `cpx62-2008-l3-cls-mirror-scale-production-v3`;
- production attempt `20260916T161938Z-92984c1f`;
- launch receipt `2ac13b1e61dffc7d73217a8daba111aed9028b7a006020d081ebd6aa3480b004`.

The deep reference is read-only. No fresh Scan search and no fresh 1M parent search is required for G0.

## 4. Search/runtime identity

Candidate and direct parent must run through the same executable and identical search configuration. The only permitted semantic difference is evaluator bytes.

Frozen runtime configuration:

- single thread;
- opening book OFF;
- TT = 16 MiB, freshly cleared per root/arm;
- real EGDB enabled with the same path/cache for both arms;
- exact node-limit semantics;
- primary node budget = 200,000;
- no search parameter override, move-order policy override, pruning override, time-control adaptation or candidate-specific branch.

The candidate evaluator SHA is sealed before the G0 cohort is opened. Once G0 starts, the same candidate bytes must be used through all four gates. No refit, calibration, quantization change or retry with modified bytes is allowed.

## 5. Same-search nodes-to-depth requirement

True nodes-to-depth is mandatory and must come from the **same iterative-deepening search**, never from independent `go depth N` searches or interpolation.

Jass already exposes passive `SearchDecisionTrace` attempts with `depth`, `nodes_before`, `nodes_after`, completion state, fail-soft bound and root-action completion, plus the final public search receipt. G0 shall use that passive trace and must prove trace-on / trace-off parity for best move, score, completed depth, effective depth, node count and stop reason before any candidate is measured.

For each root, define the parent target depth prospectively as:

`d* = max(1, parent_completed_depth_at_200k - 1)`.

`nodes_to_d*` is the cumulative `nodes_after` of the **last** attempt at depth `d*` satisfying all of: `completed=true`, `bound=Exact`, and `all_actions_searched=true`. This excludes aspiration fail-high/fail-low attempts that finish a narrow window without completing the full root decision. If either arm has no such receipt for `d*`, that root is a hard nodes-to-depth failure. No surrogate is permitted.

## 6. Frozen statistical unit

All four runtime gates use the same 512 paired roots with phase-stratified bootstrap:

- bootstrap replicates: `100000`;
- seed: `2026091605`;
- resampling unit: root_id;
- phase quotas fixed at 128/phase;
- percentile interval: q025/q975 using NumPy Type-7 quantiles.

These are engineering catastrophe gates and spend no confirmatory alpha. Their thresholds cannot be changed after any CLS candidate byte exists.

## 7. Hard catastrophe gates

All four gates are conjunctive. Missing data, non-finite values, identity drift or incomplete traces are FAIL, never PASS-by-omission.

### G0-A — NPS floor

Per root compute `log(candidate_nps / parent_nps)` at exact 200k nodes. Bootstrap the phase-stratified mean and transform back to a ratio.

PASS iff:

`exp(q025(mean_log_ratio)) >= 0.80`.

Interpretation: with the frozen uncertainty rule, the candidate must retain at least 80% of parent node throughput. This is a catastrophe floor, not an optimization target.

### G0-B — completed nominal depth floor

Per root compute:

`candidate_completed_depth - parent_completed_depth`

at exact 200k nodes. Bootstrap the phase-stratified mean.

PASS iff:

`q025(mean_depth_delta) >= -1.0`.

A candidate whose supported mean loss can exceed one full completed nominal ply is stopped before strength testing.

### G0-C — same-search nodes-to-depth floor

For each root use the parent-defined `d*` from section 5 and compute:

`log(candidate_nodes_to_d* / parent_nodes_to_d*)`.

Every root must have a valid same-search `nodes_to_d*` in both arms. Bootstrap the phase-stratified mean and transform the q975 upper bound back to a ratio.

PASS iff:

`exp(q975(mean_log_nodes_to_depth_ratio)) <= 1.50`.

Thus the candidate may not require more than 1.5x parent nodes-to-depth under the frozen upper-confidence rule.

### G0-D — search-transfer quality floor

For each root, the immutable deep reference move is CURRICULUM at 1M nodes from the authenticated mirror-scale production.

Define two indicators at 200k:

- `I_candidate = 1(candidate_bestmove_200k == curriculum_bestmove_1m)`;
- `I_parent = 1(parent_bestmove_200k == curriculum_bestmove_1m)`.

Bootstrap the paired phase-stratified mean of `I_candidate - I_parent`.

PASS iff:

`q025(mean_agreement_delta) >= -0.05`.

This prevents a candidate from buying offline fidelity or throughput at the cost of a supported loss greater than five percentage points in transfer toward the fixed deep decision reference.

## 8. Decision rule

Exactly one G0 verdict is produced for an exact candidate SHA:

- all G0-A/B/C/D PASS -> `CLS_G0_RUNTIME_CATASTROPHE_GATE_PASS_V1`;
- otherwise -> `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1` and that candidate is terminal.

A failed candidate cannot be repaired by changing thresholds, roots, bootstrap seed, search config or CURRICULUM anchor. A materially changed candidate is a new campaign attempt with new preregistration; the G0 V1 thresholds remain unchanged unless a future protocol version is prospectively approved **before** that new candidate exists.

## 9. Strength boundary after G0

G0 never establishes external strength. A PASS allows only a separately preregistered paired color-reversed strength-at-time experiment.

That later strength contract must:

- use the exact G0 candidate bytes;
- include the direct parent as primary continuation opponent;
- include the immutable CURRICULUM SHA above as fixed drift sentinel, even when the direct parent is a later-generation child;
- size game count/SPRT boundaries only from already-measured CPX62 pair throughput and variance, and freeze them before any strength game is generated;
- forbid automatic promotion/bake from G0 alone.

## 10. Generation-1 boundary

After authenticated `CLS_DIAGNOSIS_COMPLETE_V1` and merge of this exact contract, CLS generation 1 may be **preregistered and implemented**. This document does not itself authorize an unregistered fit, strength game, promotion or bake.

Because the terminal diagnosis supports both SEARCH and DECISION-EVAL, the generation-1 learning experiment must preserve the master-plan requirement that any learning-objective attribution is prospectively defined and cannot use teacher fidelity alone as the continuation judge.
