# L3 Decision Information — B3 fresh adaptive corpus v1 preregistration

Date: 2026-09-06

Status: **PREREGISTRATION — NO B3 FRESH SOURCE READ BEFORE FREEZE**

This document is the sole normative B3-v1 fresh-corpus delta after the real adaptive-teacher implementation parity gate. It freezes source generation, target-blind selection, exclusion, adaptive-teacher policy and the independent reference audit before any fresh B3 parent is generated.

It does not authorize model fitting, strength games, promotion or baking.

## 1. Immutable prerequisites

B3-v1 consumes the following already-terminal facts without reopening them.

### B2 confirmation

```text
job      cpx62-1831-l3-decision-math-b2-statistical-completion-legacy-support-json-compat-v3
attempt  20260906T105358Z-bebadf91
verdict  B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1
policy   M5=100 / M50=60 / minimum_survivors=2
```

### B3 real-teacher parity

```text
job      cpx62-1833-l3-decision-math-b3-real-adaptive-parity-rerun-v1
attempt  20260906T124918Z-7756fac9
verdict  B3_REAL_ADAPTIVE_TEACHER_PARITY_ESTABLISHED_V1
parents  4000
rows     37811
mismatch_count 0
```

The B3 parity stage authorized fresh generation but did not itself create any fresh B3 parent.

### Fresh exclusion preparation

```text
job      cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1
attempt  20260906T134208Z-c553a572
code     c553a572ed8ada9c49f8ebbefa3db22a9b6ca739
verdict  B3_FRESH_EXCLUSION_PREPARATION_COMPLETE
historical_count 223317
b2_count         4000
component_overlap 0
combined_count   227317
union_sha256      b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb
manifest_sha256   f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c
```

No identity in the fresh B3 selection may overlap this 227,317-position canonical universe.

## 2. Scientific question

B3-v1 asks only whether the already-confirmed and runtime-validated adaptive sibling teacher can produce a **new, target-blind, disjoint training corpus** with its real staged-search policy.

This is deliberately one-factor. B3-v1 does not search over margins, budgets, source recipe, cell balance, label definitions or teacher architecture.

## 3. Implementation X

The fresh-source implementation is the merged Jass commit containing:

```text
jobs/tools/adaptive_sibling_b3_fresh_source_runtime.py
jobs/tools/adaptive_sibling_b3_fresh_source_stage.py
```

The execution wrapper must authenticate X and this preregistration commit before launching source generation. Between X and the preregistration commit, the net diff is this document only. The runtime stage also authenticates the byte-pinned B2 target-blind source/selector/publisher components reused by the B3 adapter.

## 4. Frozen source generation

The source generator is the same recipe used for the successful B2 target-blind cohort, with **new seeds only**.

```text
source_shards          = 16
raw_records_per_shard  = 10000
raw_records_total      = 160000
source_seed_base       = 2026110800
source seeds           = 2026110800 .. 2026110815
selection_seed         = 2026110816
```

Per shard the generator remains:

