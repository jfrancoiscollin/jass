# L3 — Deep Search Sibling Distillation (general D) v1

Date: 2026-08-26. Status: **preregistered before any generalized sibling reanalysis labels, fit, holdout readout, or strength result**.

## Motivation

The exact tablebase-frontier experiment established that Jass can learn a decision/ranking function `D(s,m)` independently of the scalar value target `T(s)`:

- exact source: 15,763 symmetry-canonical 8-piece parents;
- holdout: 3,136 parents;
- CURRICULUM pairwise accuracy: 0.6124099820867199;
- learned D pairwise accuracy: 0.7058565278790088;
- D − CURRICULUM pairwise delta: +0.09344654579228878, bootstrap 95% CI [0.07505604277273002, 0.11191479096035059];
- exact top-hit delta: +0.0859375, bootstrap 95% CI [0.06584821428571429, 0.10602678571428571];
- all 16 label-sham controls were negative.

The tablebase supplied a perfect teacher, but the learning problem itself is not tablebase-specific. This experiment asks whether a **much more expensive search can act as the sibling-ranking teacher at arbitrary game phases**, so that its move preferences can be distilled into a cheap D head.

The current exact-TB move-ordering strength experiment remains separate. Its result does not change any parameter below.

## Scientific question

For a general position `s` with legal moves `m_1..m_k`, can a cheap state+move policy learn the ranking produced by a substantially more expensive, independently rerun search of every sibling child?

For every legal move:

```text
s --m_i--> child_i --fresh expensive search--> Q_teacher(s,m_i)
```

with parent-POV convention:

```text
Q_teacher(s,m_i) = - search(child_i).score
```

The target is therefore **relative action preference**, not a new scalar position value.

## What is deliberately NOT the primary target

Material gain, promotion, blocked-opponent counts, mobility changes, forced captures and final game WDL are recorded as diagnostics/auxiliary trajectory descriptors only. They do not define the primary label in v1.

Reason: a correct combination can lose material before winning. A hand-weighted target such as `material + promotion + mobility` would recreate the scalar-target problem and can systematically punish sacrifices.

Future trajectory-outcome work may add long-horizon rollouts after this search-teacher mechanism is established, but no rollout-derived coefficient is tuned in this experiment.

## Frozen source universe

Use the immutable MegaCorpus census already authenticated by jobs 1271/1272:

- census job `cpx62-1271-jass-megacorpus-r2-census-v4-resume5`;
- attempt `20260813T183125Z-801cb8fc`;
- catalog SHA256 `e5a6b6847a6c6e36c32e7c2dad3f8c6182a341044871a15a0cec2006f85c7334`;
- 1,264 catalog candidates, including 278 direct R2 candidates.

V1 uses the **direct R2 layer only**. Historical source scores/WDL are ignored. Only board state + side to move are read.

Candidates with census disposition `reject` are excluded. All other direct JNNW sources are eligible regardless of historical teacher/specialist/derived tags because their old labels are never consumed.

Byte-identical payloads are de-duplicated by declared SHA where available. Parent states are globally de-duplicated by exact board+STM and by the historical valid symmetry `rotate180 + colour swap` before sampling or splitting.

## Target-blind parent sampling

No teacher score may be read before parent selection.

Eligible parents satisfy:

1. total pieces between **9 and 40 inclusive** (the exact 8-piece TB-frontier support is excluded from the generalized primary corpus);
2. at least **2 legal moves**;
3. at most **16 legal moves** in v1, solely as a preregistered compute bound;
4. valid FMJD board and side to move;
5. exact/symmetry canonical state not already selected.

The selected corpus has exactly **8,000 parents**, target-blind and stratified by material phase:

- P0 opening: 30–40 pieces: 2,000;
- P1 midgame: 20–29 pieces: 2,000;
- P2 late game: 12–19 pieces: 2,000;
- P3 near-TB: 9–11 pieces: 2,000.

Within each phase, canonical candidates are ordered by:

```text
SHA256("2026083101:" + canonical_parent_fingerprint)
```

and the first eligible parents are selected. No outcome or current-model error influences this order.

## Leakage-safe split

The primary holdout boundary is **source-disjoint first, parent-disjoint second**.

Each distinct direct source payload is assigned by:

```text
u64_le(SHA256("2026083102:" + source_payload_identity)[0:8]) % 5
```

- bucket 0 = holdout source;
- buckets 1..4 = train source.

If the same canonical parent appears in both partitions because of derived/copy sources, the parent is assigned to holdout and removed from train.

Minimum support before any fit:

- >= 6,000 selected parents total after de-duplication;
- >= 1,000 holdout parents total;
- >= 200 holdout parents in each P0..P3 phase;
- both colours represented by >= 300 holdout parents;
- >= 1 stable sibling pair per accepted parent.

If support is below these thresholds, verdict is `DEEP_SIBLING_SUPPORT_NOT_ESTABLISHED`; no learner thresholds are lowered.

## Frozen teacher

Teacher engine:

