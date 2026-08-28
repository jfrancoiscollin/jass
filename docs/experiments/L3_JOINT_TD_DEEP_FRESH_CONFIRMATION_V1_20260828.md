# L3 — Joint T+D deep fresh confirmation v1

> Date de preregistration : 28 août 2026  
> Statut : **preregistered before any new q200 cohort is selected or labelled**  
> Baseline de production : `CURRICULUM`  
> Objectif : confirmer sur un cohort deep entièrement fresh que la complémentarité `T + D` observée contre q1000 se généralise à la préférence deep q200.

## 0. Règle fondamentale

Le screen `1614/1615` a servi à choisir les architectures. **Aucune donnée q200 future ne peut modifier les candidats, hyperparamètres, seuils, seeds ou gates ci-dessous.**

Le futur cohort q200 est interdit à tout fit/refit/model selection. Tous les candidats sont gelés avant sa sélection.

---

## 1. Preuves amont immuables

### Champion

`CURRICULUM` raw/decompressed SHA256 :

`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`

### D1 scellé

DSSD Phase-B source : `cpx62-1581-l3-deep-sibling-phase-b-readout-v2`.

D1 policy SHA256 utilisé par 1614 :

`e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49`

D1 est **zéro-refit** dans toute cette confirmation.

### Screen de sélection d'architecture

- prereg : `L3_TRANSFER_CAPACITY_JOINT_V1_20260828.md`, merge SHA `78b2da436f990b6db870c7c1f7b3ee7a7d12b130` ;
- implementation SHA : `d8241edc680eb50f324b2440fbde2bdadad29178` ;
- screen : `cpx62-1614-l3-transfer-capacity-joint-screen-v2`, attempt `20260828T092856Z-d8241edc` ;
- compact readout : `cpx62-1615-l3-transfer-capacity-joint-readout-publish-v1`, attempt `20260828T100556Z-d8241edc`.

DEV q1000-selection results that motivate this confirmation:

- T0 pairwise `0.6142493326` ;
- D1 `0.6569985012` ;
- A6 G0 `0.6197133624` ;
- B1 `0.6532855604` ;
- C0 `0.6726851201` ;
- C0−D1 bootstrap mean `+0.0156777066`, CI95 `[+0.0140120978 ; +0.0172939908]`.

These q1000 DEV values are **not deep confirmation evidence**.

---

## 2. Candidates frozen before q200

Five scorers are compared on exactly the same future siblings.

### S0 — T0 / CURRICULUM

Byte-identical production PatternEval.

### S1 — D1 sealed

Exact 126-feature DSSD static scorer already frozen in Phase A/B. Separate parent-colour banks, no refit.

### S2 — A6-G0 pure PatternEval

Exact selected candidate from 1614:

- arm `A6_MARGIN_L2_1E5` ;
- guard G0 `(RMS <=12 cp, p99 <=35 cp)` ;
- candidate raw SHA256 `271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed` ;
- 1614 source path conceptually `screen/A6_MARGIN_L2_1E5-G0/cand-final.pjtw`.

No refit is allowed. The bytes fetched for confirmation must match this SHA exactly.

### S3 — B1 nonlinear same-observable probe

Because 1614 published the B1 metrics/receipt but not a reusable parameter artifact, **B1 must be deterministically replayed and serialized before any fresh cohort selection**.

Frozen training semantics, exactly as 1614:

- M3 TRAIN split only, split seed `2026090401` ;
- active categorical PatternEval pattern identities ;
- signed sum of trainable 8-d embeddings ;
- 120 production extras, normalization fit on M3 TRAIN only ;
- phase one-hot 4 + side 1 ;
- hidden 64 ReLU ;
- pairwise top-plus-adjacent constraints ;
- Adam, seed `2026090402`, lr `1e-3`, batch `4096`, 6 epochs ;
- parameter count expected `875601` ;
- no D1, q1000 score, q50, q200, WDL or search score as inference input.

The freeze job must serialize all values required for deterministic inference: active-pattern mapping, embeddings, normalization mean/std, dense head weights/biases and metadata.

Replay acceptance before fresh selection:

- pairwise on frozen 1614 DEV exactly reproduces `0.6532855603952976` within `1e-12` ;
- top-hit exactly reproduces `0.26667692149925654` within `1e-12` ;
- artifact SHA256 is published.