```text
--gen-data-wdl 10000
source eval depth = 4
play depth        = 8
max plies         = 260
--wdl-zero-score
--random-open-plies 8
--explore-eps 8
--explore-decay-plies 60
--pair-openings
--drop-plycap
CURRICULUM = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

Source WDL/score target bytes are not selection inputs. Raw generator JNNW is scratch-only and is removed after publication exactly as in B2.

## 5. Frozen target-blind parent selection

The filter and selector retain the B2 structure:

```text
pieces                  = 9..40
semantic legal moves    = 2..16
canonicalization        = min(exact, rotate180_plus_colour_swap_and_invert_stm)
symmetry dedup          = before cell sampling
selection hash          = sha256(2026110816:canonical_fingerprint)
top_up                  = false
```

The eight fixed cells remain:

```text
P0 = 30..40 pieces, stm0 / stm1
P1 = 20..29 pieces, stm0 / stm1
P2 = 12..19 pieces, stm0 / stm1
P3 =  9..11 pieces, stm0 / stm1
```

Frozen quota:

```text
500 parents per cell
8 cells
4000 selected parents total
```

Insufficient support is a typed terminal B3 source outcome. No new seed, top-up, cell merge or quota reduction is allowed after source observations exist.

## 6. Machine-readable source contract

The following block is canonical JSON and is consumed directly by the B3 source stage. `derived_selection_contract_sha256` binds the exact B3 contract obtained by applying these frozen deltas to the byte-pinned B2 target-blind selection contract.

B3_FRESH_CORPUS_CONFIG_V1_BEGIN
{"audit":{"full_ladder_backfill_forbidden":true,"parents":1000,"per_cell":125,"seed":2026110817,"selection":"sha256(seed_decimal:canonical_fingerprint), lowest per cell"},"derived_selection_contract_sha256":"PENDING","exclusion":{"attempt_id":"20260906T134208Z-c553a572","code_sha":"c553a572ed8ada9c49f8ebbefa3db22a9b6ca739","job_id":"cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1","manifest_artifact_path":"artefacts/b3-fresh-exclusion-manifest.json","manifest_schema":"jass.adaptive_sibling_b3_fresh_exclusion_manifest.v1","manifest_sha256":"f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c","prefix":"r2:jass-data/runs/cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1/20260906T134208Z-c553a572","union_artifact_path":"artefacts/b3-fresh-exclusion-union.txt","union_sha256":"b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb","union_unique_canonical":227317,"universe":"DECISION_INFORMATION_B3_FRESH_V1_EXCLUSION"},"policy":{"M5":100,"M50":60,"minimum_survivors":2},"schema":"jass.b3_fresh_corpus_preregistration.v1","source_selection":{"cell_quota":500,"raw_records_per_shard":10000,"selected_parents":4000,"selection_seed":2026110816,"source_seed_base":2026110800,"source_shards":16,"top_up":false},"teacher_budgets_nodes":[5000,50000,200000]}
B3_FRESH_CORPUS_CONFIG_V1_END

## 7. Frozen real adaptive teacher

After the source-selection seal succeeds, the 4,000 fresh parents are evaluated by the already parity-established B3 teacher without modification.

```text
M5 = 100 cp
M50 = 60 cp
minimum_survivors = 2
q5   budget = 5000 exact nodes
q50  budget = 50000 exact nodes
q200 budget = 200000 exact nodes
threads = 1
TT = 16 MiB fresh Engine/TT for each executed search
book = off
node limit mode = exact
CURRICULUM unchanged
EGDB = on, explicit 256 MiB cache
JASS_* inherited environment count = 0
```

Exact/rule/TB shortcuts remain identical to B3 parity. Search sets must satisfy:

```text
q200_searches <= q50_searches <= q5_searches <= emitted_siblings
engine_constructions = q5_searches + q50_searches + q200_searches
```

The selected action is determined by the real adaptive policy only. Full-ladder reference observations are forbidden from influencing B3 adaptive allocation.

## 8. Corpus semantics

The B3 corpus is parent/action structured. For each fresh parent, the published adaptive ledger must retain:

- canonical parent identity and fixed cell;
- complete legal sibling/action identity;
- exact/rule/TB information;
- baseline value;
- q5/q50/q200 observations only where the adaptive policy actually executed them;
- searched/survived/selected flags;
- exact-shortcut / sole-survivor reason;
- uncertified flag when the frozen B3 policy defines it;
- real node cost.

Missing later-horizon observations are **structural missingness caused by allocation**, not zeros and not permission to substitute a reference value.

No full-ladder audit value may be copied into, backfilled into or used to relabel the adaptive corpus.

## 9. Independent full-ladder audit

A reference audit is frozen before any teacher score read.

```text
audit seed       = 2026110817
audit parents    = 1000
audit per cell   = 125
selection        = sha256(2026110817:canonical_fingerprint), lowest 125 per cell
```

The audit subset is selected from the sealed 4,000-parent source cohort using identities only. It is therefore target-blind.

The audit executes the B2-style complete 5k/50k/200k ladder on every legal sibling of those 1,000 parents in a **physically separate reference artifact family**.

Its purposes are measurement only:

- real adaptive node saving versus a contemporaneous full ladder;
- survivor/search rates by horizon and cell;
- selected-row equality rate;
- selected-value equivalence rate;
- conditional numeric deltas / large-delta rate;
- exact-shortcut and sole-survivor incidence;
- decisions per million teacher nodes.

B2 already supplied the prospective confirmation gates for 100/60/2 and B3 parity proved the real implementation. Therefore this B3 audit is **not a new tuning loop and has no post-hoc threshold search**. Audit metrics are published for transfer diagnostics and for the later C/D preregistration.

Any structural identity mismatch, exact-result contradiction, action-set mismatch or contamination/backfill is terminal invalid. Ordinary numeric disagreement is scientific evidence, not a technical failure and not permission to retune B3-v1.

## 10. B3 source verdicts

The source-selection stage has exactly two scientific outcomes once technical authentication succeeds:

```text
B3_FRESH_SOURCE_SELECTION_SEALED_V1
B3_FRESH_SOURCE_SELECTION_SUPPORT_NOT_ESTABLISHED_V1
```

`B3_FRESH_SOURCE_SELECTION_SEALED_V1` authorizes the already-fixed B3 adaptive-teacher stage on those exact 4,000 parent bytes.

Support-not-established is STOP. It does not authorize regeneration, new seeds, top-up or quota change.

## 11. B3 corpus completion boundary

A later B3 teacher/audit publication may declare the fresh corpus authenticated only if all structural contracts pass. That declaration may authorize creation of a SiblingDataset-v2 artifact for a separately preregistered downstream learning experiment.

It does **not** authorize:

```text
fits
calibration
model search
retuning M5/M50
strength games
promotion
bake
champion replacement
```

## 12. Information barriers

Before source selection is sealed:

```text
teacher score reads = 0
teacher label reads = 0
full-ladder audit reads = 0
```

Before the adaptive allocation decisions are sealed for a parent:

```text
q200 values for unallocated siblings are unreadable
reference-audit q50/q200 values are unreadable
```

Reference-audit artifacts and adaptive corpus artifacts remain separate through downstream packaging.

## 13. Technical repair rule

A technical failure may be repaired and requeued only if all scientific identities in this document remain fixed: implementation X, preregistration bytes, exclusion 1835 bytes, source/selection/audit seeds, source recipe, cell quotas, CURRICULUM, B3 teacher policy and budgets.

Technical incidents are capitalised automatically in the central incident ledger. No technical repair may be reclassified as a scientific result.

## 14. Execution order

The only authorized path after this preregistration is frozen is:

```text
1. B3 fresh source generation + target-blind filter/selection
2. source seal or typed support STOP
3. real B3 adaptive teacher on the sealed 4000 parents
4. target-blind 1000-parent audit subset seal
5. physically separate complete full-ladder audit
6. authenticated B3 corpus + transfer-diagnostic publication
7. STOP
```

No automatic fit, strength evaluation, promotion or bake follows B3-v1.
