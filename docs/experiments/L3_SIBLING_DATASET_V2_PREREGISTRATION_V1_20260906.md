# L3 Decision Information — C SiblingDataset v2 preregistration

Date: 2026-09-06
Status: **PREREGISTRATION — DATA PACKAGING ONLY; NO FIT / MODEL SEARCH / STRENGTH**

## 1. Terminal prerequisite

Workstream C opens only because B3-v1 terminated structurally valid.

```text
job      cpx62-1844-l3-decision-math-b3-fresh-corpus-transfer-readout-v1
attempt  20260906T180342Z-37b46f2a
code     37b46f2a228af3d327782d7d59140fbe8ed1cd1d
state    completed
exit     0
next     C_SIBLING_DATASET_V2_PREREGISTRATION
```

Required terminal facts:

```text
fresh_b3_parents                    = 4000
adaptive_rows                       = 38053
audit_parents                       = 1000
audit_rows                          = 9409
structural_identity_checks          = PASS
action_set_checks                   = PASS
exact_result_consistency_checks     = PASS
executed_search_replay_checks       = PASS
adaptive_corpus_mutated             = false
reference_backfill                  = false
sibling_dataset_v2_creation_authorized = true
fits/model_search/strength/promotion/bake authorized = false
```

B3 transfer metrics are diagnostic context only and are not C gates or tuning targets. The terminal audit reported 40.7530629% real node saving, 94.5% selected-row equality, 96.1% selected-value equivalence, conditional numeric delta mean 0.6702768 cp, conditional >=100 cp rate 0.00120337 and maximum numeric delta 102 cp.

## 2. Scientific purpose

C makes the **parent decision** the first-class dataset unit. It does not attempt to improve an evaluation and does not choose a training loss.

The C artifact exists so that downstream D can compare WDL-only versus WDL + decision supervision on exactly the same parent clusters without reconstructing sibling structure from flat rows.

C is split into:

```text
C1  schema + reader/writer + validation contract
C2  converter from the authenticated B3 adaptive corpus
C3  parent-cluster split + symmetry-dedup/overlap proof
```

No C stage may run search, fit a model, tune a loss weight, select a candidate, play strength games, promote or bake.

## 3. Authoritative data inputs

Training-data content may be derived only from:

```text
B3 source cohort
  job     cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1
  attempt 20260906T141235Z-29084b25

B3 real adaptive teacher corpus
  job     cpx62-1841-l3-decision-math-b3-fresh-adaptive-teacher-rerun-v1
  attempt 20260906T154029Z-299779c0
```

The B3 terminal publication from 1844 is used only to authenticate that those inputs are authorized for C.

### Hard information barrier

The following artifacts are **forbidden as label/value inputs to C**:

```text
1843 b3-fresh-full-ladder-audit-groups.tsv
1843 q5/q50/q200 reference observations
1844 transfer-diagnostic mismatch/value fields derived from 1843
```

The 1842/1843 audit family remains measurement-only. No reference value may fill an unsearched adaptive horizon, relabel an adaptive action, determine a split or alter a training target.

## 4. SiblingDataset v2 logical schema

One record represents one parent and all of its semantic legal actions.

### 4.1 Parent identity

Required parent fields:

```text
schema
parent_id
canonical_parent_identity
raw_parent_identity
board_identity
rule_state_identity
search_context_identity
phase
stm
pieces
legal_action_count
cell
source_shard
source_row_index
source_selection_hash
```

Board, rule-state and search-context identities are distinct fields even when the current B3 source has trivial/default rule-state values. They may not be silently collapsed into one opaque key.

### 4.2 Action identity

Every semantic legal action is present exactly once and carries:

```text
local_action_index
from
to
captured_square_bitboard
num_captures
promotes
moving_king
captured_kings
material_count_delta_parent
child_identity
child_pieces
child_legal_moves
child_forced_capture
```

The converter reconstructs semantic move identity and child identity with production move generation from the sealed parent bytes. It must validate the B3 ledger columns against the reconstructed action before publication. Duplicate capture paths that reach the same semantic Move object must not gain extra weight.

### 4.3 Exactness and baseline

Per action:

```text
rule_terminal
child_tb_exact
exact_parent_utility
static_baseline_parent
```

`exact_parent_utility` is `-1/0/+1` when exact and `null` otherwise. Rule-terminal and TB-exact are mutually exclusive. Exact values may never be replaced by search values.

### 4.4 Adaptive search observations

For each horizon in `{5k,50k,200k}` store an observation object:

```text
observed
score_parent
nodes
completed_depth
effective_depth
aborted_iteration
stop_reason
elapsed_us
pv_enters_egdb
```

If the real adaptive policy did not execute a horizon, then:

```text
observed = false
all observation payload fields = null
```