Failure to reproduce is **technical** and forbids fresh q200 generation.

### S4 — C0 minimal joint stack T+D

C0 also must be deterministically replayed/serialized before future labels because 1614 did not publish its fitted coefficients as a reusable artifact.

Frozen semantics exactly as 1614:

- M3 TRAIN only, same split seed `2026090401` ;
- top-vs-rest constraints ;
- inputs per sibling: `[T0 scalar, D1 scalar, phase one-hot P0..P3, parent side]` ;
- pairwise logistic fit via `fit_dense_pair` ;
- L2 `1e-6` ;
- no q1000/q50/q200/WDL as inference input ;
- D1 remains sealed and zero-refit.

Serialize the 7 coefficients, feature order, exact T0 SHA, D1 policy SHA and fit receipt.

Replay acceptance before fresh selection:

- pairwise on frozen 1614 DEV exactly reproduces `0.6726851201348883` within `1e-12` ;
- top-hit exactly reproduces `0.3072860585550941` within `1e-12` ;
- artifact SHA256 is published.

Failure to reproduce is **technical** and forbids fresh q200 generation.

### Freeze rule

S0–S4 identities/SHAs must be written to one immutable `candidate-freeze.json` **before the fresh selection job starts**. After that point no model bytes or parameters may change.

---

## 3. Fresh cohort Q1

### Selection

Select exactly **4000 new CURRICULUM parents**, target-blind:

- seed `2026090420` ;
- P0 30–40 pieces: 1000 ;
- P1 20–29: 1000 ;
- P2 12–19: 1000 ;
- P3 9–11: 1000 ;
- legal moves 2..16 ;
- book-independent position identity ;
- exact-state de-dup plus canonical rotate180/colour-swap de-dup.

Selection must occur before any q50/q200/q1000 score is read.

### Mandatory exclusions

Exclude canonical overlap with all parent cohorts used by:

- DSSD Phase A/B ;
- Rich-D R1 ;
- micro-search M1/M2/M3 ;
- M5/1612 ;
- all prior L3 force pools where exact/canonical inventories are available ;
- this confirmation itself if retried.

At minimum, overlap with M3 and M5 must be machine-proven zero.

A retry after a purely technical failure reuses the **same selected cohort**, never selects a replacement cohort.

### Selection outputs

Publish selected parent payload, canonical fingerprints, phase/colour counts, exclusion receipts, seed and SHA256. Markers:

- `TARGET_BLIND__TRUE`
- `DEEP_LABELS_READ__0`
- `TEACHER_SCORES_READ__0`
- `MODEL_REFITS__0`

---

## 4. Deep teacher and stable target

For every legal sibling child of each selected parent:

- book OFF ;
- one thread/search ;
- fresh Engine / fresh TT / fresh search state per sibling and budget ;
- frozen production search semantics ;
- exact node budgets.

Budgets:

- `q1000` = 1,000 nodes, diagnostic teacher bridge ;
- `q50` = 50,000 nodes, stability screen ;
- `q200` = 200,000 nodes, primary deep target.

Scores are converted to parent POV exactly as in DSSD/M5.

### Stable-pair contract

Exact terminal/TB W>D>L precedence remains authoritative.

For non-terminal pairs, retain a pair only if:

- `sign(d50) == sign(d200)` ;
- both deltas non-zero ;
- `abs(d50) >= 10 cp` ;
- `abs(d200) >= 30 cp`.

Primary target = q200 ranking. q1000 never changes acceptance.

---

## 5. Support gate

Before interpreting model metrics require:

- selected parents exactly `4000` and exactly `1000/phase` ;
- accepted parents `>=3000` ;
- accepted each P0/P1/P2/P3 `>=500` ;
- accepted each parent colour `>=1200` ;
- every accepted parent contributes at least one stable pair ;
- zero forbidden-cohort canonical overlap ;
- candidate-freeze authentication PASS.

If support fails: verdict `JOINT_TD_DEEP_FRESH_SUPPORT_NOT_ESTABLISHED`, terminal, no retune and no runtime/Elo.

---

## 6. Readout

Score **the same accepted sibling rows** with S0–S4 and q1000.

Publish for each scorer:

