# Jass target-data preflight standard v1 — 2026-09-06

## Purpose

Prevent a full scientific stage from being the first execution that exercises a real immutable producer/consumer contract on the target host.

This standard was introduced after B2 recovery job 1826 proved that a synthetic/full-pipeline rehearsal can be green while an edge case in a real frozen dataset still violates a downstream consumer invariant.

## Mandatory gate

For any stage that consumes an immutable external result bundle and can subsequently execute expensive or scientifically decisive work, the execution sequence is:

1. **Synthetic contract rehearsal** in CI.
2. **Target-data admissibility preflight** on the target host, using the exact immutable input identities and exact executable toolchain intended for the scientific run.
3. **Full scientific stage** only when the target-data preflight publishes an authenticated PASS receipt.

The full scientific stage MUST NOT be queued merely because CI or a synthetic rehearsal is green.

## What the target-data preflight must do

A target-data preflight must:

- authenticate exact source job, attempt, code SHA and file descriptors;
- exercise the real producer/consumer boundary on every relevant record, or prove an equivalent exhaustive contract check;
- publish the first exact divergence with record/parent identity, typed failure class/stage and a stable human-readable invariant message;
- emit a bounded field-level diff when two supposedly equivalent payloads differ;
- use the same target host/runtime capability set required by the full stage;
- execute zero fit, strength game, promotion, bake or scientific bootstrap unless the preflight itself is the preregistered scientific operation;
- publish a machine-readable receipt and `scientific-summary.json` through the status bridge.

## Fail-closed rule

A preflight result is either:

- `PASS`: the exact target-data contract is admissible and the declared next scientific stage may be prepared; or
- `BLOCKED`: a contract divergence exists; the full scientific stage remains forbidden; or
- technical failure: infrastructure must be repaired and the preflight rerun before any scientific stage.

A `BLOCKED` preflight is not a negative scientific verdict.

## Diagnostic quality

Generic categories such as `PROJECTION_BINDING_INVALID` are insufficient as the only observable output when multiple invariants share that category. The preflight must preserve the underlying invariant message (for example `shadow cost differs from sealed allocation receipt`) and the exact record identity.

## B2 recovery application

For frozen B2, the mandatory gate is `adaptive_sibling_b2_recovery_admissibility_preflight.py`.

It authenticates the immutable 1815 failure/bundle, evaluates the X readout consumer parent-by-parent, then feeds the same parent through a fresh deterministic X projection and the same X consumer. It classifies the first divergence as one of:

- `STALE_BINDING_METADATA_ONLY` — potentially admissible for the existing narrow recovery;
- `PRODUCER_CONSUMER_CONTRACT_MISMATCH` — blocked; producer and consumer disagree even on fresh output;
- `NON_BINDING_RECEIPT_DRIFT` — blocked; science/cost/decision payload differs outside approved binding hashes;
- another explicit blocked state.

The B2 bootstrap (`R=200000`, seed `2026110717`) is forbidden until this preflight publishes `B2_RECOVERY_ADMISSIBILITY_PASS`.

## Generalization

New campaigns should implement target-data preflights whenever their real immutable input distribution can exercise states not exhaustively represented by synthetic fixtures. Every real-data-only failure discovered later must be converted into either:

- a synthetic regression fixture if the edge case can be represented safely; or
- a permanent target-data admissibility invariant when it depends on immutable external evidence/runtime.

This rule complements, and does not replace, the stage-spec, stage-receipt, object-store capability and synthetic/full-pipeline rehearsal contracts.
