# L3 Adaptive Shadow B2 — Statistical Completion Recovery V1

Date: 2026-09-06

## Purpose

Complete the already-frozen B2 confirmation without generating new scientific data and without changing the adaptive policy.

The original B2 terminalization stopped fail-closed after an authenticated readout-build failure before any production statistics were run. This recovery exists only to complete the preregistered readout/statistical stage on the immutable B2 evidence.

## Immutable scientific inputs

- implementation X: `d3657332c3a5609a5501a9ff130f5d5c19488c7f`
- preregistration Y: `b382cd4b1d8b9b632bcaf500156a6e827e114527`
- target-blind source selection: `cpx62-1778-l3-decision-math-b2-source-selection-v1`, attempt `20260905T102917Z-d3657332`
- full teacher/merge publication: `cpx62-1801-l3-decision-math-b2-full-teacher-publish-empty-artifact-repair-v1`, attempt `20260905T214101Z-d3657332`
- failed terminal bundle to recover: `cpx62-1815-l3-decision-math-b2-allocation-readout-terminal-historical-receipt-serialization-repair-v1`, attempt `20260906T002518Z-d3657332`
- authenticated 1815 failure: `PROJECTION_BINDING_INVALID`, stage `PROJECTION_RECEIPT`, parent `1216`; production statistics invocations and bootstrap draws were zero.

No new source parent, teacher search, fit, calibration, strength game, promotion, bake, or policy/model selection is allowed.

## Frozen policy and statistics

Unchanged from Y:

- `M5 = 100`
- `M50 = 60`
- `minimum_survivors = 2`
- production bootstrap replications `R = 200000`
- bootstrap seed `2026110717`
- same support gates, global gates, simultaneous cell gates, value-equivalence rules, signal-family rules, numeric-delta rules, exact-mismatch rule, and maximum-delta rule.

The terminal verdict set remains exactly:

- `B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1`
- `B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1`
- `B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1`

Every verdict remains terminal STOP. B3 is never launched automatically.

## Recovery boundary

The 1815 bundle must first authenticate byte-for-byte through the existing X common/readout contracts.

A binding repair is permitted only when all of the following hold for every affected parent:

1. the allocation object is canonical and authenticated;
2. the stored receipt and a fresh deterministic X projection agree exactly on every policy-visible and cost field:
   `ordered_rows`, `S5_rows`, `S50_rows`, `S200_charge_rows`, `pre_q200_choice_row_or_null`, exact/sole-survivor reasons, uncertified flag, `shadow_nodes5`, `shadow_nodes50`, `shadow_nodes200`, `shadow_nodes_total`, and all q200/noninterference counters;
3. no q200 value/label/policy read or branch is introduced;
4. any difference is confined to the three cryptographic binding fields `projection_input_sha256`, `decision_input_sha256`, `decision_output_sha256` and the projection manifest catalogue derived from them;
5. repaired binding hashes are recomputed from the exact authenticated allocation line, decision view, and sealed decision object;
6. the recovered projection manifest is regenerated deterministically and rebound into a new readout-input manifest;
7. the full X readout must then pass with no classified build failure before the production bootstrap may start.

If any policy/cost/counter field differs, or if the recovery would need to modify teacher rows, allocation decisions, q200 values/labels, support thresholds, seeds, or gates, the recovery MUST stop technically and no scientific verdict is produced.

## Infrastructure gate

The new execution architecture is established before this recovery:

- Level-1 synthetic contract rehearsal PASS;
- Level-2 CPX target-host rehearsal PASS;
- Level-3 full-pipeline rehearsal `cpx62-1824-infra-b2-full-pipeline-rehearsal-v3`, attempt `20260906T070803Z-7f740b8e`, completed exit 0 with authenticated inputs/outputs and `B3_INFRASTRUCTURE_READY`.

The recovery must run through `jass.stage_spec.v1` and the generic observable stage runner. Any failure must expose `failure_stage`/`failure_class` in GitOps status; no diagnostic-only retry chain is allowed.

## Terminal publication

On successful rich/sufficient readout, run the existing production statistical analyzer unchanged and the existing X terminal publisher unchanged. Publish the exact statistics/progress/terminal receipt when available, the recovery audit, zero-side-effect guards, and the exact terminal verdict.

The recovery itself does not authorize B3. A positive B2 result only establishes the scientific prerequisite for a separately authorized B3 campaign.
