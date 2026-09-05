# PR #771 — B2 adaptive-sibling shadow confirmation preregistration v1

Date: 2026-09-05, Europe/Paris.

Status: **FROZEN CONFIRMATORY PREREGISTRATION**.

Schema identity: `jass.pr771_b2_preregistration.v1`.

This file is the sole normative delta from implementation commit X. It freezes
the prospective B2 confirmation before any fresh B2 parent generation or any
teacher score read. It does not itself launch compute.

## 0. Scientific question

B1 on historical material suggested that the fixed adaptive sibling policy can
save deep-search work while preserving the decision selected by the full
200k-node sibling reference. B2 asks whether that result reproduces on a fresh,
independently selected, target-blind parent cohort.

The hypothesis under test is exactly the already implemented policy:

```text
M5 = 100
M50 = 60
minimum_survivors = 2
```

No policy threshold, selector, cohort size, support threshold, statistical gate,
bootstrap seed, teacher budget, model, opening/data recipe or score treatment may
be changed after fresh B2 generation starts.

B2 is a confirmation/readout experiment only. It does not fit a model, play
strength games, promote a candidate, bake weights, or automatically start B3.

## 1. Immutable implementation X

The exact implementation commit executed by all B2 stages is:

```text
X = d3657332c3a5609a5501a9ff130f5d5c19488c7f
```

Y is the descendant commit containing this Markdown and no other repository
change relative to X. The source publisher authenticates that relationship
before fresh generation. All scientific tools executed at runtime are the X
blobs, not Y working-tree replacements.

Before the first teacher search, a later documentary commit S must contain only
the audited source/selection publication receipt F relative to Y. The mandatory
pre-read barrier authenticates:

```text
HEAD == X
X ancestor-of Y
Y ancestor-of S
diff(X,Y) == this Markdown only
diff(Y,S) == F receipt only
```

and re-hashes the fetched selection payloads before checking that all 20,000
target bytes remain zero.

## 2. Historical material is authentication/exclusion only

Historical B1 observations are not confirmation rows and are not pooled with B2.
They may be used only to authenticate the frozen implementation, exclude prior
parent identities, calibrate technical runtime envelopes, and verify the
projection implementation.

Frozen exclusion source:

```text
job      cpx62-1773-l3-decision-math-b2-historical-identities-v1
attempt  20260905T012244Z-1490b353
code     1490b3536f6943ec5eab62578ea7d42a29395a27
manifest sha256 2f1a551bf6fe020e6436689dc8ef8c95940f473d79a2ebc8613e6c15447cff16
union sha256    3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f
unique canonical identities = 223317
```

Any canonical overlap with this union is forbidden in the fresh B2 selected
cohort.

The historical projection-equivalence check and teacher smoke are implementation
validation only. Their scientific outcomes cannot enter the B2 confirmation
statistics or gates.

## 3. Champion/model identity

`CURRICULUM` remains the only evaluation network used by the source and teacher:

```text
raw SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
source job = cpx62-1341-jass-megacorpus-arm-d-fit-v1
attempt    = 20260814T191555Z-18c38a33
gzip SHA256 = 59114babe3724e17ce145616d23e34b8cd90459b7a8e0c224505d258c2b1e597
```

There is no model search, retuning, prior change, Scan weight read, Scan score
read, distillation, candidate promotion or alternate model arm in B2.

## 4. Fresh target-blind source generation

The source contract is the immutable X file:

```text
jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json
```

Its prospective source is exactly sixteen producer processes, each emitting
10,000 JNNW rows:

```text
source_shards = 16
raw_rows_per_shard = 10000
raw_rows_total = 160000
seed(shard) = 2026110700 + shard
shards = 0..15
```

Producer argv semantics are frozen by the contract:

```text
--gen-data-wdl 10000
eval_depth = 4
play_depth = 8
max_plies = 260
--wdl-zero-score
--random-open-plies 8
--explore-eps 8
--explore-decay-plies 60
--pair-openings
--drop-plycap
```

