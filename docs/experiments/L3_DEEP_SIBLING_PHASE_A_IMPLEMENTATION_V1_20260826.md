# DSSD v1 Phase-A implementation note

This note fixes implementation details **before any generalized DSSD teacher output, stable-pair count, holdout metric, or learner result is read**. It does not change `L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md`.

- The frozen source partition and P0..P3 phase for every parent are read from the already-immutable `1570` selection receipt; Phase A never re-splits or re-samples parents.
- A non-terminal sibling pair is accepted exactly when the 50k/200k signs agree, both deltas are nonzero, `abs(d50) >= 10 cp`, and `abs(d200) >= 30 cp`.
- Exact rule-terminal/TB W>D>L precedence is applied when both siblings have an exact parent-POV utility and those utilities differ. If exact evidence does not distinguish the pair, the frozen 50k/200k rule applies; diagnostics never enter acceptance.
- An `accepted parent` is a frozen selected parent having at least one accepted stable sibling pair. Every accepted parent therefore contributes at least one stable pair; no minimum stable-parent count is invented beyond the preregistered support/optimizer/gate requirements.
- Training pairs are ordered deterministically by `(parent_id, good_row_index, bad_row_index)` and the first 250,000 per parent colour are retained if the cap is reached. This introduces no additional random seed.
- Pairwise accuracy is computed per parent over accepted stable pairs and then parent-averaged. This is the parent cluster unit used by the bootstrap.
- Top-hit is evaluated only against the accepted stable-pair relation: the teacher top set is the set of siblings participating in accepted pairs with no incoming accepted loss. A model-score tie is scored fractionally by the fraction of tied top siblings in that teacher top set. An otherwise-uncompared sibling cannot earn a top hit merely from an unstable teacher difference.
- The single preregistered bootstrap seed `2026083103` generates the parent-resampling indices used for both pairwise and top-hit deltas. No secondary bootstrap seed is introduced.
- The 16 sign shams use the preregistered seed `2026083104`; signs are randomized only on capped training pair differences, while the untouched holdout stable labels remain fixed.
- Phase and colour gates use untouched holdout accepted parents. If a required phase or colour has no evaluable accepted holdout parent, its strict-positive gate is false; thresholds are never weakened.
- The primary T baseline is the frozen `t_baseline_parent = -CURRICULUM(child)` emitted by the teacher. The independent 5k score is diagnostic only and cannot rescue a failed gate.
- Feature geometry is fail-closed at exactly 120 production eval extras plus the six preregistered move-local scalars, total 126, with separate white-parent and black-parent linear banks.
