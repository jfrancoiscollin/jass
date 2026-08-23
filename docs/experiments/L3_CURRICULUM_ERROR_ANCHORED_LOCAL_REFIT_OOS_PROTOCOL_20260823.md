# CURRICULUM anchored local-refit OOS protocol (2026-08-23)

## Purpose

This stage tests whether a support-limited residual update learned from confirmed
CURRICULUM errors improves new errors without moving the champion outside the
preregistered decision channel.  It is an offline causal screen, not a strength
promotion.

## Sequential authorization

1. The 600-pair endgame-abstention confirmation must pass.
2. The immutable-1508 stable-subspace screen must pass.
3. The joint refit/OOS preregistration is published before any OOS label.
4. Exactly one anchored residual delta is fit.  CURRICULUM PatternEval bytes,
   feature mean/RMS, coefficients outside the stable support, and all decisions
   outside the fixed risk gate remain unchanged.
5. A separate OOS-availability preregistration authenticates that fit and seals
   the campaign before any OOS game or label.
6. Target-free availability must pass before exact depth-12 labels are read.
7. Only the final sealed 600-pair audit may authorize strength-gate
   preregistration.

Every negative scientific gate closes the branch.  Technical failures may be
repaired without changing the scientific constants.

## Sealed OOS campaign

- 15,360 CURRICULUM-vs-CURRICULUM games from 1,920 openings per pool.
- Pool seeds `2026082311` and `2026082312`; split/order seed `2026082313`.
- Opening and source-game disjointness from the authenticated historical,
  training, fresh-confirmation, and availability chains.
- Candidate profiles contain no exact action values.
- Canonical states are unique and at most two states come from one source game.
- Availability requires at least 3,600 eligible states, 1,800 games, 1,800
  openings, 1,800 raw pairs overall, 720 raw pairs in each pool, and a projected
  exact-target cost no greater than 360 minutes.

## Fixed per-pool selection

The OOS set is exactly 300 valid error/control pairs from each pool.  Each pool
has an independent order fixed before target reconstruction.  An unknown edge
blocks later edges only in its own pool; therefore batching cannot alter either
pool's selected prefix.  Labels determine whether an already ordered edge is a
valid error/control pair, but never rank candidates.

## OOS gates

The anchored delta is compared incrementally with the confirmed alpha-300
endgame-abstention baseline on the same 600 pairs.  All preregistered regret,
paired-control, per-pool direction, decision-change, calibration, symmetry, and
identity gates are required jointly.  The audit also verifies the actual
CURRICULUM file hash and bit identity of all coefficients outside the stable
support.

An OOS pass authorizes only the preregistration of two native-primary strength
gates on fresh disjoint pools, with Q00 depth 9 diagnostic.  It does not
authorize frozen evaluation or automatic promotion.