- code: the current merged generalized-policy implementation lineage, pinned by the future control prereg job before reanalysis;
- leaf evaluator: byte-authenticated CURRICULUM raw SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`;
- opening book OFF;
- one search thread per sibling search;
- fresh TT / fresh search state for every sibling so earlier siblings cannot donate TT information to later siblings;
- exact node-budget mode;
- real EGDB enabled where available, but EGDB is not required for parent eligibility and is not the source of the generalized label;
- current frozen production search parameters, no per-phase retuning.

Every sibling is searched independently at **two preregistered exact node budgets**:

- teacher A: 50,000 nodes;
- teacher B: 200,000 nodes.

The same child is searched from a clean state at both budgets. Search order among siblings is canonicalized by semantic move identity and may not depend on the 50k/200k scores.

## Stable pair labels

For sibling pair `(i,j)`, define parent-POV deltas:

```text
d50  = Q50(s,m_i)  - Q50(s,m_j)
d200 = Q200(s,m_i) - Q200(s,m_j)
```

A non-terminal pair enters the training/evaluation label set only if:

1. `sign(d50) == sign(d200)`;
2. neither delta is zero;
3. `abs(d50) >= 10 cp`;
4. `abs(d200) >= 30 cp`.

Exact rule-terminal/TB outcomes take precedence over centipawn margins when they distinguish the siblings. A proven win > draw > loss relation is retained even if a finite search score margin is smaller.

The 50k search is a stability screen; the **200k ranking is the teacher target**. No threshold may be changed after label counts are known.

For diagnostics only, record per sibling:

- material delta after move;
- promotion flag;
- captured pieces/kings;
- legal move count of child;
- immediate forced-capture status;
- whether the child or searched PV enters EGDB;
- teacher completed/effective depth and node count.

These diagnostics never enter pair acceptance in v1 except for the exact terminal/TB precedence above.

## General D feature family

Reuse the demonstrated compact policy family:

- exactly 120 production `scan_eval::compute_extras(child)` features;
- plus 6 move-local features:
  - `num_captures`;
  - `captured_kings`;
  - `promotes`;
  - `moving_king`;
  - `from / 50.0`;
  - `to / 50.0`.

Total = **126 features**, separate white-parent and black-parent linear banks.

This intentionally tests whether the existing cheap feature family generalises beyond the exact TB frontier before introducing more capacity.

## Baselines

On untouched holdout parents, compare D against two frozen baselines:

1. **T baseline**: `-CURRICULUM(child)` scalar leaf score;
2. **cheap-search diagnostic baseline**: independent 5,000-node search per child with the same CURRICULUM leaf evaluator and fresh TT.

The T baseline is the preregistered primary comparison. Cheap search is diagnostic and cannot rescue a failed primary D gate.

## Learner

Same pairwise logistic family as the TB-frontier success:

```text
mean log(1 + exp(-w · (x_good - x_bad))) + 0.5 * 1e-3 * ||w||²
```

Frozen settings:

- separate white/black banks;
- L2 = 1e-3;
- L-BFGS-B;
- maxiter = 500;
- gtol = 1e-6;
- max 250,000 training pairs per colour, deterministic cap;
- zero initialization;
- 100,000 parent-cluster bootstrap resamples, seed `2026083103`;
- 16 label-sign shams, seed `2026083104`.

No PatternEval fit, no change to CURRICULUM, no policy-to-value blending.

## Phase-A learnability PASS gate

`DEEP_SIBLING_RANK_SIGNAL_ESTABLISHED` requires all of:

1. support gate established;
2. optimizer success for both colour banks;
3. D holdout pairwise accuracy >= 0.58;
4. D − T-baseline pairwise bootstrap 95% lower bound > 0;
5. D − T-baseline top-hit bootstrap 95% lower bound > 0;
6. D pairwise point delta vs T baseline > 0 in **each** P0, P1, P2 and P3 phase;
7. both colour-bank pairwise point deltas > 0;
8. true pairwise improvement exceeds every one of the 16 shams.

If support passes but any learnability gate fails, verdict is `DEEP_SIBLING_RANK_SIGNAL_NOT_ESTABLISHED`. No feature expansion, margin retuning or budget retuning is allowed inside v1.

## Phase-B confirmation if and only if Phase A passes

Before runtime search integration, generate a **fresh position holdout** independent of the historical R2 training corpus:

- 2,000 parent positions from fresh CURRICULUM play;
- target-blind phase quotas matching P0..P3 where reachable;
- teacher and stability rules unchanged (50k/200k, fresh TT, no book);
- zero refit after reading this confirmation set.

The already-fit D must again have positive pairwise point delta vs T in all represented phases and a global parent-bootstrap 95% lower bound > 0.

Failure closes v1 without strength games.

## Runtime experiment only after two learnability PASSes

The first runtime intervention remains deliberately narrow:

- CURRICULUM remains the only leaf evaluator;
- policy affects **capture sibling ordering only**;
- apply generalized D at capture parents with 9–40 pieces;
- TT priority, alpha/beta values, pruning thresholds, result semantics and legal moves remain unchanged;
- policy OFF is the exact baseline;
- native fixed-time strength is primary because it prices policy compute cost automatically;
- Q00 fixed-depth is diagnostic;
- no automatic promotion.

Quiet-move ordering is a separate future experiment because current quiet ordering already includes killer/countermove/history signals, whereas captures currently provide the cleanest causal seam.

## Trajectory-outcome extension (not part of v1 gate)

If deep-search sibling distillation is established, a subsequent preregistration may augment teacher evidence with fixed-policy rollouts and long-horizon outcomes such as:

- terminal W/D/L;
- tablebase entry/outcome;
- material swing;
- promotion;
- opponent mobility/blockade;
- horizon-specific outcomes H4/H8/H16/H32.

Those outcomes may be used to study *why* a move is good and to create a multi-horizon D, but v1 deliberately first tests the cleaner counterfactual teacher: expensive sibling reanalysis.

## Promotion / automatic continuation

- zero automatic promotion;
- no scalar refit;
- no modification of CURRICULUM;
- no threshold changes after labels or holdout are read;
- technical failures may be repaired without changing science;
- scientific FAIL is terminal for this exact target/feature/budget family.