All sixteen producers are direct children held behind the published Linux
process barrier. Their JASS-prefixed environment is empty and the contract's
forbidden environment variables must be absent.

This producer can internally search/play to generate rows. Those generator
searches/games are not teacher observations and are not strength games.

## 5. Parent filter and target-blind selection

Each raw shard is filtered using only board/STM/legal-move structure:

```text
pieces in [9,40]
semantic legal moves in [2,16]
```

Selection is globally canonicalized under:

```text
min(exact, rotate180_plus_colour_swap_and_invert_stm)
```

Historical exclusion happens before sampling. Duplicate canonical states are
collapsed before cell selection.

The selection hash is frozen:

```text
algorithm = SHA256
selection_seed = 2026110716
payload = "2026110716:<canonical_fingerprint>"
```

Final cohort:

```text
parents = 4000
cells = 8
quota per cell = 500
cell order =
  P0_stm0 P0_stm1 P1_stm0 P1_stm1 P2_stm0 P2_stm1 P3_stm0 P3_stm1
phase P0 = pieces 30..40
phase P1 = pieces 20..29
phase P2 = pieces 12..19
phase P3 = pieces 9..11
```

ACTIVE top-up or any equivalent recovery is forbidden. The contract has
`top_up=false`.

If the authenticated target-blind population cannot supply the frozen 8x500
cohort, selection must terminate with the typed support route:

```text
B2_SOURCE_SELECTION_SUPPORT_NOT_ESTABLISHED_V1
```

No new seed, extra generation, relaxed quota, replacement population or teacher
read is allowed after that outcome.

Before teacher publication, F must prove:

```text
parents = 4000
forbidden_overlap = 0
target_blind = true
all output target bytes = 0
teacher_rows = 0
teacher_searches = 0
fits = 0
strength_games = 0
promotions = 0
bakes = 0
top_up = false
regeneration = false
new_seed = false
```

## 6. Source-stage operational pins

These values are plumbing fail-safes only. They were frozen before fresh B2 data
using historical/runtime calibration; they do not influence row ranking or any
scientific gate.

The producer deadline remains the previously reviewed 413 s bound derived from
the comparable CPX62 1578 chain (317 s x 1.3). Barrier and exec verification
remain 30 s each.

The 1777 historical calibration measured the 10k filter bound as 1 s. Therefore
launcher 540 s is frozen as a conservative composition of the bounded launcher
phases:

```text
30 barrier + 30 exec verification + 413 producer + 16 * 1 filter = 489 s
launcher bound = 540 s
```

The source publisher outer deadline is frozen at 1800 s. It is only a global
cleanup fail-safe around individually bounded Git/fetch/build/launcher/selector
steps and does not change their scientific outputs.

B2_SOURCE_OPERATIONAL_PINS_V1_BEGIN
{"filter_timeout_seconds":1,"launcher_timeout_seconds":540,"outer_timeout_seconds":1800,"schema":"jass.pr771_b2_source_operational_pins.v1"}
B2_SOURCE_OPERATIONAL_PINS_V1_END

A timeout is a technical failure. It is never converted into a scientific
support or confirmation verdict and may only be mechanically requeued with the
same frozen science and pins.

## 7. Mandatory source publication and pre-teacher barrier

A successful source/selection run publishes F under schema:

```text
jass.adaptive_sibling_b2_source_selection_publication.v1
verdict B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE
```

The 16 raw producer JNNWs are scratch-only and are deleted only after replay and
publication checks. The selected parents, metadata, ordered identities and
selection report are immutable portable payloads.

F is audited before teacher. Then S is created as a direct descendant of Y by
adding exactly the audited bytes of F and nothing else.

Immediately before the first teacher shard, X executes:

```text
jobs/tools/adaptive_sibling_b2_teacher_preread.py
```

It must publish:

```text
schema  jass.adaptive_sibling_b2_teacher_preread_auth.v1
status  VALID
verdict B2_TEACHER_PREREAD_AUTH_COMPLETE
target_bytes_nonzero = 0
teacher_scores_read = 0
teacher_searches = 0
```

