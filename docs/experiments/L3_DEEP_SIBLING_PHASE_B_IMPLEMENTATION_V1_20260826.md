# DSSD v1 Phase-B confirmation implementation note

This note is implementation-only and does not change `L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md`.
It is frozen after Phase-A returned `DEEP_SIBLING_RANK_SIGNAL_ESTABLISHED` and before any Phase-B fresh teacher output or confirmation metric is read.

## Trigger and frozen inputs

Phase-B is permitted only from successful `cpx62-1575-l3-deep-sibling-phase-a-v1` and reuses its already-fitted `dssd-policy.json` with **zero refit**.
CURRICULUM remains byte-identical raw SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.
No D policy is used to generate or select the fresh positions.

## Fresh CURRICULUM-play source

A fresh source stream is generated from CURRICULUM-only play with deterministic seeds disjoint from the historical R2 source. Source score/WDL fields are never consumed for Phase-B parent selection; the production parent filter reads board bitboards + STM only and zeroes target bytes.

Before any fresh source is generated, the technical play-source contract is frozen as:

- 16 independent single-process producers on CPX62;
- 10,000 requested JNNW records per producer, for 160,000 requested fresh source records before filtering;
- `--gen-data-wdl` with CURRICULUM passed through `--nnue`;
- label depth 4, play depth 8, max plies 260;
- generation seed for shard `s` = `2026083200 + s`, `s=0..15`;
- `--wdl-zero-score`, so no score-search target is required for this source;
- `--random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 --pair-openings --drop-plycap`;
- compiled frozen production search parameters are used for play; no D policy or Phase-A result influences move selection;
- shard payloads are concatenated in ascending shard index before the board/STM-only parent filter.

These settings are a position-source mechanism only. Generated game WDL/outcome bytes are not read by the selector and cannot affect inclusion.

The fresh selector uses:

- Phase-B selection seed `2026083105`;
- exact + rotate180/colour-swap canonical parent de-duplication;
- explicit exclusion of every canonical parent in the frozen Phase-A 1570 selection;
- frozen eligibility 9..40 pieces and 2..16 semantic legal moves;
- exactly 2,000 selected parents;
- target quota 500 parents in each P0/P1/P2/P3 phase whenever at least 500 unique eligible fresh parents are available in that phase;
- if a phase has fewer than 500 available, all available parents from that phase are retained and the remaining slots are filled from the globally lowest SHA256(`2026083105:` + canonical fingerprint) unused fresh parents. This is target-blind and cannot depend on teacher scores, D scores, or outcomes.

The selection stage must publish a receipt proving zero Phase-A canonical overlap and zero source-label reads before any 50k/200k teacher score is consumed.

## Frozen teacher

The Phase-B teacher is byte-for-byte the same DSSD teacher contract as Phase-A:

- book OFF;
- one thread per sibling search;
- fresh TT and fresh search state for every sibling and every budget;
- exact 5,000-node diagnostic, exact 50,000-node stability screen, exact 200,000-node teacher;
- semantic sibling order independent of scores;
- parent POV `Q=-child score`;
- real EGDB allowed with exact terminal/TB W>D>L precedence;
- no retuning.

Stable-pair acceptance is unchanged: same-sign nonzero 50k/200k deltas with `abs(d50)>=10 cp` and `abs(d200)>=30 cp`, except exact terminal/TB W>D>L precedence.

## Zero-refit confirmation gate

The already-fitted Phase-A policy is scored on exactly the same 120 production eval extras + 6 move-local features. No optimizer is invoked.

For confirmation parents having at least one accepted stable pair:

- primary baseline remains `-CURRICULUM(child)`;
- compute per-parent pairwise accuracy for D and T;
- each selected phase represented by fresh parents must also have stable-pair support; otherwise confirmation fails rather than silently dropping the phase;
- D-T pairwise point delta must be strictly positive in every represented P0/P1/P2/P3 phase;
- global D-T pairwise delta is bootstrapped by parent cluster with 100,000 resamples and seed `2026083103`; the 95% lower bound must be strictly positive.

PASS verdict name: `DEEP_SIBLING_CONFIRMATION_ESTABLISHED`.
FAIL verdict name: `DEEP_SIBLING_CONFIRMATION_NOT_ESTABLISHED`.
Either Phase-B verdict is terminal for this automation: zero strength games, zero promotion, and no runtime move-order integration.
