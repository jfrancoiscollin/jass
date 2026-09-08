# ED3-P0 — TRAIN-only label-pressure diagnostic V1

User mandate: "Allez go et fait ce qu'il faut pour que le process de lancement
 des jobs soit plus robuste comme tu le proposes". Date: 2026-09-08.

## Scope and immutable history

ED2-N1 job 1878 / 20260908T191343Z-d71679e9 completed exit 0 with
`ED2_N1_PARTIAL_ORDER_VALUE_NOT_SUPPORTED_V1`. Its verdict and STOP_ED2 remain.
CURRICULUM remains champion. No old TEST or historical WDL holdout is a tuning
set. ED3 asks whether strict preference pressure may exaggerate otherwise useful
value differences. This is a proposed mechanism, not the diagnosed cause of ED2.

This implementation is the FIRST diagnostic step, not the ED3 learner. It uses
only already-computed TRAIN labels, native TRAIN/replay feature tables and the
sealed BASE/POINT/PARTIAL evaluators. It does not run a search, invoke an
optimizer, choose a checkpoint, generate data, or read held-out target values.

## Exact permitted inputs

- P0 1875 / 20260908T171140Z-bc30d685: `source/groups.tsv` for ownership/roles.
- N1 1878 / 20260908T191343Z-d71679e9: eight complete TRAIN shards, TRAIN seal
  and support, WDL selection/seal, BASE TRAIN/replay native tables, POINT/PARTIAL
  TRAIN native tables, and the two frozen candidate model files.
- BASE 1849 / 20260906T222203Z-08fd187a: WDL_CONTROL, SHA256
  `e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`.
- Context30 1340 / 20260814T123246Z-2ce07222: existing target sidecar; only the
  original 8192 replay row IDs are selected. Other target payloads are not
  interpreted or evaluated; transport/decompression is allowed and selection
  uses a memory-mapped array. No holdout metrics or selections are made.

Authenticate all sources through completed runner manifests/inventory/checksums.
Validate candidate hashes, label file hashes, source seal, original nonterminal
PARTIAL inequalities, exact TRAIN512/4976 children/17622 retained pairs, and eight
64-parent cells. Reconstruct candidate values from the native BASE feature path
and exact quantized coefficient delta and compare with retained candidate native
TRAIN outputs. A mismatch is technical failure, never missing-value imputation.

## Frozen descriptive measurements

Use the SAME PARTIAL-retained comparisons for all three evaluators. Each parent
has weight 1/512 and distributes it uniformly over its retained pairs. Report:

- weighted signed margin and absolute margin, and change versus BASE;
- the fraction of hard-label derivative mass on already-correct inequalities;
- derivative mass within fixed Scan50k gap bands (0,10], (10,50], (50,200], >200;
- hard-pair and replay-WDL gradient norms/cosine in the original 240 coordinates;
- original replay logloss/Brier reconstructed from native features, not a fresh
  native-heldout gate.

An empty diagnostic band is shown as unsupported/null, never a passing gate.
Hard-label derivative mass in margin space is not a parameter-gradient share.
Opposing gradients at a joint optimum are expected in many compromises: that
observation alone cannot establish causal harmful conflict or overconfidence.
No bootstrap significance, generalization claim, promotion or positive learning
verdict can emerge from these descriptive TRAIN quantities.

## Prospective soft-label scale rule, fixed before reading this diagnostic

For a later separately preregistered single soft candidate, use
`p=sigmoid(DeltaQ50k/tau)` on the SAME PARTIAL edges, where
`tau=weighted_median(positive retained TRAIN gaps)/log(3)` with original parent
weights and stable ascending sort. This maps the weighted median training gap
to preference 0.75. It is a train-only target-construction rule, not a fit to
TEST, a calibrated WDL probability or certified teacher confidence. No tau sweep
is authorized. Numerical saturation handling, solver stress rehearsal, fresh
TEST/holdout selection and full learner implementation remain to be frozen in
that learner's own prospective protocol BEFORE any new fit/evaluation.
The present diagnostic reports tau but does not fit or choose a model.

## Launch path and cost

The audit uses the new admission gate. First execute the entire audit as a
rehearsal on CPX62 via the original generic runner and real R2 fetch/publisher.
Then a production audit may run only after re-reading that exact successful
published receipt and output bytes. Same SHA, command, profile, runtime and
normalized spec. CI must execute the complete synthetic audit through the real
stage runner, publisher and verifier, plus deliberate failure cases.

Both audit modes: fits=0, new Scan/Jass searches=0, new positions=0,
strength/self-play games=0, TEST target reads=0, promotion/bake=0. The only cost is
artifact transport/decompression and bounded array statistics. No whole source
or native build tree is copied. The stage cap is 600 seconds and admission cap
is 1200 seconds including transport/tests; neither is a promised completion time.
The same-data audit rehearsal is NOT a rehearsal for a future training stage.

Terminal: `ED3_TRAIN_PRESSURE_DIAGNOSTIC_COMPLETE_V1`, classification
`EXPLORATORY_TRAIN_ONLY`, next `REVIEW_ED3_TRAIN_DIAGNOSTIC`. No automatic fit,
new Scan labels, new TEST, runtime experiment or Elo follows this stage.