Any failure of X/Y/S/F identity, local payload hashes, target-byte zeroing or
selection structure is technical/authentication failure and stops before teacher.

## 8. Full teacher observation

Only after the pre-read receipt succeeds may the fresh B2 teacher run.

Teacher semantics are fixed by X:

```text
parents = 4000
teacher shards = 16
book = OFF
threads per search = 1
TT = 16 MiB
fresh Engine per sibling per budget = true
fresh TT per search = true
node limit mode = exact
budgets = 5000, 50000, 200000 nodes
EGDB build = ON
EGDB cache = 256 MiB
EGDB configuration = explicit positional arguments
JASS_* inherited environment count = 0
```

Every legal sibling of every selected parent is observed. The teacher may not
prune the legal catalogue according to the adaptive policy: B2 needs the full
reference observations first, while the policy is replayed later from sealed
receipts.

Invalid selected-parent rows are fatal; duplicate semantic actions, missing
legal actions, extra actions, forbidden reordering, nonzero child targets or
failed parent->child transition verification are fatal.

The teacher merge must pass the native legal verifier and the post-search
publisher before allocation input is built.

## 9. Teacher operational bound from 1777

Historical parallel calibration:

```text
job      cpx62-1777-l3-decision-math-b2-parallel-calibration-v1
attempt  20260905T092718Z-82a9a093
code     82a9a09363e9480ed4d55bf2119a9aa687e1b3f9
verdict  B2_PARALLEL_TEACHER_AND_FILTER_CALIBRATION_COMPLETE
receipt SHA256 3bd16cf7a0d49b9c5aa3bdf45837e679846485297ea7aed3d8961fe37f316902
```

It used historical parents only, read no fresh B2 parent/teacher score for a
scientific decision and invoked no bootstrap.

Frozen full-teacher timeout:

```text
teacher_full_timeout_seconds = 390
```

The timeout is operational only. A timeout is a technical failure and does not
change the B2 verdict map or sample.

## 10. Sealed allocation policy and q200 noninterference

The allocation input and projection are the X implementations already validated
against historical B1.

The policy is exactly:

```text
M5 = 100
M50 = 60
minimum_survivors = 2
```

The policy may use the frozen q5k/q50 fields and allowed exact/terminal
information according to X. It must not decode q200 values/labels to decide who
receives 200k work.

`nodes200k` is a cost field, not a decision value. q200 reference values are read
only downstream for the sealed comparison after parent allocation receipts and
the projection manifest are immutable.

The following counters must remain zero through the allocation-policy boundary:

```text
q200_value_reads = 0
q200_label_reads = 0
q200_branches = 0
nodes200k_policy_reads = 0
nodes200k_policy_branches = 0
```

The projection manifest policy object must be byte-equivalent to:

```json
{"M5":100,"M50":60,"minimum_survivors":2}
```

No retuning after B2 observations is permitted.

## 11. Parent-level readout population

The analysis unit is the selected parent. Sibling rows are joined only through
the authenticated selection, semantic-action ledger, teacher merge, allocation
receipts and projection manifest.

The fixed readout publishes rich parent ledgers and then a sufficient projection.
The sufficient representation is the sole input to the statistical kernel.

Population identity remains 4,000 parents in the eight frozen 500-parent cells.
No historical B1 parent is added to the inferential sample.

## 12. Bootstrap and multiplicity

Frozen resampling:

```text
bootstrap replications = 200000
bootstrap seed = 2026110717
resampling unit = parent
```

Global confidence level is 95%.

For eight-cell simultaneous gates, family alpha is 0.05 and per-cell alpha is:

```text
0.05 / 8 = 0.00625
```

The implementation and synthetic statistical preflight in X define the exact
bootstrap, Clopper-Pearson and simultaneous-bound mechanics. No alternate CI,
continuity correction, resampling unit, seed, one-sided direction or multiplicity
rule may be chosen after observations are read.

## 13. Frozen support requirements

