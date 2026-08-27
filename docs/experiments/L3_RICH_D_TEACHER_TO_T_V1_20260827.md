# L3 — Rich D teacher → T transfer v1

Date: 2026-08-27. Status: **preregistered before any fresh Rich-D validation labels or any T-transfer result is read**.

## Motivation and sealed upstream evidence

CURRICULUM remains the current champion, raw decompressed `.pjtw` SHA256:

`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`

The general Deep Search Sibling Distillation program established a reproducible static decision signal:

- Phase A: `cpx62-1575-l3-deep-sibling-phase-a-v1`, attempt `20260826T191127Z-f1dee26a`, verdict `DEEP_SIBLING_RANK_SIGNAL_ESTABLISHED`.
- Phase B: `cpx62-1581-l3-deep-sibling-phase-b-readout-v2`, attempt `20260826T212656Z-87475360`, verdict `DEEP_SIBLING_CONFIRMATION_ESTABLISHED`.
- Fresh Phase-B pairwise: D1 `0.7260411979` vs CURRICULUM/T `0.6140599673`, delta `+0.1119812306`, bootstrap 95% CI `[0.0988270517, 0.1251451547]`, positive in P0/P1/P2/P3.
- The 5k-search diagnostic was approximately `0.95` pairwise against the stable 200k teacher in the upstream program. It is an **upper diagnostic / information beacon only**, not an allowed Rich-D input.

Direct runtime use of D1 is scientifically closed:

- `cpx62-1584-l3-dssd-move-ordering-force-pool1-v1`, attempt `20260826T232038Z-9cc1788b`.
- native 0.1 s: D1 score `0.4944166667`, Elo `-3.8799`, paired 95% CI `[0.4856667, 0.50325]`.
- verdict `DSSD_MOVE_ORDERING_NOT_SUPPORTED`.
- runtime D reduced NPS by about 11.4%; Pool2 was correctly not authorized.

Therefore v1 tests a different hypothesis: **D is an offline high-capacity teacher whose information should be compressed into a new scalar T, not a permanent runtime search component.**

## Scientific questions

1. Can a static nonlinear D_teacher, with richer position representation but no search-derived input at inference, materially exceed the sealed linear D1 on genuinely fresh deep-sibling labels?
2. If yes, can a new scalar evaluator T1 absorb part of that decision signal and become stronger than byte-identical CURRICULUM **with D completely absent at runtime**?

The intended chain is:

`deep 200k teacher -> rich static D_teacher -> large cheap sibling corpus -> T1 -> T1 vs CURRICULUM`

No result in this protocol authorizes runtime deployment of Rich-D.

---

# Phase R1 — Rich static D_teacher

## Training source

No fresh validation data is touched during model construction.

Training may use all already-observed DSSD teacher data from:

- Phase-A selection `cpx62-1570-l3-deep-sibling-selection-v2`, attempt `20260826T104456Z-1493d426`;
- Phase-A teacher `cpx62-1574-l3-deep-sibling-teacher-v2`, attempt `20260826T185527Z-a6da4a0b`;
- Phase-B fresh selection `cpx62-1578-l3-deep-sibling-phase-b-fresh-v2`, attempt `20260826T203927Z-87475360`;
- Phase-B teacher `cpx62-1579-l3-deep-sibling-phase-b-teacher-v1`, attempt `20260826T210539Z-87475360`.

All previously exposed A/B parents are now treated as development/training data. The scientific Rich-D test is a new parent-disjoint Phase-C cohort generated only after the model, feature contract and training recipe are committed.

Stable-pair labels remain exactly the DSSD v1 rule:

- exact terminal/TB W>D>L precedence;
- otherwise sign(d50) == sign(d200), both non-zero;
- `abs(d50) >= 10 cp`;
- `abs(d200) >= 30 cp`;
- target ordering is 200k parent-POV Q.

No thresholds may be changed after fresh Phase-C labels are read.

## Rich-D input contract: static only

For each sibling child, exactly 333 inputs:

1. 120 production `scan_eval::compute_extras(child)` features;
2. 200 raw board occupancy inputs = four 50-square binary planes `(wm,wk,bm,bk)` from the JNNW child record;
3. six frozen move-local features:
   - `num_captures`
   - `captured_kings`
   - `promotes`
   - `moving_king`
   - `from / 50.0`
   - `to / 50.0`
4. one scalar byte-identical CURRICULUM parent-POV child score `t_baseline_parent`;
5. four parent-phase one-hot inputs P0/P1/P2/P3;
6. two parent-context inputs `pieces / 40.0` and `legal_moves / 16.0`.

