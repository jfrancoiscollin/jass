# L3 — T2 phase-specialist deep-fresh v1

Date: 2026-08-28. Status: **preregistered before any T2 training run and before any new fresh T2 validation label is read**.

## 1. Motivation and allowed evidence

`CURRICULUM` remains the production champion, raw decompressed `.pjtw` SHA256:

`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`

The Q1 campaign is terminal (`JOINT_TD_DEEP_FRESH_NOT_CONFIRMED`) and its cohort seed `2026090420` is consumed. **Q1 scores, labels and metrics are forbidden for T2 model selection, architecture tuning, feature selection or calibration.** Q1 may only be used as an exclusion set so that the future T2 validation cohort is disjoint.

The design choice in this protocol is based on pre-Q1 / non-Q1 evidence that is now development data:

- DSSD Phase A/B established a robust static sibling-ranking baseline D1 against q200.
- DSSD Phase-B confirmation: D1 pairwise `0.7260411979` vs CURRICULUM `0.6140599673`, delta `+0.1119812306`, CI95 `[0.0988270517,0.1251451547]`.
- Rich-D Phase-C terminal readout: `cpx62-1590-l3-rich-d-r1-phase-c-readout-v2`, attempt `20260827T111601Z-f931da1b`, verdict `RICH_D_TEACHER_SIGNAL_NOT_ESTABLISHED`.
- Rich-D global pairwise `0.7322476093` vs D1 `0.7299377664`, but its delta vs D1 was strongly phase-dependent: P0 `+0.0501047718`, P1 `-0.0021040634`, P2 `-0.0127784371`, P3 `-0.0352769135`; black `+0.0074989965`, white `-0.0031351031`.
- Rich-D q5k diagnostic pairwise `0.9569280372`, showing substantial remaining search headroom.

This motivates one narrow hypothesis rather than a broad architecture sweep:

> a single global static network underuses late-game structure; a shared state representation with **hard phase-specialist residual experts** and phase/colour-balanced training can exceed D1 on a new q200 holdout while remaining state-only at inference.

No Q1 metric is used to choose widths, optimizer settings, loss weights, gates or seeds below.

---

## 2. Scientific question

Can a state-only evaluator `T2-PMoE` trained directly on already-observed q200 stable-pair data beat the sealed D1 baseline on a completely new parent-disjoint q200 cohort, globally and in every phase and both colours?

The chain is:

`old deep q200 development data -> fixed T2-PMoE fit -> immutable freeze -> new fresh q200 confirmation -> STOP`

No result in this protocol authorizes runtime integration, Elo, strength games, bake or promotion.

---

## 3. Immutable training sources

Training may consume only already-observed deep teacher artefacts from these completed campaigns:

### DSSD Phase A

- selection `cpx62-1570-l3-deep-sibling-selection-v2`, attempt `20260826T104456Z-1493d426`;
- teacher `cpx62-1574-l3-deep-sibling-teacher-v2`, attempt `20260826T185527Z-a6da4a0b`.

### DSSD Phase B

- selection `cpx62-1578-l3-deep-sibling-phase-b-fresh-v2`, attempt `20260826T203927Z-87475360`;
- teacher `cpx62-1579-l3-deep-sibling-phase-b-teacher-v1`, attempt `20260826T210539Z-87475360`.

### Rich-D Phase C

- selection `cpx62-1587-l3-rich-d-r1-phase-c-select-v2`, attempt `20260827T074201Z-fff1f716`;
- teacher `cpx62-1588-l3-rich-d-r1-phase-c-teacher-v1`, attempt `20260827T084459Z-fff1f716`.

All these parents are now development/training data for T2. Their q200 labels may be used for fitting because the T2 scientific test is a future fresh cohort selected only after T2 is frozen.

The stable-pair definition is unchanged:

- exact terminal/TB W>D>L precedence;
- otherwise `sign(d50) == sign(d200)`;
- both deltas non-zero;
- `abs(d50) >= 10 cp`;
- `abs(d200) >= 30 cp`;
- target ordering = q200 parent-POV ranking.

No threshold may change after T2 training begins.

---

## 4. T2 state-only input contract

T2 inference must depend only on the child position itself. It must not require parent move metadata or any search-derived score.

Exactly `326` inputs per child:

