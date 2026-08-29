# L3 Jass / Scan search-semantics attribution V1 — preregistration

Date: 2026-08-29. Status: **preregistered before Discovery A cohort generation and before every Discovery A Jass/Scan scientific score**.

Atlas source-only frozen first: [`L3_JASS_SCAN_SEARCH_SEMANTICS_ATLAS_20260829.md`](L3_JASS_SCAN_SEARCH_SEMANTICS_ATLAS_20260829.md).

## 0. Scientific question and hard separation

This HOME-only, benchmark-only campaign asks:

> Which identifiable, causally isolated search-semantics differences recover a reproducible fraction of the fresh same-budget Jass200k-to-Scan200k ranking gap while Jass evaluation bytes remain fixed?

It is independent of CPX62 T3-A runtime/strength. No HOME task may wait for, alter, cancel, reorder, or consume a CPX62 task or artifact. Every real campaign job is prefixed `home-`. A local micro-smoke may verify compilation and protocol only.

The immutable upstream motivation is the aggregate terminal of `home-1660-l3-scan-ceiling-readout-v1`, attempt `20260829T154532Z-46623b26`, code `46623b26b8d684f5685475d81fbb36f215ba4ac2`, verdict `JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED`, roadmap `JASS_SEARCH_SEMANTICS_PRIMARY`. Its cohort and all position-level scores are consumed and quarantined. This preregistration reads no upstream position or score to choose an axis, threshold, parent, move, or parameter.

Permanent guards:

```text
SCAN_BENCHMARK_ONLY=true
SEARCH_ATTRIBUTION_ONLY=true
HOME_ONLY=true
fits=0
refits=0
calibrations=0
feature_selections=0
model_selections=0
strength_games=0
bakes=0
promotions=0
T3_A_variant_searches=0
```

No Scan evaluator, weights, PST, feature, or score is imported into Jass. No training, distillation, calibration, parameter sweep or selection is authorized. The frozen Jass evaluator in every `J0/Ji` search is CURRICULUM/T0 SHA256:

