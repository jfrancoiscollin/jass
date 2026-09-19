# CLS HIER — independent Scan reference diagnostic V1

Analysis protocol frozen before this diagnostic reads the historical Scan score
payloads. This is EXPLORATORY_CONSUMED_DATA, not a new confirmation experiment,
not a rerun of G0, and not permission to select, tune or promote a model.
JFC approved an independent evaluation of the disagreements after diagnostic 2064.

## Question and independence

For the two already-frozen choices on each of the FULL-512 roots, does the
external Scan evaluator prefer HIER's move, CURRICULUM's move, or neither at its
published precision? How stable is that comparison between 1M and 2M requested
nodes per child? The evaluator is independent of the two Jass parameter files;
the positions are NOT statistically independent fresh confirmation data. Scan
is an external_deep_reference, never ground truth. Native centi-Scan score gaps
are not Elo, win probabilities, or commensurate Jass centipawns.

## Immutable sources

- Decisions: cpx62-2063-l3-cls-g0-hier-runtime-rehearsal-v1,
  attempt 20260919T155826Z-a6f9fa6f,
  code a6f9fa6fbdc66f8d89dd7a5e8c196422cf98a28a,
  launch receipt a5b9a83a6a7932920ca23cf1cd7d15f67855c12835ddecb18c4f67bc9b0d6e59.
- Sibling identities and geometry: home-1651-l3-scan-ceiling-selection-v1,
  attempt 20260829T133348Z-28e12fba,
  code 28e12fba0ead14def244ffc442b15937f65edc0e.
- Historical Scan sibling scores: home-1658-l3-scan-ceiling-scan-deep-v1,
  attempt 20260829T152036Z-46623b26,
  code 46623b26b8d684f5685475d81fbb36f215ba4ac2.
- Cohort: 478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e.
- CURRICULUM: 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1.
- HIER: 95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628.
- Scan source: 7aae17e7b7bfc47744601afb1ee7655e18983ce5;
  binary 96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1.

Require completed immutable result identities, inventory/checksum consistency,
selection quarantine and hash chain, all 16 Score/Report shard pairs and pinned
Scan source/binary/runtime receipts. No substitutes, fresh searches, missing
shards or incomplete root/action coverage are accepted.

## Selection and joining BEFORE Scan score reads

Retain the exact G0 root order: 512 roots, 128 in each of P0/P1/P2/P3. Include
all 168 move disagreements and all 344 identical choices. Keep the 30 missing-G0
roots, including the 21 whose moves are unchanged. No root may be dropped,
resampled, ranked, or selected based on a Scan score or agreement stability.

Join G0 move strings using RAW board `from,to,captured_hex`, with bit i mapping
to square i+1. G0's `bestmove_canonical` is semantic capture-set notation, NOT
rotation/color canonicalization. Do not use `canonical_from/canonical_to` to
match it. Require exactly one sibling for each choice, full legal catalogues,
matching parent canonical fingerprints/phases, and every sibling at both budgets.
Write the complete score-blind join and its SHA before reading any Scan scores.
The historical sibling table includes legacy scalar columns; these are ignored,
not claimed to be absent. No Jass model, corpus binary or training target is read.

## Frozen descriptive analysis

Primary reference: Scan 2,000,000 requested nodes PER CHILD. Secondary stability
reference: Scan 1,000,000 requested nodes per child, always reported regardless
of whether it agrees with the primary. These are previously computed sibling
searches, not new parent-root searches. Source semantics remain stock Scan 3.1,
book off, 1 thread, bb-size 0, go analyze, fresh state per sibling/budget. Recorded
node counts are progressive snapshots, not invented final consumption totals.

For each root r, let p/h be the frozen parent/HIER choices, q_N the parent-POV
Scan score, and M_N the maximum q_N over ALL legal siblings. Report:

- delta_N(r) = q_N(h) - q_N(p); sign positive favors HIER under this reference;
- exact-score ties (integer published precision), separating same move from
  different moves with equal score; ties are never broken by sibling order;
- regret_parent = M_N - q_N(p), regret_hier = M_N - q_N(h);
- top-set membership at exact precision, with every tied best move accepted;
- counts and raw descriptive distributions on all roots, the disagreement
  subset, each phase, and G0 missing/present subsets with explicit denominators;
- 1M-to-2M sign transition table and exact top-set stability, WITHOUT filtering
  the primary results to a favorable stable subset.

Preserve native terminal score receipts and exact parent/child negation. Score
magnitudes, including extreme/terminal values, remain visible in the full table;
means are descriptive and may be dominated by these values. No significance
threshold, bootstrap, p-value, alpha spending, or global quality verdict is added.

## Boundary and outputs

Existing `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1` remains FAIL. CURRICULUM remains
champion. The August benchmark's training/tuning/calibration/model-selection/
runtime-scale/promotion quarantine remains active. The output cannot authorize
any learner or promotion; interpreting reference disagreement is not model
selection. No new searches, fits, matches or simulations are performed. Count
historical score rows explicitly; do not call them zero reference reads.

Outputs: score-blind join; full 512-row table with both budgets; descriptive JSON;
source authentication; manifest; RESULTS; structured summary; Launch-V2 phase
receipt. Terminal `CLS_HIER_SCAN_REFERENCE_DIAGNOSTIC_COMPLETE_V1` means the
DIAGNOSTIC completed, with scientific_verdict=null. Next action is
`INTERPRET_DIAGNOSTIC_NO_AUTOMATIC_REPLAY`.

## Operational contract and validation

CPX62, 16-CPU host identity, one stdlib reader; no native build/engine/shards.
Each selected object and expanded gzip is bounded at 32 MiB; 64 MiB per source.
Fresh scratch outside Git, at least 512 MiB free; hard stage cap 900 s and outer
cap 1500 s (not a completion forecast). The recent read-only diagnostic 2064
completed start-to-publication in 322 s; this is a different read workload and
no per-byte performance extrapolation is claimed. Only canonical hash-bound
Launch-V2 dispatch is permitted. Mandatory synthetic tests, including full main
with real StageEvidence and substituted transport, precede target-host execution.

Source code used for schema/semantics: `cls_g0_runtime_probe.cpp`,
`scan_ceiling_merge.py`, `scan_ceiling_scan_score.py`, `scan_ceiling_readout.py`.
Upstream contracts: `L3_CLS_G0_RUNTIME_CATASTROPHE_CONTRACT_V1_20260916.json` and
`L3_SCAN_CEILING_BENCHMARK_V1_20260829.md`. No existing contract/result is changed.