Forbidden as Rich-D inputs:

- q5k, q50 or q200 scores;
- WDL / game outcome labels;
- EGDB result flags except the already-defined exact-label precedence during training target construction;
- source-corpus identity;
- train/validation membership;
- any future holdout statistic.

Thus inference of Rich-D is static and can later label a large sibling corpus without search.

## Rich-D architecture

One fixed architecture, no architecture sweep after fresh validation:

- separate white-parent and black-parent banks;
- MLP `333 -> 384 -> 192 -> 96 -> 1`;
- ReLU after each hidden layer;
- scalar score, higher = better for parent;
- train-feature normalization statistics fitted on training parents only;
- board planes remain represented exactly as 0/1 before the train-only normalization transform.

Training is a deterministic self-contained CPU implementation using NumPy only for the network update; SciPy may be used for metrics/bootstrap but not to change the architecture.

Frozen optimization recipe per colour:

- pairwise logistic loss on accepted stable pairs;
- Adam;
- seed `2026090101` for parameter initialization and deterministic shuffling;
- batch size `4096` pairs;
- `80` epochs, no holdout-based early stopping;
- initial lr `1e-3`;
- lr multiplied by `0.3` after epochs 40 and 60;
- weight decay `1e-5`;
- global gradient norm clip `5.0`;
- all accepted A+B training pairs used, capped only if needed at `500000` pairs per colour by deterministic SHA256 ordering with seed `2026090102`.

The model artifact must contain architecture, input ordering, normalization, seeds, optimizer receipt and SHA256.

## Fresh Phase-C confirmation

Generate exactly 8,000 fresh CURRICULUM parents, target-blind, after the Rich-D artifact is frozen:

- 2,000 each in P0 30-40, P1 20-29, P2 12-19, P3 9-11;
- legal moves 2..16;
- exact+rotate180/colour-swap canonical de-dup;
- exact exclusion of all Phase-A/Phase-B parents and all established force-pool states;
- fresh deterministic selection seed `2026090103` fixed before generation;
- teacher remains book OFF, one thread/search, fresh TT/search state each sibling/budget;
- 5k diagnostic, 50k screen and 200k target, exact node budgets;
- same stable-pair rule as upstream DSSD.

Support gate before interpreting model accuracy:

- exactly 8,000 selected parents;
- >= 6,000 parents with at least one accepted stable pair;
- >= 1,000 accepted parents in every P0..P3;
- >= 2,500 accepted parents of each original parent colour.

If support fails: `RICH_D_FRESH_SUPPORT_NOT_ESTABLISHED`, terminal for v1; no threshold relaxation.

## Frozen Phase-C metrics

Evaluate on the same fresh accepted parent clusters:

- byte-identical CURRICULUM/T baseline;
- sealed linear D1 from Phase A, unchanged;
- Rich-D;
- q5k search diagnostic only.

Bootstrap is parent-clustered, 100,000 samples, seed `2026090104`.

Primary PASS verdict `RICH_D_TEACHER_SIGNAL_ESTABLISHED` requires all:

1. Rich-D global pairwise accuracy >= `0.80`;
2. Rich-D minus D1 pairwise bootstrap 95% lower bound > 0;
3. Rich-D minus D1 top-hit bootstrap 95% lower bound > 0;
4. Rich-D minus T pairwise bootstrap 95% lower bound > 0;
5. Rich-D pairwise delta vs D1 positive in every P0/P1/P2/P3;
6. Rich-D pairwise delta vs D1 positive for both parent colours;
7. optimizer finite / deterministic replay reproduces the artifact and metrics.

`0.85` and `0.90` are stretch milestones to report, **not gates that may be tuned toward after Phase-C is read**.

q5k is diagnostic only and cannot cause a PASS or FAIL.

If any model gate fails after support passes: `RICH_D_TEACHER_SIGNAL_NOT_ESTABLISHED`, terminal for this architecture. No hidden-width, feature, epoch, margin or threshold retuning on Phase-C.

---

# Phase R2 — Transfer Rich-D into scalar T

Only authorized if Phase R1 returns `RICH_D_TEACHER_SIGNAL_ESTABLISHED`.

Rich-D is frozen before this phase. It is never inserted into runtime search.

## Cheap teacher corpus

Select 100,000 target-blind canonical parents from the immutable R2 MegaCorpus universe:

- exactly 25,000 per P0/P1/P2/P3;
- 9..40 pieces, 2..16 legal moves;
- exact exclusion of all R1 train/Phase-C parents and all established force pools;
- selection seed `2026090110`;
- enumerate all legal siblings;
- compute the 333 static Rich-D inputs and 120 production extras;
- Rich-D ranks siblings with frozen bytes;
- produce only top-vs-rest pair constraints for T transfer.

