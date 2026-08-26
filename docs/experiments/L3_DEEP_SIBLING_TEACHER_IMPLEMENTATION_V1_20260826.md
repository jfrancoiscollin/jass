# DSSD v1 teacher implementation note

This note is implementation-only and does not change `L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md`.

The generalized sibling teacher consumes only the already frozen target-blind selected-parent JNNW. It does not choose parents, accept stable pairs, fit D, run strength games, or authorize promotion.

For each selected parent it de-duplicates and canonicalizes legal semantic moves before reading any teacher score. Every child is then processed independently with byte-pinned CURRICULUM, opening book disabled, one search thread, the production default search parameters, and a 16 MiB Engine TT that is cleared before every search. Search history is reset by setting the child position before every call.

Each child produces three clean exact-node searches: 5,000 nodes for the preregistered cheap-search diagnostic, 50,000 nodes for the frozen stability screen, and 200,000 nodes for the frozen teacher target. The exact node-limit mode is used with `MAX_PLY` only as an iterative-deepening safety ceiling. Parent-POV values are the negation of the child-STM search score. The direct T baseline is likewise the negation of CURRICULUM's child-STM scalar evaluation.

Real EGDB is required on the production CPX62 execution. No-legal-move children and exact EGDB WLD are emitted as separate exact-outcome metadata so the later stable-pair stage can apply the already preregistered terminal/TB precedence. The teacher extractor itself deliberately does **not** decide stable-pair acceptance.

The executable is shardable by parent row (`parent_id % nshards`) so multiple independent single-thread sibling searches can run concurrently without sharing TT/search state across sibling evaluations. Outputs are zero-target child JNNW rows plus TSV provenance/search telemetry suitable for the later 120-extra + 6 move-feature learner stage.