1. `120` production `scan_eval::compute_extras(child)` features;
2. `200` raw child board occupancy bits, four 50-square planes `(wm,wk,bm,bk)`;
3. `1` byte-identical CURRICULUM scalar score of the child from child side-to-move POV;
4. `1` child side-to-move bit;
5. `4` child-phase one-hot inputs derived only from child piece count:
   - P0: 30..40 pieces;
   - P1: 20..29;
   - P2: 12..19;
   - P3: 0..11.

Forbidden model inputs:

- q1000, q5k, q50, q200 or any search score;
- WDL / game result;
- D1 score or D1 move-local features;
- move `from/to`, captures, captured kings, promotion or moving-king flags;
- parent legal-move count, parent phase, parent colour or parent ID;
- corpus/source identity;
- train/validation membership;
- Q1 labels, scores or metrics.

The implementation must have deterministic tests proving the exact width/order and absence of forbidden inputs.

---

## 5. T2-PMoE architecture

One fixed architecture; **no architecture sweep** is authorized in v1.

### Shared trunk

`326 -> 256 -> 128`, ReLU after each hidden layer.

### Phase experts

Hard routing from the child phase one-hot. Four independent residual heads:

`128 -> 64 -> 1`, ReLU at the 64-unit hidden layer.

There is one shared trunk and four phase experts; there are **not separate white/black networks**. The child side-to-move bit is an ordinary shared input.

### Output

Each expert predicts a scalar residual. Child evaluation is:

`T2(child) = T0(child) + residual_phase(child)`

where `T0` is the byte-identical CURRICULUM child score already included in the input.

For sibling ranking from the parent perspective, the score is `-T2(child)` because side to move flips after the move. The implementation must test this POV convention explicitly.

T2 is an offline frozen evaluator in this campaign. Runtime cost/serialization format suitable for production is a later question and cannot change this deep-confirmation result.

---

## 6. Deterministic training recipe

Training uses all accepted stable pairs from the three immutable source families above.

No holdout-based early stopping or hyperparameter selection is permitted.

Fixed optimizer:

- pairwise logistic ranking loss;
- deterministic NumPy Adam;
- initialization/shuffle seed `2026090601`;
- batch size `4096` pairs;
- `80` epochs;
- learning rate `1e-3`;
- LR multiplied by `0.3` after epochs 40 and 60;
- weight decay `1e-5`;
- global gradient norm clip `5.0`.

### Phase/colour balance

To directly test the preregistered phase-specialization hypothesis, each accepted pair belongs to one cell `(parent phase, parent colour)` = 8 cells.

The training objective gives **equal total weight to each non-empty cell**, independent of raw pair count. Within each cell all accepted pairs are used, capped only if a cell exceeds `150000` pairs; any cap uses deterministic SHA256 ordering with seed `2026090602`.

No cell weight, cap, epoch count, width or LR may be changed after training metrics are read.

### Normalization

- normalization statistics are fitted once on rows referenced by the allowed training pairs only;
- board planes enter as exact 0/1 values before normalization;
- zero-variance coordinates use scale `1`;
- normalization and all weights are serialized into the frozen artefact.

### Freeze

Training success is technical, not scientific. Before any new fresh parent is selected, publish an immutable T2 manifest containing:

- architecture and input order;
- source job/attempt identities;
- optimizer and balance receipt;
- normalization arrays;
- weights;
- deterministic replay hash;
- artifact SHA256;
- `Q1_LABEL_READS__0` and `Q1_SCORE_READS__0`.

Verdict at this stage: `T2_PHASE_SPECIALIST_FROZEN` only.

---

## 7. New fresh q200 confirmation cohort

Only after T2 bytes are frozen, select exactly `8000` new target-blind CURRICULUM parents:

- 2000 P0 (30..40 parent pieces);
- 2000 P1 (20..29);
- 2000 P2 (12..19);
- 2000 P3 (9..11);
- legal moves 2..16;
- exact-state and valid rotate180/colour-swap canonical de-dup;
- deterministic selection seed `2026090610`.

The selector must exclude canonical parents from:

- DSSD Phase A/B;
- Rich-D Phase C;
- micro-search M1/M2/M3/M5 cohorts;
- Q1 seed `2026090420` cohort;
- established force pools and previously consumed fresh confirmation cohorts.