```text
319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

## 1. Engine and source pins

### 1.1 Jass baseline

- source baseline used by the atlas: `cb91bec5c64b60f1084adb7c0c5459846f4624b1`;
- production default search parameters are materialized in full and hashed;
- `J0 = production Jass + frozen CURRICULUM + exact requested 200000-node cap`;
- book off, one thread, Jass TT `16 MiB`, fresh Engine/TT/search state for each sibling, arm and budget;
- production EGDB configuration remains identical across all Jass arms;
- no environment runtime policy or T3 model override is permitted.

The implementation commit may advance from the atlas source only to add default-off attribution switches, passive receipts, tests and runners. `J0` must pass byte-for-byte result replay against the pinned pre-attribution search on technical sentinels and default parameters must remain behaviorally unchanged.

### 1.2 Scan external reference

Unmodified official Scan 3.1:

```text
repository = https://github.com/rhalbersma/scan
commit = 7aae17e7b7bfc47744601afb1ee7655e18983ce5
tree = 023eace16a90ec543b6b6174c79cfc42488a356e
prior_HOME_binary_sha256 = 96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1
variant = normal
book = false
ponder = false
threads = 1
tt-size = 24
bb-size = 0
new-game = before every sibling/budget
command = go analyze
```

HOME first reauthenticates the prior binary. If unavailable or its SHA differs, HOME rebuilds unchanged sources at the frozen commit with the already authenticated official flags and must reproduce the same binary SHA. A non-byte-identical rebuild is a technical stop pending provenance resolution; Scan is never patched.

Scan receives the exact requested `level nodes=N`. Its stock one-thread counter/poll receipt follows the already frozen source-derived contract: requested nodes are exact commands, poll quantum is 16, and the last published `info nodes` snapshot must not exceed `ceil(N/16)*16`. It is never called the exact final consumed-node count.

## 2. Frozen causal arms

No arm was selected from a scientific score. The source-only atlas mechanically froze six axes. `Ji` changes exactly the named semantic relative to `J0`; all other evaluator, engine, runtime and search settings remain identical.

| Arm | Only treatment | Fixed source-derived implementation |
|---|---|---|
| `J0` | none | production Jass defaults |
| `J1_SCAN_VERIFY` | Scan verification pruning | enable exact same-position, same-STM probe at non-PV depth >=3; raised beta `10*depth`; 40% depth; phantom ply+1; no recursive verification |
| `J2_SCAN_THREAT_REENTRY` | exact threat-node semantics | replace only `qs_threat_ext` with same-position depth-1 main-search re-entry at first calm threatened qsearch ply |
| `J3_SCAN_SINGLE_REPLY` | single-reply extension | extend by exactly one at nodes with exactly one legal move; extension/reduction interplay follows frozen Scan |
| `J4_SCAN_LMR` | exact Scan LMR | depth >=2; zero-based PV move index >=3/non-PV >=1; quiet non-promotion only; reduction 2 only for non-PV index >=4 else 1; extension cancels reduction; Scan re-search contract; no Jass LMR shaping participates |
| `J5_SCAN_ORDERING` | exact Scan probabilistic ordering | per-search from/to table initialized 2048; TT 4095; captures included; good/bad EMA shift 5 on final best-over-original-alpha and all preceding tried moves; no killer/countermove/conthist contribution in this arm |
| `J6_NO_NULL_MOVE` | remove fictitious-pass pruning | disable null move only; every other Jass production pruning/reduction mechanism stays active |

Every new attribution switch is default `false` and disabled in production. Exact arm strings and their SHA256 digests are materialized before cohort generation. No override may be added, removed or changed after the first scientific score.

No sweep is permitted. In particular, there is no alternative LMR threshold, reduction, aspiration window, margin, depth, history shift, qsearch recursion cap, TT size or node budget.

## 3. Technical preflight before Discovery A

Technical sentinel positions are outside Discovery A and never contribute a scientific metric. Preflight must prove:

1. exact Jass board/STM to Scan Hub conversion and round trip;
2. one-to-one legal move identity including complete captured-square set, promotion and resulting child;
3. child-to-parent score sign and terminal utility;
4. deterministic replay after fresh state;
5. no book, one thread, fixed TT/EGDB settings and exact requested node configuration;
6. `J0` default-off equivalence to the pinned baseline;
7. same evaluator file bytes loaded by every arm;
8. same legal moves, terminal/TB metadata, root/child identities and node cap across Jass arms;
9. an activation sentinel for every treatment: verification probe, threat re-entry, single-reply extension, LMR reduction, ordering update, and baseline null probe removed only in J6;
10. all passive counters are internally coherent and do not change a default-off replay.

Any ambiguous move map, POV failure, inactive treatment, asymmetry, evaluator drift, unexpected non-axis diff, non-determinism or Scan provenance failure stops before cohort generation. The smoke publishes no accuracy, top-hit or rank statistic.

## 4. Fresh Discovery A cohort

Exactly `512` parents:

```text
P0 = 128 parents, 30..40 pieces
P1 = 128 parents, 20..29 pieces
P2 = 128 parents, 12..19 pieces
P3 = 128 parents,  9..11 pieces
legal moves = 2..16 inclusive
legal = true
terminal = false
```

Selection is target-blind. No Jass or Scan score/eval is read during source generation, filtering, deduplication, exclusion or quota selection.

Frozen random contract:

```text
source_seed_base = 2026091410
source_seed(shard i) = 2026091410 + i, i in [0,15]
selection_seed = 2026091401
subset_hash_seed = 2026091402
bootstrap_seed = 2026091403
RNG = numpy.random.Generator(numpy.random.PCG64(seed))
```

Each phase's eligible candidates are ordered by `SHA256("L3_SEARCH_SEMANTICS_DISCOVERY_A_V1" || selection_seed || canonical_identity)` and the first 128 are selected. Source volume and seeds are fixed. If quotas cannot be filled, selection fails; no seed, constraint or parent is replaced.

Identity and deduplication:

- exact board+STM deduplication;
- canonical identity is the lexicographically smaller serialized `(board,STM)` of the original and rotate180+colour-swap representation, using the established Jass convention;
- canonical deduplication before quotas;
- overlap with the immutable exclusion snapshot must equal zero.

### 4.1 Exclusion snapshot and cutoff

Identity-only exclusion cutoff:

```text
cutoff_local = 2026-08-29T18:40:13+02:00
jass_code_floor = cb91bec5c64b60f1084adb7c0c5459846f4624b1
jass_control_origin_main = 2c581c640876269cf18d70906b5b6051394e89b1
```

The snapshot includes canonical identities, never scores/labels, from at least:

- consumed Scan ceiling jobs 1651 through 1660;
- historical T3 A/B/C training;
- Q1, T2 fresh, RF1 fresh 1633, T3 fresh 1638;
- M1/M2/M3/M5 and every other M cohort;
- Rich-D fresh and DSSD confirmation;
- R0 runtime and every T3-A runtime pool created by cutoff;
- all force pools and known strength/opening pools by cutoff;
- every scientific cohort known by cutoff.

The selector inventories repositories/control-plane and immutable object-store manifests, publishes every included source URI/job/attempt/code/cohort SHA, per-source identity count, merged canonical count and a SHA256 of the sorted exclusion set. A mandatory source missing or unauthenticated is a technical stop, not permission to weaken exclusions. Later artifacts do not mutate Discovery A, but their future selection must exclude Discovery A once its identity SHA is published.

## 5. Nested subset fixed before scores

`DEEP128` contains exactly 128 Discovery A parents, 32 per phase. Within each phase, sort selected parents by:

```text
SHA256("L3_SEARCH_SEMANTICS_DEEP128_V1" || subset_hash_seed || canonical_identity)
```

and take the first 32. The subset is published with parent identities and SHA before every scientific score. No score participates.

## 6. Score ladder and immutable search state

### 6.1 All Discovery A siblings

For every legal sibling of all 512 parents:

- Scan50k, requested 50,000 nodes — lower-budget diagnostic;
- Scan200k, requested 200,000 nodes — **primary reference**;
- J0 and J1..J6, exact 200,000 Jass nodes.

### 6.2 DEEP128 only

- Scan2M, requested 2,000,000 nodes — secondary deep reference;
- J0 1M, exact 1,000,000 Jass nodes — secondary budget comparator;
- existing J0/J1..J6 200k scores are evaluated against Scan2M as secondary agreement contrasts.

No Ji 1M score is generated in Discovery A. No budget may be added or changed after reading a score.

Each sibling/arm/budget uses fresh engine, TT and search state. Book is off, one thread/search, same Jass TT size and EGDB, same Scan options, and parent POV. Terminal/TB exact siblings retain the common exact handling and zero searched nodes; every such line is marked.

Scoring is resumable and sharded. Selection, Jass arms, Scan50k/200k, Scan2M/J0-1M and readout are separate immutable stages. Every shard manifest contains input SHA, code SHA, engine/evaluator SHA, arm SHA, row range/hash, budget, receipts, output SHA and `benchmark_only=true`. A retry resumes missing/invalid shards only; a slow sibling is never replaced.

Discovery A identities and all its scores become permanently consumed at the first scientific score generation. They are prohibited from all future training, tuning, feature/model/parameter selection, calibration or production promotion.

## 7. Pairwise and ranking contract

For each parent enumerate all unordered sibling pairs by canonical sibling identity.

Against a given Scan reference:

- distinct exact reference scores: comparable primary pair;
- exactly tied reference scores: exclude the pair from primary pairwise accuracy;
- correct direction = `1`, incorrect = `0`, Ji/J0 signal tie on a reference-distinct pair = `0.5`;
- no score margin, epsilon or post-hoc threshold.

Primary top-hit resolves the signal's own exact top tie by selecting the smallest canonical sibling identity, then scores `1` if that choice is in Scan's exact top-tie set. A strict diagnostic tie-breaks both signal and reference by canonical identity. It never replaces the primary.

Per signal/reference publish:

- pairwise accuracy;
- top-hit;
- parent-macro Kendall tau-b and Spearman rho where defined;
- total/comparable/tied pairs and admissible/NA parent counts;
- P0/P1/P2/P3, black/white STM, branching and piece-count breakdowns.

Fixed strata:

```text
branching = 2..4 | 5..8 | 9..12 | 13..16
pieces    = 9..11 | 12..15 | 16..19 | 20..24 | 25..29 | 30..34 | 35..40
colour    = black | white parent STM
```

Global pairwise accuracy is weighted by comparable pairs. Top-hit is parent mean. Rank correlations are computed per parent with standard tie handling, then macro-averaged over defined parents.

## 8. Primary causal estimand, bootstrap and multiplicity

For axis `i`:

```text
A0 = accuracy(J0, Scan200k_reference)
Ai = accuracy(Ji, Scan200k_reference)
delta_i = Ai - A0
```

Parent-cluster paired bootstrap:

```text
samples = 200000
seed = 2026091403
CI95 = percentile [2.5%, 97.5%]
```

Parents are sampled with replacement; all their siblings/pairs travel together. Each replicate recomputes numerator and denominator. A zero denominator is NA and counted. All arm deltas use the same parent index draws.

For multiplicity, compute the preregistered one-sided bootstrap sign-tail for `H0: delta_i <= 0`:

```text
p_i = (1 + count(delta_i_bootstrap <= 0)) / (200000 + 1)
```

Apply Holm step-down at family-wise `alpha=0.05` to the six primary p-values only, sorted ascending with Axis ID as deterministic tie-break. Report raw p, Holm adjusted p, rejection status and the unadjusted percentile CI95. Secondary metrics/references never enter or rescue this family.

### 8.1 Major-subgroup catastrophe guard

Major subgroups are the four phases and two colours, provided a subgroup has at least 32 parents and 200 comparable pairs. A treatment is `clearly_catastrophic` if its paired delta CI95 upper bound is below `-0.0100`. Branching/piece strata remain diagnostics and do not add post-hoc gates.

### 8.2 Axis PASS rule

Axis `i` is `SEARCH_SEMANTICS_AXIS_ESTABLISHED` only if all are true:

1. `delta_i > 0`;
2. unadjusted paired parent-cluster CI95 low `> 0`;
3. Holm rejects its primary null at family-wise 0.05;
4. all technical contracts pass and its treatment demonstrably activates;
5. no major subgroup is `clearly_catastrophic`;
6. source diff and artifact manifests prove no modification outside the axis.

Top-hit, rank correlations, Scan2M and J0-1M are secondary and cannot create PASS. Failure of primary pairwise is negative/inconclusive for the axis.

## 9. Gap recovery, fixed before scores

Two descriptive quantities are reported, never as Elo or engine-strength equality.

### 9.1 Absolute-reference remaining gap closure

```text
absolute_gap_recovery_i = (Ai - A0) / (1 - A0)
```

Guard `NA` if `1-A0 <= 0`. The value is explicitly called descriptive because self-agreement of the reference is trivial.

### 9.2 Lower-budget practical same-reference closure

Let:

```text
A_scan50 = accuracy(Scan50k, Scan200k_reference)
same_budget_gap_closed_i = (Ai - A0) / (A_scan50 - A0)
```

Guard `NA` if `A_scan50 - A0 <= 0`. This denominator places the causal gain against a real lower-budget Scan signal evaluated by the same Scan200k reference. It is more interpretable than the trivial ceiling but remains a ranking-agreement descriptor, not force or Elo.

Report point estimates and paired parent-bootstrap CI95 for numerators and ratios, with ratio replicates NA whenever their denominator is non-positive.

## 10. Secondary deep analysis

On DEEP128, recompute every J0/Ji 200k agreement against Scan2M, with paired deltas and raw CI95 only. Also publish:

- Scan200k versus Scan2M agreement;
- J0 200k versus Scan2M;
- J0 1M versus Scan2M;
- `delta_i(Scan2M)` beside primary `delta_i(Scan200k)`.

This checks whether a primary gain also points toward a deeper external reference and compares the magnitude with a 5x Jass budget. It cannot save a primary failure and receives no separate establishment label.

## 11. Runtime/search receipts

For every Jass arm and budget publish aggregate and distributional:

- requested/reported nodes and stop reason;
- completed/effective depth;
- wall time and NPS diagnostic;
- eval calls;
- qsearch calls and qnodes;
- TT probes/hits;
- cutoffs and first-move cutoffs;
- reductions, reduced plies and LMR re-searches;
- extensions by kind;
- verification probes/cutoffs;
- threat re-entries;
- null probes/cutoffs;
- ordering good/bad updates.

Wall clock is diagnostic HOME performance only and is never mixed with CPX force/runtime. The primary remains node-budget pairwise.

## 12. Discovery A terminal decision

If no axis passes §8.2:

```text
NO_SINGLE_SEARCH_SEMANTICS_AXIS_ESTABLISHED
```

Scientific stop. No combinatorial or best-looking post-hoc arm is launched. The descriptive interpretation may be that simple isolated differences are insufficient and interactions/evaluation should be tested only under a future preregistration.

If at least one axis passes:

```text
SINGLE_SEARCH_SEMANTICS_AXIS_ESTABLISHED
```

Proceed to a separate, merged-before-selection composite-confirmation preregistration. The composite must contain **all and only** passed axes, in ascending Axis ID order. There is no manual choice, retune or optimization. Technical incompatibility stops and is documented.

Global `SEARCH_SEMANTICS_ATTRIBUTION_TECHNICALLY_INCONCLUSIVE` is reserved for an unresolved mapping/provenance/evaluator/arm-isolation or incomplete-reference failure that invalidates the scientific contract; it is not used for a small or null effect.

## 13. Conditional composite contract (not authorization to score yet)

Only §12 PASS authorizes writing and merging:

`docs/experiments/L3_JASS_SCAN_SEARCH_SEMANTICS_COMPOSITE_CONFIRMATION_V1_20260829.md`

before a fresh Confirm B cohort. Confirm B will use exactly 1024 parents, 256/phase, fresh seeds fixed in that separate preregistration, all Discovery A identities excluded, J0/composite 200k versus Scan200k primary, 200000 parent bootstraps, and a pre-score DEEP256 with J0/composite 200k/1M and Scan200k/1M/2M. No Confirm B position or score may exist before that document is merged.

## 14. Terminal documentation and immutability

At Discovery terminal create a dedicated result memo and update without changing older verdicts:

- `docs/L3_CURRENT.md`;
- `docs/L3_TEACHER_DISTILLATION_ROADMAP.md`;
- `docs/L3_SCIENTIFIC_SYNTHESIS_20260829.md`.

The lineage remains explicit:

```text
F6: representation bottleneck established
T3-A: distillation transfer established
Scan ceiling: teacher/search Jass has large external headroom
Search semantics attribution: independent HOME benchmark-only causal branch
```

Every stage manifest repeats `strength_games=0`, `bake=false`, `promotion=false`. Even a confirmed composite remains experimental and never changes production automatically.

## 15. Preregistration guard receipt

At document creation:

```text
Discovery_A_parents_generated = 0
Discovery_A_Scan_scores = 0
Discovery_A_Jass_scores = 0
consumed_Scan_ceiling_positions_read = 0
fits = 0
strength_games = 0
```