Structural missingness is never encoded as numeric zero and is never backfilled from the full-ladder audit.

### 4.5 Allocation / decision state

Per action:

```text
searched5
searched50
searched200
survived5
survived50
selected
```

Per parent:

```text
exact_shortcut_reason
sole_survivor_reason
uncertified
policy = {M5:100,M50:60,minimum_survivors:2}
budgets_nodes = [5000,50000,200000]
real_teacher_nodes
```

Nested invariants remain:

```text
searched200 => searched50 => searched5
survived50  => survived5
selected count == 1
```

### 4.6 Optional decision-information fields

The v2 schema reserves explicit, typed containers for future SearchDecisionTrace information:

```text
search_bounds
certified_relations
stability
```

For B3-derived C-v1 conversion these fields must be empty/null unless the information exists in authenticated B3 inputs. They may not be inferred from missing horizons or from 1843 reference values.

### 4.7 Provenance

Every parent record carries or resolves through the dataset manifest to:

```text
source job/attempt/code SHA
adaptive teacher job/attempt/code SHA
B3 terminal job/attempt/code SHA
source parents JNNW SHA256
source ordered identities SHA256
adaptive groups SHA256
converter code SHA
schema version
config/preregistration SHA256
```

## 5. C1 — schema / reader / writer contract

Canonical serialization is newline-delimited canonical ASCII JSON (`jsonl`) for parent records plus one canonical manifest JSON.

Writer requirements:

- exclusive-create outputs; no overwrite;
- deterministic key ordering and LF termination;
- parent records sorted by `parent_id` 0..3999;
- actions sorted by `local_action_index`;
- exact type checking (`bool` is not accepted as integer);
- all 4,000 parents and all 38,053 adaptive sibling rows accounted for exactly once;
- fail closed on duplicate parent/action identity, missing parent, extra action, malformed observation or provenance drift.

Reader requirements mirror the writer and revalidate all cross-field invariants rather than trusting the manifest.

## 6. C2 — B3 converter contract

The converter may fetch/authenticate 1837, 1841 and the 1844 terminal authorization. It must not fetch 1843 reference groups.

Conversion sequence:

```text
1. authenticate 1844 terminal C authorization
2. authenticate exact 1837 source bytes
3. authenticate exact 1841 adaptive ledger bytes
4. reconstruct every parent from JNNW
5. generate and semantic-deduplicate legal moves with production movegen
6. join ledger rows to reconstructed actions in deterministic semantic order
7. verify child/action/exactness/search/allocation invariants
8. write SiblingDataset-v2 parent records
9. write canonical manifest and independent validation receipt
```

Any parent/action-set mismatch, exact contradiction, executed-search inconsistency or unauthorized reference read is terminal invalid. Ordinary score magnitude or disagreement is not a C failure.

## 7. C3 — parent-cluster split and overlap proof

The split unit is the parent cluster; sibling rows never split across partitions.

Because the B3 source is exactly 500 parents in each of 8 cells, C freezes an exact stratified split per cell:

```text
train = 400 parents per cell = 3200 total
valid =  50 parents per cell =  400 total
test  =  50 parents per cell =  400 total
```

Within each frozen cell order parents by:

```text
sha256("C_SIBLING_DATASET_V2_SPLIT_V1:" + canonical_parent_identity)
then canonical_parent_identity ASCII
then parent_id
```

Take first 400 train, next 50 valid, final 50 test.

The split is independent of teacher scores, adaptive survival, selected action, node cost and 1843 reference metrics.

Mandatory overlap proof:

```text
canonical parent identities unique globally
train ∩ valid = empty
train ∩ test  = empty
valid ∩ test  = empty
symmetry-canonical identity overlap across partitions = 0
all 4000 parents assigned exactly once
all 38053 sibling rows assigned through their parent only
```

## 8. C completion verdicts

C has structural outcomes only:

```text
C_SIBLING_DATASET_V2_AUTHENTICATED_V1
C_SIBLING_DATASET_V2_INVALID_V1
```

`AUTHENTICATED` requires C1/C2/C3 invariants and authorizes only a separately preregistered D learning experiment.

`INVALID` is STOP and does not authorize repairing data by importing 1843 reference values, changing split rules, dropping difficult parents or altering B3 labels.

## 9. Explicitly unauthorized actions

C does not authorize:

```text
fit
WDL/listwise lambda tuning
temperature tuning
Fisher/JFI anchoring
model search
feature search
strength games
equal-node gate
equal-time gate
promotion
bake
champion replacement
```

Those belong to later preregistered stages.

## 10. Execution order

```text
C1 schema + validator + reader/writer
 -> C2 converter + target-data rehearsal
 -> C3 deterministic parent split + overlap proof
 -> authenticated SiblingDataset-v2 artifact
 -> STOP
```

Only after terminal C authentication may D be preregistered.
