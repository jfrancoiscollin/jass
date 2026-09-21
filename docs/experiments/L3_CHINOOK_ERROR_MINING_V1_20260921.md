# Jass CHINOOK error mining V1

Date: **21 September 2026**  
Status: **EXPLORATORY_CONSUMED_DATA / NO PROMOTION AUTHORITY**

## Objective

Turn already-computed independent Scan references into an explicit blind-spot mining
stage for Jass. The primary question is:

> Which pre-score position/action-pattern descriptors are overrepresented among
> roots where CURRICULUM has high regret versus the frozen Scan 2M-per-child
> reference?

This is inspired by the Chinook workflow of examining recurring failure motifs
and converting repeated errors into targeted knowledge. It is not a new strength
claim, not a G0 replay, and not a model-selection gate.

## Frozen inputs

The stage consumes only previously published artifacts:

1. `all-512-scan-reference.tsv` from
   `L3_CLS_HIER_SCAN_REFERENCE_DIAGNOSTIC_V1_20260920`;
2. the frozen `siblings.tsv` metadata for the same 512 roots.

No fresh Jass search, Scan search, fit, self-play, match, promotion, bake or test
target read is permitted.

The Scan reference is an external deep reference, **not ground truth**. Native
centi-Scan values are not Elo, win probabilities or Jass centipawns.

## Primary error measure

For each root, use the frozen 2,000,000-node-per-child column:

`curriculum_regret = b2000000_parent_regret`.

The gross-error tail is fixed before pattern inspection as the highest **64 roots**
by curriculum regret, with all ties at the 64th-root regret included. This
tie-inclusive rule can produce more than 64 roots and must be reported explicitly.

No score threshold is tuned after observing pattern performance.

## Pre-score descriptors

Only board/action metadata available without reading Scan scores may define
patterns:

- phase;
- total pieces;
- side to move;
- white/black men and kings;
- total kings;
- weighted material margin from side-to-move point of view (man=1, king=3);
- legal-move count bucket;
- capture availability;
- number of capture choices;
- maximum capture length;
- multi-capture availability;
- promotion-option availability/count;
- king-move-option availability/count;
- king-capture-option availability/count.

The implementation derives board counts from `parent_fingerprint` and action
properties from the complete legal sibling catalogue. It may not derive a feature
from Scan scores, HIER score deltas, or the gross-error label itself.

## Pattern enumeration

Each descriptor is categorical/bucketed before reading score columns. For every
(feature, value) pair report:

- support;
- gross-error count;
- gross-error rate;
- global gross-error baseline;
- lift = rate / baseline;
- mean and median curriculum regret;
- mean primary Scan score gap between HIER and CURRICULUM as secondary context.

The exploratory shortlist is mechanically defined as patterns with support >= 16
roots and at least 4 gross errors. It is sorted by descending lift, then gross
count, support, feature and value.

This ordering is a discovery aid only. It is not a causal ranking and does not
authorize implementation of a feature.

## Boundary

The stage must state:

- `diagnostic_only=true`;
- `reference_is_ground_truth=false`;
- `scientific_verdict=null`;
- `promotion_authorized=false`;
- `automatic_feature_implementation_authorized=false`;
- `new_scan_searches=0`;
- `new_jass_searches=0`;
- `fits=0`;
- `strength_games=0`.

A candidate motif emerging here requires a separate preregistered causal feature
experiment before any runtime adoption.

## Outputs

- `chinook-error-mining-v1.json`
- `chinook-error-patterns-v1.csv`

The implementation is `jobs/tools/chinook_error_mining.py`.
