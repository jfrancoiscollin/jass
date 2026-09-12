# ED4-FRESH-D — fresh decision source V1

Date: 2026-09-12. Status: preregistration before any D-source generation.
Parent protocol: `L3_ED4_FRESH_CONFIRMATION_V1_20260912.md`.

## Purpose

Implement only the score-free source stage for ED4-FRESH block D. This stage generates and seals identities; it performs zero Scan calls, zero evaluator calls, zero target reads, zero fits and zero games. It cannot produce an ED4 scientific verdict.

## Frozen population

Production generates the same structural roles as the established ED2/ED3 source mechanism: calibration=2/cell, decision=64/cell, reserved=32/cell over the 8 phase x STM cells. Only the `decision` block (512 parents total) is eligible for later ED4-FRESH-D confirmation. Calibration is timing-only; reserved is never confirmation.

Each independently restarted trajectory begins at the initial position, advances a uniformly selected legal move for a uniformly generated target length in 8..160 plies, requires >=9 pieces and 2..16 root legal moves, and accepts at most one endpoint from a trajectory. No model, teacher, WDL, score or candidate value is available to generation.

Master seed is the already frozen D seed `202609120401`. Split seeds are derived mechanically and prospectively as:
- calibration = `202609120401`
- decision = `202609120402`
- reserved = `202609120403`

This derivation is not tunable. The reserve master seed `202609120411` from the parent protocol, if its predeclared technical condition is met before any D target read, similarly maps to `+0/+1/+2`.

## Information boundary

The source output uses counted 38-byte JNNW records with the final five target bytes all zero. Published metadata may contain canonical identities, phase, STM, trajectory index, seed, row ownership and terminal/legal-move structural fields. It may not contain teacher scores, evaluator scores, WDL outcomes, qvalues or candidate-derived selection fields.

The stage must publish a cohort seal before any future target stage. The seal contains code SHA, generator identity/hash, exact master/split seeds, creation time, quotas, source-file hashes, canonical parent/child identity digest and explicit counters `target_reads=0`, `scan_searches=0`, `jass_searches=0`, `fits=0`.

## Validation

The validator must prove: counted JNNW integrity; target bytes zero; exact 8-cell quotas; phase/STM agreement with board bytes; 2..16 siblings; parent/child ownership alignment; unique `(seed,trajectory_index)`; no duplicate canonical identity within the generated source footprint; exact split seeds; and source.json counters all zero. Any failure is technical and consumes no confirmation target.

## Terminal

Success: `ED4_FRESH_D_SOURCE_SEALED_V1` with next stage `GENERATE_AND_SEAL_W_AND_S_SOURCES_OR_AUTHENTICATE_CROSS_BLOCK_DISJOINTNESS`.
Failure: `ED4_FRESH_D_SOURCE_TECHNICAL_FAILURE_V1`.

No automatic target scoring, no alpha spending, no promotion, no bake.