- pairwise accuracy vs q200 stable target ;
- top-hit vs q200 ;
- phase P0/P1/P2/P3 ;
- parent colour ;
- parent count / stable pair count.

Bootstrap all principal deltas by parent cluster:

- samples `100000` ;
- seed `2026090421`.

Principal comparisons:

1. `C0 - D1` — primary causal hypothesis ;
2. `C0 - T0` — sanity/utility ;
3. `A6_G0 - T0` — optimized pure-T transfer ;
4. `B1 - T0` and `B1 - D1` — same-observable capacity generalization ;
5. `C0 - B1` ;
6. `q1000 - C0` — remaining dynamic headroom.

Publish disagreement decompositions at minimum:

- C0 correct / D1 wrong ;
- D1 correct / C0 wrong ;
- C0 correct / B1 wrong ;
- B1 correct / C0 wrong ;
- q1000 correct / C0 wrong ;
- C0 correct / q1000 wrong.

Also publish deep-transfer fractions:

`R_C0_from_D = (A_C0 - A_D1) / (A_1000 - A_D1)`

`R_C0_from_T = (A_C0 - A_T0) / (A_1000 - A_T0)`

with NA if denominator <=0.

---

## 7. Primary scientific gate

Verdict `JOINT_TD_DEEP_FRESH_CONFIRMED` **iff all** are true after support:

1. C0−D1 pairwise parent-bootstrap CI95 lower bound `> 0` ;
2. C0−D1 top-hit parent-bootstrap CI95 lower bound `> 0` ;
3. C0−T0 pairwise CI95 lower bound `> 0` ;
4. C0−D1 pairwise point delta is positive in every P0/P1/P2/P3 ;
5. C0−D1 pairwise point delta is positive for both parent colours ;
6. S0/S1/S2/S3/S4 artifact identities remain byte-identical to the freeze receipt ;
7. zero fit/refit after `candidate-freeze.json` ;
8. zero selfplay, strength games, promotion.

If support passes but any primary gate fails: `JOINT_TD_DEEP_FRESH_NOT_CONFIRMED`, terminal for this candidate. No tuning on Q1.

### Secondary pure-T classification

Independently report `A6_G0_DEEP_TRANSFER_CONFIRMED=true/false` using the same robust pattern:

- A6−T0 pairwise CI95 low >0 ;
- A6−T0 top-hit CI95 low >0 ;
- positive pairwise point delta in all phases and both colours.

This secondary classification cannot rescue a failed C0 primary gate.

### B1 classification

B1 is diagnostic in Q1. Report whether B1−T0 and B1−D1 pairwise CIs are positive, but do not create a new gate after seeing results.

---

## 8. What this experiment does NOT authorize

This prereg does **not** automatically promote a model or start an Elo match.

Even if C0 confirms, D1's six move-local inputs mean C0 is not yet a conventional context-free leaf evaluator. A separate preregistration must define the runtime mechanism and price its cost before force games.

Therefore throughout Q1:

- selfplay = 0 ;
- strength games = 0 ;
- promotion = false ;
- T/D/B1/C0 refits after freeze = 0.

A Q1 PASS authorizes only the next scientific design step: **runtime-capable joint mechanism + cost/parity preflight**, followed by a separately preregistered Elo gate if technically valid.

---

## 9. Interpretation matrix

### C0 > D1 confirmed deep fresh

The T+D complementarity is real beyond q1000 imitation. Joint student architecture becomes the priority runtime branch.

### C0 fails deep fresh but A6 passes

The q1000 joint gain was teacher-specific; prioritize pure PatternEval transfer and representation work.

### B1 beats D1 deep fresh while C0 fails

Nonlinear PatternEval observables generalize better than the static D stack; prioritize a production-capable nonlinear student.

### All static candidates remain far below q1000

The residual dynamic-information hypothesis is strengthened; feature discovery from q1000 residuals becomes mandatory.

---

## 10. Immutable seeds / constants

```text
candidate replay split = 2026090401
B1 replay seed          = 2026090402
fresh selection seed    = 2026090420
bootstrap seed          = 2026090421
selected parents        = 4000
phase quota             = 1000 each
q1000                    = 1000 nodes
q50                      = 50000 nodes
q200                     = 200000 nodes
bootstrap samples       = 100000
```

No seed or threshold above may change after merge of this document.