Exclusion may read only parent identities/fingerprints from Q1, never Q1 labels, candidate scores or metrics.

Selection is committed before q1000/q50/q200 or T2/D1/T0 scores on this cohort are read.

---

## 8. Fresh teacher contract

For every legal sibling of the frozen 8000 parents:

- book OFF;
- one thread per search;
- new Engine, TT and search state for every sibling and every budget;
- q1000 = exactly `1000` nodes, diagnostic only;
- q50 = exactly `50000` nodes, stability screen;
- q200 = exactly `200000` nodes, final target;
- parent POV `Q = - child search score`;
- exact terminal/TB W>D>L precedence identical to DSSD/Q1;
- stable nonterminal pair exactly as in Section 3.

q1000 cannot control pair acceptance or any PASS/FAIL gate.

No model may be fit, refit, calibrated or selected after the first fresh teacher score is read.

---

## 9. Common frozen readout

On exactly the same accepted fresh parents and stable pairs, score:

- T0 / CURRICULUM;
- sealed D1, unchanged SHA `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49`;
- frozen Rich-D artifact SHA `2b8b9672307c0a84b0baaaccbd4a9aff117223c706290e2dd648ef2e42083bb2` as a historical diagnostic only;
- frozen T2-PMoE;
- q1000 diagnostic.

Publish pairwise and top-hit globally, P0/P1/P2/P3, and original parent colour.

Parent-cluster bootstrap:

- samples `200000`;
- seed `2026090611`.

Required CIs:

- T2-D1 pairwise and top-hit;
- T2-T0 pairwise and top-hit;
- T2-Rich-D pairwise (diagnostic);
- q1000-T2 pairwise headroom (diagnostic).

---

## 10. Support gate

Support PASS requires all:

- exactly `8000` parents selected;
- at least `6000` accepted parents with >=1 stable pair;
- at least `1000` accepted parents in each P0/P1/P2/P3;
- at least `2500` accepted white-parent and `2500` accepted black-parent positions;
- at least one stable pair in every phase and colour cell;
- zero forbidden cohort overlap;
- frozen T2 bytes unchanged;
- no post-freeze fit/refit/calibration.

Support failure gives terminal verdict:

`T2_PHASE_SPECIALIST_SUPPORT_NOT_ESTABLISHED`

No threshold relaxation or replacement cohort is allowed.

---

## 11. Primary scientific gate

`T2_PHASE_SPECIALIST_DEEP_SIGNAL_ESTABLISHED` requires support PASS and all:

1. T2-D1 pairwise bootstrap CI95 lower bound > 0;
2. T2-D1 top-hit bootstrap CI95 lower bound > 0;
3. T2-D1 pairwise point delta > 0 in each P0/P1/P2/P3;
4. T2-D1 pairwise point delta > 0 for both original parent colours;
5. T2-T0 pairwise bootstrap CI95 lower bound > 0;
6. deterministic frozen-artifact replay passes;
7. T2 inference contains no parent move-local, D1, search-score or Q1-derived input.

If support passes but any primary gate fails:

`T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED`

No post-hoc phase weighting, architecture enlargement, feature addition, retraining or seed replacement is allowed after fresh results.

Rich-D and q1000 are diagnostics only and cannot rescue a failed primary gate.

---

## 12. Stop rule

This protocol stops at the deep-fresh verdict.

Even on PASS:

- zero strength games;
- zero runtime integration;
- zero Elo gate;
- zero bake;
- zero promotion.

A PASS only authorizes a new, separate preregistration for runtime feasibility/cost and causal strength testing of the exact frozen T2 bytes.

`CURRICULUM` remains champion throughout this campaign.

---

## 13. Planned orchestration

Use the next free CPX62 IDs, expected approximately:

- `1626`: prereg/source-auth + implementation tests, no training or fresh labels;
- `1627`: deterministic T2 training + immutable freeze;
- `1628`: target-blind fresh selection;
- `1629`: q1000/q50/q200 teacher;
- `1630`: common frozen readout + terminal verdict.

Technical failures may be repaired mechanically with versioned IDs, but must never alter sources, feature contract, architecture, optimizer, balance rule, seeds, teacher budgets, support thresholds or primary gates.
