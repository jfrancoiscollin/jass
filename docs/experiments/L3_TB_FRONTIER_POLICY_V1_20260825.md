# L3 — Exact Tablebase-Frontier Move-Ordering Policy v1

**Date:** 25 August 2026  
**Status:** preregistered before any frontier corpus or policy result  
**Frozen parent:** `CURRICULUM`, raw PJTW SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`  
**Predecessor verdict:** `RGSC_RESTART_NOT_SUPPORTED` (1562).  
**Safety:** no PatternEval replacement, no leaf-eval change, no frozen cohort, no automatic promotion.

## 1. Motivation

RGSC v1 established a stronger fact than a null treatment effect: all three continuation fits (`NORMAL`, `ARCHIVE_RANDOM`, `ARCHIVE_REGRET`) regressed against frozen CURRICULUM. The data-distribution intervention is therefore no longer the P0 target. We instead test whether Jass can learn **relative legal-move preferences** from an exact oracle while leaving CURRICULUM's scalar evaluation untouched.

The current search gives every non-TT capture the same ordering score (`0`), so capture siblings retain generator order. This creates a clean intervention point: a learned policy may reorder siblings without changing alpha-beta semantics, leaf values, pruning constants, or CURRICULUM.

## 2. Exact supervision source

Use the installed Kingsrow/`egdb_intl` WLD database through Jass's existing `egdb` seam. Let `K = egdb::max_pieces()` on CPX62. Candidate parents have exactly `K+1` pieces and at least two unique legal capture moves. A parent is accepted only when:

1. every unique legal child has at most `K` pieces;
2. every child returns an **exact** WLD (`WhiteWin`, `Draw`, `BlackWin`), never `Unknown`;
3. at least two siblings have different WLD utility from the **parent side-to-move** perspective.

Thus every retained preference is exact:

```text
utility(parent, move) ∈ {-1, 0, +1}
move_i ≻ move_j iff utility_i > utility_j
```

Same-WLD siblings are ties and create no training pair in v1. MTC is not used in v1, so no distance interpretation can leak into the target.

Semantic duplicate moves (`from`, `to`, captured-set, promotion) are deduplicated before labelling.

## 3. Fresh source distribution

Generate **4,000,000 fresh normal CURRICULUM JNNW rows** on CPX62:

- 16 workers × 250,000 rows;
- play depth 8;
- label depth 8 (irrelevant to the exact TB target, kept identical across workers);
- max plies 200;
- random opening plies 4;
- split self-play RNGs;
- drop ply-cap games;
- epsilon/top-K exploration off;
- material adjudication off;
- no seed-file restart intervention;
- generator seed schedule `2026082901..2026082916`.

The generated WDL/score bytes are **not** used to select or label frontier parents. Only the board+STM is consumed by the frontier extractor.

## 4. Child representation and frozen baseline

For every retained child:

- dump the production 120-wide dense Scan/PatternEval extras using Jass `--dump-eval-features` built with `ENDGAME_FEATURES + KING_MOBILITY + SCAN_PARITY + TEMPO_STAGE`;
- append six cheap move-local scalars:
  - number of captures,
  - captured kings,
  - promotes,
  - moving piece is king,
  - `from / 50`,
  - `to / 50`.

No sparse pattern buckets are used in v1. This keeps a future search-time policy tiny and cheap.

The frozen comparator is CURRICULUM itself. Every child is rescored by byte-authenticated CURRICULUM. Because the child is the opponent to move, the baseline parent-preference score is:

```text
baseline_score(parent, move) = - CURRICULUM_score(child, child_STM_POV)
```

Higher score means preferred move for both baseline and learned policy.

## 5. Parent-disjoint split

The unit of independence is the **parent position**, never the child row or pair.

- exact parent fingerprint: `(wm,wk,bm,bk,stm)`;
- split seed: `2026082801`;
- holdout iff `sha256(seed:fingerprint)[0:8] little-endian mod 5 == 0`;
- all siblings of a parent remain in the same split;
- separate White-parent and Black-parent policy banks are trained; no colour result may be hidden by pooling.

Support gate before interpreting learnability:

- at least **800 informative holdout parents** total;
- at least **250 informative holdout parents per parent colour**.

If support fails: `TB_FRONTIER_SUPPORT_NOT_ESTABLISHED`, terminal for this corpus scale. Do not lower thresholds post hoc.

## 6. Frozen policy learner

Two independent linear banks (White-parent / Black-parent), each over exactly `120 + 6 = 126` raw features.

Training pairs contain every exact sibling relation `utility_good > utility_bad`, capped deterministically at **250,000 train pairs per colour** using split-derived seeds if necessary.

Objective per colour:

```text
mean log(1 + exp(-w · (x_good - x_bad))) + (1e-3 / 2) ||w||²
```

Frozen optimiser:

- SciPy L-BFGS-B;
- `maxiter = 500`;
- `gtol = 1e-6`;
- `maxcor = 20`;
- zero initial weights;
- per-column pair-difference standardisation folded back into raw weights after fit;
- no hyperparameter sweep, no arm-specific tuning.

## 7. Metrics

All headline metrics give equal weight to each **holdout parent**.

### Pairwise exact accuracy
For every exact ordered pair `(good,bad)` in a parent:

- 1 if `score_good > score_bad`;
- 0.5 for a score tie;
- 0 otherwise.

Parent score is the mean of its informative pairs; corpus score is the mean over parents.

### Exact top-tier hit
Among all moves tied for the highest model score, take the fraction whose exact utility equals the best utility available in that parent. This gives a fair fractional score to baseline integer ties.

### Exact WLD regret

```text
max_utility(parent) - mean_utility(top_scored_tied_moves)
```

Lower is better.

### Bootstrap
Parent-cluster bootstrap, **100,000** resamples:

- pairwise delta seed `2026082802`;
- top-tier delta seed `2026082803`;
- regret delta seed `2026082804`.

Primary comparison is learned policy minus frozen CURRICULUM baseline.

## 8. Negative controls

Train **16** sham policies, seed `2026082803`. For each sham, independently multiply each training pair difference by a random ±1 sign, fit the identical two-bank learner, then evaluate against untouched exact holdout labels.

The real policy's mean pairwise improvement over CURRICULUM must exceed **every** sham improvement. With 16 shams this is a conservative family control near the 94th percentile without retuning after seeing the corpus.

## 9. Phase-A PASS gate — learnability only

`TB_FRONTIER_RANK_SIGNAL_ESTABLISHED` requires all of:

1. support gate passes;
2. both colour-bank optimisations converge successfully;
3. learned holdout pairwise accuracy ≥ **0.58**;
4. parent-bootstrap CI95 lower bound of pairwise improvement vs CURRICULUM is **strictly > 0**;
5. parent-bootstrap CI95 lower bound of exact top-tier-hit improvement vs CURRICULUM is **strictly > 0**;
6. White-parent and Black-parent pairwise point deltas are both > 0 and top-tier point deltas are non-negative in both;
7. true pairwise improvement exceeds all 16 shuffled-label shams.

Otherwise: `TB_FRONTIER_RANK_SIGNAL_NOT_ESTABLISHED`, terminal for this feature/target family. Do not tune thresholds or learner on the holdout.

Phase A performs **zero strength games** and cannot promote anything.

## 10. Phase B — authorised only after Phase-A PASS

Only after `TB_FRONTIER_RANK_SIGNAL_ESTABLISHED` may Jass add a dormant policy loader and move-order hook.

Frozen semantics for the first strength ablation:

- CURRICULUM remains the **only leaf evaluator**;
- same engine/search parameters and pruning in both arms;
- policy affects **move ordering only**;
- TT move remains first priority;
- policy initially reorders **capture siblings only**, because current captures otherwise share ordering score zero;
- no policy score enters alpha, beta, TT values, static eval, pruning thresholds or game result;
- baseline arm has policy disabled and must be byte-identical to current search behaviour;
- first gate uses fresh openings disjoint from Phase-A source/holdout and all recent force pools, paired colours, native 0.1s primary, Q00 d9 diagnostic, paired opening bootstrap 200k;
- no promotion on the first gate.

A strength PASS would then justify expanding the policy supervision beyond the tablebase frontier using deep-search or exact acquisition. A Phase-A failure closes this route without touching search.

## 11. Interpretation contract

A PASS means only:

> exact sibling preferences contain learnable move-order information in a cheap head that generalises to unseen parent positions better than CURRICULUM's own child ranking.

It does **not** mean the head is a better value evaluator. The experiment is explicitly designed to avoid the scalar-refit failure mode established by RGSC/CTX history.