No q5k/q50/q200 and no game WDL are consumed in this cheap corpus.

## T1 definition

T1 must remain a scalar PatternEval-compatible evaluator and must run with **D absent**.

Before fitting, implementation must prove the exact algebraic mapping between the 120 production extras used for pairwise constraints and the writable PatternEval coefficient representation. If exact mapping cannot be established, Phase R2 must stop technically; it is forbidden to fake transfer through a second runtime head and call it T.

Fit a residual around CURRICULUM using Rich-D top-vs-rest constraints:

- initialization = byte-identical CURRICULUM;
- pairwise logistic ranking objective on 120-extra differences;
- deterministic optimizer;
- residual L2 `1e-3` in train-standardized feature coordinates;
- then deterministically scale the fitted residual by the largest scalar `s in [0,1]` satisfying both anchors on a fixed 500,000-state target-blind MegaCorpus anchor set (selection seed `2026090111`):
  - RMS absolute T1-T0 scalar score drift <= `10 cp`;
  - p99 absolute score drift <= `30 cp`.

The anchor set contains no deep labels and cannot select direction from strength results.

No value loss, WDL or Elo is used to choose the residual scaling.

Artifact must be a real loadable `.pjtw` plus receipt proving CURRICULUM parent SHA, residual, scale, anchor drift and model SHA.

## Fresh deep confirmation of T transfer

After T1 bytes are frozen, generate a new, mutually disjoint deep-labelled cohort of exactly 4,000 parents (1,000/phase), seed `2026090120`, with the same 50k/200k stable-pair teacher contract.

Parent-cluster bootstrap 100,000, seed `2026090121`.

`RICH_D_TO_T_TRANSFER_ESTABLISHED` requires:

1. T1 minus T0 pairwise bootstrap 95% lower bound > 0;
2. T1 minus T0 top-hit bootstrap 95% lower bound > 0;
3. positive pairwise delta in every represented phase;
4. positive pairwise delta for both colours;
5. anchor RMS/p99 guards remain satisfied after serialization/reload;
6. Rich-D is not loaded during T1 scoring.

If fail: `RICH_D_TO_T_TRANSFER_NOT_ESTABLISHED`, terminal; no Elo gate and no retuning.

---

# Phase R3 — Strength of T1 alone

Only authorized after `RICH_D_TO_T_TRANSFER_ESTABLISHED`.

Causal contrast:

`T1 alone vs byte-identical CURRICULUM`

D is OFF / absent for both players.

Pool1:

- fresh deterministic 3,000 openings, exact-state disjoint from all prior force pools and all R1/R2 labelled cohorts;
- generator seed `2026090130`;
- paired/reversed colours = 6,000 games;
- native fixed wall-clock 0.1 s/move PRIMARY;
- Q00 depth9 diagnostic, same 6,000 games;
- paired opening-cluster bootstrap 200,000 seed `2026090131`.

If native Pool1 point estimate <= 0.5: `RICH_D_TO_T_STRENGTH_NOT_SUPPORTED`, terminal.

If native Pool1 > 0.5, authorize exactly one unchanged Pool2:

- fresh disjoint seed `2026090140`;
- bootstrap seed `2026090141`;
- same game counts/settings;
- chained bootstrap 200,000 seed `2026090149`.

Final `RICH_D_TO_T_STRENGTH_SUPPORTED` requires:

1. native T1 point estimate > 0.5 on both Pool1 and Pool2;
2. chained native bootstrap 95% lower bound > 0.5;
3. no technical error asymmetry;
4. T1 bytes unchanged across pools;
5. D absent at runtime in every strength game.

If both directions positive but chained lower bound <= 0.5: `RICH_D_TO_T_STRENGTH_INCONCLUSIVE`.
Any non-positive Pool2: `RICH_D_TO_T_STRENGTH_NOT_SUPPORTED`.
Q00 never rescues native failure.

No automatic champion promotion is authorized by this document. A supported T1 is reported for an explicit subsequent promotion/bake decision.

---

# Global prohibitions / scientific hygiene

Throughout R1-R3:

- CURRICULUM is immutable except for the explicitly produced T1 candidate in R2;
- no self-play compounding loop;
- no post-hoc threshold changes;
- no hidden architecture sweep on fresh validation;
- no Rich-D runtime move-ordering test;
- no automatic promotion;
- technical failures may be repaired with versioned jobs without changing science;
- every job publishes exact code/model/data provenance and distinguishes technical state from scientific verdict.