Scientific gates are evaluated only if all support requirements pass.

```text
fully-nonexact parents:
  global >= 2000
  each cell >= 100

numeric-eligible parents:
  global >= 1000
  each cell >= 50

full and shadow observations:
  each cell nonzero
```

A support violation produces:

```text
status = INVALID_UNKNOWN
scientific_gates_evaluated = false
verdict = B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1
```

No bootstrap result from an unsupported population may be interpreted as a
confirmation or refutation gate.

Structural authentication/schema/join/I/O failures remain technical failures,
not `INVALID_UNKNOWN` scientific support outcomes.

## 14. Frozen cell-level gates

All eight cells must simultaneously satisfy all of the following.

### 14.1 All-parent search saving

```text
simultaneous LCB95 saving >= 0.20 in every cell
```

### 14.2 Fully-nonexact search saving

```text
simultaneous LCB95 saving >= 0.20 in every cell
```

### 14.3 Value equivalence

```text
simultaneous Clopper-Pearson LCB95 >= 0.90 in every cell
```

### 14.4 Signal-event rate

For the eight cell rates, simultaneous Clopper-Pearson upper bounds must satisfy:

```text
mean(cell UCBs) <= 0.020
max(cell UCBs)  <= 0.040
```

### 14.5 Moderate numeric delta (1..99)

```text
bootstrap UCB95 <= 4.0 in every cell
```

### 14.6 Total numeric component

```text
bootstrap UCB95 <= 6.0 in every cell
```

### 14.7 Large numeric delta (>=100)

For the eight cell rates, simultaneous Clopper-Pearson upper bounds must satisfy:

```text
mean(cell UCBs) <= 0.015
max(cell UCBs)  <= 0.030
```

Failure of any required cell gate prevents confirmation.

## 15. Frozen global gates

The supported 4,000-parent population must also satisfy all global gates:

```text
all-parent saving LCB95              >= 0.30
fully-nonexact saving LCB95          >= 0.30
same-row rate LCB95                  >= 0.94
value-equivalence rate LCB95         >= 0.96
conditional numeric mean UCB95       <= 2.0
exact mismatch count                 == 0
maximum numeric delta                <= 1000
```

These are conjunctive with all cell gates. No weighted score, gate dropping or
post-hoc trade-off is allowed.

## 16. Terminal verdict map

The terminal mapping is closed and exact.

### Support not established

If authenticated population/statistical support is insufficient:

```text
B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1
```

### Policy not confirmed

If support is valid but at least one frozen scientific gate fails:

```text
B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1
```

### Policy confirmed

Only if support is valid and every frozen cell/global gate passes:

```text
B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1
```

No fourth scientific verdict is allowed.

## 17. Stop rule and forbidden downstream

Every terminal B2 verdict is a STOP for this preregistration.

```text
automatic_downstream_jobs = 0
fits = 0
strength_games = 0
promotion_authorized = false
bake_authorized = false
```

In particular, `B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1` does **not** authorize
B3 automatically. A later real adaptive-teacher experiment requires its own
explicit scientific preregistration and GO.

Technical failures may be repaired and requeued mechanically only when the exact
same X, Y, F/S identities (as applicable), cohort, seeds, model, policy, gates,
timeouts and outputs remain scientifically unchanged.

## 18. Execution order

The only authorized prospective path after Y is frozen is:

```text
1. fresh source generation + target-blind filter/selection at X using Y pins
2. source publication F or typed source-support STOP
3. remote audit of F
4. documentary S = Y + exact audited F bytes only
5. teacher pre-read authentication at X => B2_TEACHER_PREREAD_AUTH_COMPLETE
6. full teacher observation at X
7. native legal merge + teacher publication seal
8. allocation input seal (q200 opaque)
9. allocation receipts + projection manifest
10. rich -> sufficient readout
11. fixed 200000-parent-cluster bootstrap/statistics
12. terminal publication
13. STOP at the exact three-verdict map
```

No data-dependent change is authorized between these steps.
