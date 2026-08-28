# L3 — Residual Feature Discovery v1

Date: 2026-08-28. Status: **preregistered before any new residual-family metric or new fresh validation label is read**.

## 0. Motivation and immutable upstream

The terminal T2 campaign established:

- `T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED`;
- D1 q200 fresh pairwise `0.7338846504`;
- T2 q200 fresh pairwise `0.7018589740`;
- q1000 q200-target pairwise `0.9374100334`;
- q1000−T2 headroom `+0.2355510594`;
- T2−D1 by phase: P0 `+0.0186385392`, P1 `-0.0388096009`, P2 `-0.0592457989`, P3 `-0.0539011136`.

Immutable identities:

- CURRICULUM/T0 raw SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`;
- sealed D1 SHA256 `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49`;
- historical Rich-D SHA256 `2b8b9672307c0a84b0baaaccbd4a9aff117223c706290e2dd648ef2e42083bb2`;
- frozen T2 SHA256 `80de2d003c139c0fd8371e17175889a31f97792c5fd042a2a7338ca9dbc83c4d`.

Consumed validation cohorts **forbidden for tuning, family selection, coefficient fitting, calibration or threshold choice**:

- Q1 seed `2026090420`, selection `cpx62-1617-l3-joint-td-q1-select-v7`;
- T2 fresh seed `2026090610`, selection `cpx62-1628c-l3-t2-phase-specialist-fresh-select-v3`.

Only their canonical identities may later be read to exclude them from a new fresh cohort.

The earlier CURRICULUM sparse-coordinate residual-atlas line is also treated as negative historical evidence, not a family to repeat: its successful final atlas had orientation-symmetry fraction about `0.8172` and coordinate-replication fraction about `0.3478`, with the preregistered residual-region gates failing. Therefore v1 does **not** search PatternEval coordinates or fit a post-hoc sparse Jacobian direction.

## 1. Scientific question

> Can a fixed, search-free family of explicitly computed game-mechanical observables add reproducible q200 sibling-ranking information beyond sealed D1, first on two historical out-of-sample cohorts and then on a completely new fresh q200 cohort?

This is a **feature-value experiment**, not a production evaluator experiment. No result here authorizes runtime, Elo, strength, bake or promotion. A PASS only authorizes a separately preregistered T3/student integration experiment.

## 2. Data roles fixed before screening

### TRAIN — Phase A only

Fit residual-family probes only from the already-exposed DSSD Phase-A data:

- selection `cpx62-1570-l3-deep-sibling-selection-v2`, attempt `20260826T104456Z-1493d426`;
- teacher `cpx62-1574-l3-deep-sibling-teacher-v2`, attempt `20260826T185527Z-a6da4a0b`.

### DEV-B — Phase B, zero probe fit

- selection `cpx62-1578-l3-deep-sibling-phase-b-fresh-v2`, attempt `20260826T203927Z-87475360`;
- teacher `cpx62-1579-l3-deep-sibling-phase-b-teacher-v1`, attempt `20260826T210539Z-87475360`.

### DEV-C — Rich-D Phase C, zero probe fit

- selection `cpx62-1587-l3-rich-d-r1-phase-c-select-v2`, attempt `20260827T074201Z-fff1f716`;
- teacher `cpx62-1588-l3-rich-d-r1-phase-c-teacher-v1`, attempt `20260827T084459Z-fff1f716`.

All stable-pair labels use exactly the existing DSSD rule:

- exact terminal/TB W>D>L precedence;
- otherwise `sign(d50)==sign(d200)`, both non-zero;
- `abs(d50)>=10 cp`;
- `abs(d200)>=30 cp`;
- q200 parent-POV ordering is the target.

No Q1 or T2-fresh data may be fetched during TRAIN/DEV screening.

## 3. Feature contract

All new features are deterministic, finite, search-free and computed from a sibling **child position** plus the known parent side (`parent = opposite(child.stm)`). No q1000/q5k/q50/q200 score, WDL/game outcome, source identity, split membership, D1 score, T2 score or future-holdout statistic is a feature input.

Full legal-move generation is permitted. Bounded enumeration explicitly specified below is permitted. Alpha-beta, TT, iterative deepening, learned evaluation and node-budget search are forbidden inside feature extraction.

Every scalar is oriented to **parent POV**. Colour-paired quantities are represented as `parent_side_value - opponent_side_value` unless a component is explicitly defined as a direct parent-POV aggregate.

### Diagnostic reference only — `CTX2_REF` (not eligible to win)

The existing 15 base concepts from `compute_conditional_context_v2`: men delta, has-king delta, extra-king delta, legal-move-count delta, legal-capture-option delta, max-capture-length delta, forced-move delta, promotion-pressure delta, blocked-man delta, center-presence delta, wing-skew-abs delta, king-centrality delta, king-proximity delta, king-safe-mobility delta, king-denied delta.

This is reported to connect the new experiment to the older CTX2/CTX3 line; it cannot be selected as the v1 winning family.

### F1 — `CAPTURE_GEOMETRY` — 12 scalars

For each side independently using the complete FMJD legal generator, then parent-minus-opponent:

1. legal move count;
2. legal capture move count;
3. maximum captured-piece count among legal captures;
4. mean captured-piece count among legal captures (0 if none);
5. maximum captured-king count among legal captures;
6. mean captured-king count among legal captures (0 if none);
7. unique capture landing-square count;
8. unique capture origin-square count;
9. legal promotion-move count;
10. legal capture-and-promote move count;
11. forced-move indicator (`legal_moves==1`);
12. capture-landing dispersion = mean squared FMJD-square distance from the mean landing coordinate over legal captures, 0 if fewer than two.

A legal multi-capture move is one complete semantic move. No partial-capture pseudo-move is counted.

### F2 — `RESPONSE_FRONTIER` — 14 scalars

Starting from the child position, enumerate **all legal moves of child STM** (the opponent of the parent). Apply each complete legal move once. For the resulting reply states compute the parent's immediate legal frontier, without applying a parent move.

Direct parent-POV aggregates:

1. number of opponent replies;
2. fraction of opponent replies that are captures;
3. fraction of opponent replies that promote;
4. minimum parent material delta after opponent reply;
5. mean parent material delta after opponent reply;
6. maximum parent material delta after opponent reply;
7. minimum parent next legal-move count;
8. mean parent next legal-move count;
9. maximum parent next legal-move count;
10. minimum parent next maximum-capture length;
11. mean parent next maximum-capture length;
12. maximum parent next maximum-capture length;
13. fraction of replies after which parent has at least one legal capture;
14. fraction of replies after which parent is forced to exactly one legal move.

Material delta is `parent men + 3*parent kings - opponent men - 3*opponent kings`, relative to the input child state. Empty sets are impossible for legal nonterminal positions; exact terminal states use deterministic zero-fill plus a terminal flag already handled by the label precedence, not as an input.

### F3 — `PROMOTION_RACE` — 12 scalars

For each man, compute a deterministic monotone quiet-path BFS to its promotion row on the current occupancy graph. The BFS:

- uses only forward quiet diagonal steps appropriate to that colour;
- treats all currently occupied squares as blocked except the starting square;
- does not move blockers or model captures;
- returns infinity if no such current-occupancy path exists.

For each side summarize: minimum finite distance, mean finite distance, count distance<=1, count distance<=2, count distance<=3, count with no path. Use `8` as the numeric sentinel for no finite distance in min/mean summaries. The family is the six parent-minus-opponent differences = 6 scalars, plus the same six summaries recomputed on a second graph where squares immediately capturable by an enemy man on its next legal capture are treated as blocked = 6 more scalars.

### F4 — `STRUCTURE_GRAPH` — 16 scalars

For men only, build an undirected graph connecting same-colour men on diagonally adjacent playable squares. Compute per side and parent-minus-opponent:

1. connected-component count;
2. largest-component size;
3. isolated-man count;
4. diagonal-adjacent friendly-man edge count;
5. edge-file man count (outermost playable files);
6. central-16-square man count, with the square set frozen in implementation tests before metrics;
7. home-row man count;
8. blocked-man count (no forward quiet step on current occupancy);
9. mean nearest-friendly-man Chebyshev board distance, 0 for <2 men;
10. maximum nearest-friendly-man distance, 0 for <2 men;
11. absolute wing skew `|sum(2*col-9)|`;
12. occupied bounding-box area on `(row,col)`, 0 if no men;
13. frontmost-man advancement;
14. rearmost-man advancement;
15. number of empty playable squares adjacent to at least three friendly men (`holes3`);
16. quiet mobility per man = legal quiet destinations ignoring mandatory-capture suppression divided by `max(1,men)`.

Board coordinate/square sets and colour mirroring are frozen by unit tests before any family metric is read.

### F5 — `KING_GEOMETRY_PLUS` — 12 scalars

For kings only, per side and parent-minus-opponent:

1. king count;
2. total unobstructed slide destinations;
3. safe slide destinations not immediately capturable by an enemy man;
4. denied slide destinations;
5. edge-square king count;
6. central-square king count using the same frozen central set as F4;
7. trapped-king count (`safe_slide_destinations<=1` per king);
8. minimum king-to-enemy-piece Chebyshev distance, sentinel 8 if no king or enemy;
9. mean nearest-enemy distance, sentinel 8 if no king or enemy;
10. count of enemy pieces sharing an unobstructed king diagonal;
11. minimum same-colour king-pair distance, sentinel 8 if fewer than two kings;
12. count of king pairs on the same unobstructed long diagonal.

### F6 — `ALL_NEW`

The fixed concatenation `F1 || F2 || F3 || F4 || F5`, exactly 66 scalars. It is a candidate from the start; it is not constructed conditionally after seeing individual-family results.

## 4. Residual probe — fixed learner

For each eligible family F1..F6 fit a residual around sealed D1 on TRAIN Phase A only.

For every sibling child:

`R_F(child) = D1(child) + w_F · z_F(child)`

where `z_F` is the family vector standardized with TRAIN-only mean/std. D1 coefficient is fixed at exactly `1.0`; there is no intercept and D1 is never refit/rescaled.

Training objective:

- pairwise logistic loss on accepted q200 stable pairs;
- residual L2 `1e-3` in standardized coordinates;
- deterministic L-BFGS-B, zero residual initialization, `maxiter=500`, `gtol=1e-7`, `maxcor=10`;
- all Phase-A accepted pairs, cap `250000` pairs only if necessary by deterministic SHA256 order seed `2026090701`;
- no early stopping, no hyperparameter sweep.

CTX2_REF is fit identically for diagnostic reporting but is ineligible for winner selection.

## 5. Historical out-of-sample screen

Evaluate frozen Phase-A-fitted probes without refit on DEV-B and DEV-C separately and pooled.

Primary metric: q200 stable-pair accuracy. Secondary: parent top-hit.

Bootstrap: parent-cluster `100000`, seed `2026090702`.

For each candidate publish global, DEV-B, DEV-C, P0/P1/P2/P3 and original parent-colour deltas versus sealed D1.

### Negative-control shams

Generate exactly 32 deterministic parent-cluster sign shams per family, seed base `2026090703`: every parent's complete family residual vector is multiplied by one random sign `+1/-1`, shared by all siblings of that parent; signs are independently generated within TRAIN, DEV-B and DEV-C from canonical parent identity and sham index. Fit/evaluate each sham with the identical learner. This preserves family magnitudes, sibling geometry and cluster structure while destroying directional association.

### Family screen PASS

A family F1..F6 is `screen_pass=true` iff all are true:

1. pooled `R_F - D1` pairwise bootstrap CI95 lower bound > 0;
2. DEV-B pairwise point delta > 0;
3. DEV-C pairwise point delta > 0;
4. pooled point delta > 0 in P0/P1/P2/P3;
5. pooled point delta > 0 for black and white parents;
6. observed pooled pairwise delta is strictly greater than the maximum pooled delta of all 32 shams for that family;
7. optimizer is finite/successful and artifact replay deterministic.

If no F1..F6 passes: terminal verdict `RESIDUAL_FEATURE_FAMILY_NOT_ESTABLISHED`. No new fresh cohort is generated.

If one or more pass, choose **exactly one** winner by preregistered ordering:

1. largest pooled pairwise delta vs D1;
2. if tied within `1e-12`, largest pooled top-hit delta;
3. if still tied, fixed lexical order `F1 < F2 < F3 < F4 < F5 < F6`.

No post-hoc union, threshold change, feature deletion or coefficient editing is allowed.

## 6. Freeze after historical screen

Only after a winner exists, refit that exact family once on the union TRAIN+DEV-B+DEV-C with the identical learner/L2, fresh train-only normalization on that union, and no architecture/feature change.

Publish immutable `RF1` artifact containing:

- winning family identity and exact ordered feature names;
- extractor/code SHA;
- D1 SHA;
- normalization;
- residual coefficients;
- source attempts and pair counts;
- optimizer receipt;
- artifact SHA256;
- full historical screen and sham receipt.

This refit occurs **before** any new fresh parent is generated or teacher score read.

## 7. New fresh confirmation cohort

Only after RF1 bytes are frozen, generate exactly `6000` new target-blind CURRICULUM parents:

- 1500 P0 (30..40 pieces);
- 1500 P1 (20..29);
- 1500 P2 (12..19);
- 1500 P3 (9..11);
- legal moves 2..16;
- exact + rotate180/colour-swap canonical de-dup;
- selection seed `2026090710`;
- source-generation seed base `2026090720`, frozen before generation.

Exclude canonical identities from DSSD A/B, Rich-D C, M1/M2/M3/M5, Q1, T2-1628c and every established force/confirmation pool used by the current L3 history. Q1 and 1628c may be read **only as identity lists** for exclusion; their labels/scores/metrics remain unread.

Selection is committed before RF1/D1/T2/q1000/q50/q200 scoring on the new cohort.

## 8. Fresh teacher

All legal siblings of the exact fresh cohort:

- book OFF;
- one thread/search;
- new Engine/TT/search state for every sibling and budget;
- q1000 exact 1000 nodes, diagnostic only;
- q50 exact 50000 nodes, stability screen;
- q200 exact 200000 nodes, target;
- parent POV `Q=-child_score`;
- identical terminal/TB precedence and stable-pair rule from section 2.

q1000 never controls acceptance. No fit/refit/calibration is allowed after the first fresh teacher score is read.

## 9. Fresh support gate

Before interpreting model metrics require all:

- selected parents exactly `6000`;
- accepted parents >= `4500`;
- accepted parents >= `750` in every P0/P1/P2/P3;
- accepted parents >= `1800` for each original parent colour;
- stable pairs >0 in every phase×colour cell;
- forbidden canonical overlap = 0;
- RF1/D1/T2 bytes unchanged;
- zero post-freeze fit/refit/calibration;
- zero selfplay/strength/runtime/Elo/bake/promotion.

If support fails: terminal `RESIDUAL_FEATURE_FRESH_SUPPORT_NOT_ESTABLISHED`; thresholds may not be relaxed.

## 10. Fresh readout and terminal gate

Evaluate on the same accepted parents/pairs:

- T0/CURRICULUM;
- sealed D1;
- frozen T2 diagnostic;
- frozen RF1;
- q1000 diagnostic.

Parent-cluster bootstrap `200000`, seed `2026090711`.

Publish pairwise/top-hit globally, by phase and colour; RF1−D1, RF1−T2, RF1−T0, q1000−RF1 CIs; and an error taxonomy including q1000-correct/D1-wrong/RF1-correct transitions. The taxonomy is diagnostic only.

Primary PASS verdict `RESIDUAL_FEATURE_FAMILY_CONFIRMED` requires all:

1. support PASS;
2. RF1−D1 pairwise mean >= `+0.005`;
3. RF1−D1 pairwise bootstrap CI95 lower bound > 0;
4. RF1−D1 top-hit bootstrap CI95 lower bound > 0;
5. RF1−D1 pairwise point delta > 0 in P0/P1/P2/P3;
6. RF1−D1 pairwise point delta > 0 for black and white parents;
7. RF1−T0 pairwise bootstrap CI95 lower bound > 0;
8. deterministic extractor/model replay and all forbidden-input guards pass.

If support passes but any primary gate fails: terminal `RESIDUAL_FEATURE_FAMILY_NOT_CONFIRMED`.

q1000 and T2 diagnostics cannot rescue a failed gate.

## 11. Stop rule and downstream authorization

At any terminal verdict, STOP. This campaign performs:

- zero PatternEval/T3 fit;
- zero runtime integration;
- zero Elo/strength games;
- zero bake/promotion.

`RESIDUAL_FEATURE_FAMILY_CONFIRMED` authorizes only a **new separately preregistered T3/student experiment** that integrates the frozen winning feature family and uses another new deep-fresh confirmation cohort.

`RESIDUAL_FEATURE_FAMILY_NOT_ESTABLISHED` or `...NOT_CONFIRMED` closes this hand-engineered family bank v1; the next scientific pivot should be a separately preregistered inductive-bias experiment (for example local convolution/message passing) rather than silently adding or retuning features.

## 12. Non-negotiable leakage rules

1. Q1 and T2-1628c labels/scores/metrics are never inputs to discovery, selection, fitting or calibration.
2. No family definition may change after any family screen metric is read.
3. No new fresh cohort is generated before the winning RF1 artifact is immutable.
4. No fresh result may change L2, optimizer, feature set, support threshold, seeds or PASS gates.
5. D1 and T2 remain frozen diagnostics; D1 is the primary baseline.
6. q1000 imitation, q200 accuracy and eventual Elo remain separate scientific levels.
