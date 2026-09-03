# L3 — Decision-information implementation plan v1

Date: 2026-09-03
Status: implementation roadmap; no scientific gate, fit, game, promotion or compute authorization by itself.
Base at authoring: `develop` @ `0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220`.

## 0. Objective

Exploit the mathematics already present in Jass search and JFI as one coherent loop:

```text
search bounds / iteration stability
        -> decision uncertainty
        -> adaptive teacher compute
        -> parent-grouped sibling dataset
        -> WDL + ranking supervision
        -> Fisher-aware anchoring / active acquisition
        -> equal-node causal gate
        -> equal-time strength gate
```

The programme is deliberately staged so that instrumentation and offline shadow tests arrive before any change to search semantics, teacher allocation, model class or runtime strength.

This document does **not** amend the active JFI preregistration, does not authorize reads from consumed holdouts, and does not authorize new CPX62 jobs. JFI-C continues under its own frozen contract until its terminal verdict.

## 1. Programme-wide invariants

1. `CURRICULUM` remains champion until a separately preregistered fresh strength gate says otherwise.
2. Search/teacher/model changes are one-factor-at-a-time unless an explicit factorial experiment is preregistered.
3. Parent cluster is the unit of split, bootstrap and objective weighting for sibling-ranking science.
4. A returned alpha-beta score is never treated as exact unless the search contract says it is exact.
5. Interrupted iterations never become complete teacher labels.
6. Board identity, rule-state identity and search-context identity are stored separately.
7. Semantic move identity is canonicalized; duplicate capture paths that reach the same semantic move are never double-weighted.
8. Every runtime candidate is tested first at equal nodes, then at equal time.
9. Pairwise/listwise agreement is a transfer metric, never by itself a promotion gate.
10. New handcrafted feature families remain offline probes until independently confirmed and costed.
11. Any use of JFI classes waits for the terminal JFI-C verdict and authenticates the frozen Fisher/L2 artifacts.
12. No automatic promotion, bake or strength continuation is implied anywhere in this roadmap.

## 2. Workstream A — SearchDecisionTrace v1

### Goal

Turn the information already produced by iterative deepening, PVS, aspiration and TT bounds into a stable structured decision record without changing the searched tree.

### Proposed API

Add a passive optional pointer in `SearchLimits`:

```cpp
SearchDecisionTrace* decision_trace = nullptr;
```

with records at two levels:

- one record per completed/attempted root iteration;
- one record per semantic root action searched in that iteration.

Minimum action fields:

```text
semantic move id
score
bound = Exact | Lower | Upper
nodes / eval calls
alpha-before / beta
cutoff flag
zero-window/full-window flag
PVS re-search flag
PV hash + PV length
```

Minimum iteration fields:

```text
depth
aspiration attempt
window alpha/beta
completed/aborted
best semantic move
root score/bound
nodes/eval calls
```

### Derived mathematics

Represent every score as an interval:

```text
Exact(v) -> [v,v]
Lower(v) -> [v,+inf)
Upper(v) -> (-inf,v]
```

For chosen action `a*`:

```text
certified_at_current_horizon iff L(a*) > max_{b!=a*} U(b)
R_max(a*) = max_b U(b) - L(a*)
```

Also derive:

- best-move flip count across completed depths;
- first stable depth;
- score volatility;
- aspiration failure count;
- PVS re-search count;
- PV hash churn;
- unresolved-interval width.

### PR sequence

- **A1**: data types + passive root capture + deterministic serializer.
- **A2**: exact bound semantics tests and duplicate semantic-move grouping.
- **A3**: corpus exporter and readout metrics.

### Hard gate before use

With tracing OFF vs ON on a frozen root set:

```text
best move mismatch = 0
score mismatch = 0
completed depth mismatch = 0
nodes mismatch = 0
eval calls mismatch = 0
PV mismatch = 0
```

## 3. Workstream B — Adaptive deep sibling teacher

### Goal

Spend deep teacher nodes on ambiguous siblings instead of giving every sibling the same 5k/50k/200k ladder.

### Scientific boundary

The first implementation must be a **shadow simulator** over already-produced q5k/q50/q200 sibling tables. It performs no new search. Only after a frozen shadow verdict can an adaptive teacher executable be preregistered.

### B1 — shadow racing simulator (first PR)

Input: a `groups.tsv` emitted by the existing `deep_sibling_teacher.cpp` contract containing at least:

```text
parent_id
exact_parent_utility / terminal/TB flags
q5k_parent
q50_parent
q200_parent
nodes5k / nodes50k / nodes200k
```

No q200 row may influence which arm survives from 5k to 50k. q200 is read only for retrospective loss/regret measurement after the simulated allocation is frozen per parent.

Frozen v1 shadow policy:

1. Terminal/TB-exact siblings are resolved without simulated search cost.
2. All unresolved siblings receive q5k.
3. Rank by q5k parent score, deterministic semantic-row tie-break.
4. Promote to q50 every unresolved sibling whose q5k score is within `M5=100 cp` of the q5k best; always promote at least the top 2 unresolved siblings.
5. At q50, promote to q200 every surviving sibling whose q50 score is within `M50=60 cp` of the q50 best; always promote at least the top 2 survivors when at least two exist.
6. All promotion decisions are made before reading the corresponding deeper score for that parent.
7. The simulated chosen move is the best available exact/TB result if one dominates by WDL; otherwise the best q200 among q200 survivors. If exactly one unresolved survivor remains before q200, it may be chosen without q200 only for cost accounting and is marked `uncertified_shadow`.

The margins are fixed implementation constants for v1 shadow only. They are **not** approved adaptive-teacher thresholds and cannot be tuned on the same corpus.

Primary shadow outputs:

```text
full_ladder_nodes
shadow_nodes
node_ratio = shadow_nodes / full_ladder_nodes
teacher_node_saving = 1 - node_ratio
best_move_match_vs_full_q200
mean_q200_regret_cp
p95_q200_regret_cp
catastrophic_regret_rate(|regret| >= 100 cp)
parent counts by survivor pattern
```

All metrics are parent-level or parent-cluster bootstrap-ready.

### B2 — threshold confirmation

After B1 exists, run it on historical development teacher tables only. Select/freeze one policy on a designated development set, then confirm unchanged on a disjoint historical/fresh-but-already-consumed diagnostic set if available without violating prior contracts. If no legal disjoint table exists, generate a new target-blind confirmation only under a new preregistration.

Required before real adaptive compute:

```text
node saving materially > 0
best-move loss bounded by preregistered threshold
q200 regret bounded
no phase/colour collapse
```

### B3 — real adaptive teacher

A new executable performs geometric racing with fresh TT/search state and exact node caps. It may use structured alpha-beta intervals from Workstream A when available; before A is available it uses only preregistered score-margin survival.

Preferred eventual ladder:

```text
B0 -> 2*B0 -> 4*B0 -> ... -> Bmax
```

A sibling can be dropped only by a preregistered safe rule. If bound-aware tracing is available, a sufficient dominance certificate is:

```text
U(b) < max_a L(a)
```

Final teacher efficiency metric:

```text
certified decisions per 1e6 teacher nodes
```

## 4. Workstream C — SiblingDataset v2

### Goal

Make the parent decision the first-class training object rather than unrelated child rows.

### Schema

One parent group contains:

```text
board identity
rule-state identity
search-context identity
phase / colour / source provenance
all semantic legal actions
child position identity per action
terminal/TB exactness
static baseline score
teacher observations by budget
bound/exactness flags
certified pair relations
stability diagnostics
teacher compute spent
artifact/code/config SHAs
```

### PR sequence

- **C1**: versioned schema + Python reader/writer + invariants.
- **C2**: converter from existing Deep Sibling `children.jnnw + groups.tsv`.
- **C3**: parent-cluster splitter, canonical symmetry dedup and overlap proof.

### Invariants

- no siblings from one canonical parent cross a split;
- each parent contributes bounded/equal total training weight;
- parent POV is explicit and tested;
- duplicate semantic actions do not increase objective weight.

## 5. Workstream D — WDL + listwise decision objective

### Goal

Preserve global value while learning the local decision ordering exposed by the teacher.

For child action `a` of parent `s`:

```text
q_theta(s,a) = -V_theta(child(s,a))
```

For exact teacher scores on a parent, define:

```text
pi_T(a|s) = softmax(Q_T(s,a)/tau)
pi_theta(a|s) = softmax(q_theta(s,a)/tau)
```

Candidate objective:

```text
L = L_WDL
  + lambda_decision * sum_s CE(pi_T(.|s), pi_theta(.|s))
  + 0.5 * sum_j lambda_j * (theta_j - theta0_j)^2
```

For non-exact actions use only certified order relations, never invented exact margins.

### D1 screen

Three fixed recipes on identical TRAIN/DEV parents:

```text
WDL only
WDL + decision
WDL + decision + Fisher-aware anchor
```

No strength in the screen. Candidate bytes freeze before any fresh confirmation.

### Convexity requirement

For linear PatternEval, keep the listwise score linear in parameters and use positive quadratic anchoring so the production candidate optimization remains convex/strongly convex where practical.

## 6. Workstream E — Fisher x decision active acquisition

### Goal

Separate parameter uncertainty from decision ambiguity.

JFI parameter leverage:

```text
F(s) = sum_j x_j(s)^2 / (F_j + lambda_j)
```

Decision ambiguity comes from Workstream A/B diagnostics and must be defined before labels are read.

First experiment is factorial, not an arbitrary weighted sum:

```text
U  = uniform
F  = Fisher only
D  = decision ambiguity only
FD = Fisher + decision intersection/ranking
```

All arms have identical volume and matched phase/colour/opening/legal-move strata.

Only after a confirmed interaction may a continuous combined acquisition score be introduced.

## 7. Workstream F — uncertainty-controlled search budget

### Goal

Use uncertainty to decide **how much to search**, never to directly bias the game value.

Approximate evaluation uncertainty:

```text
sigma2(s) ~= sum_j x_j(s)^2 / (F_j + lambda_j)
```

For two actions:

```text
sigma2(a-b) ~= sum_j (x_j(a)-x_j(b))^2 / (F_j + lambda_j)
```

First runtime probe is root-only and behaviorally bounded:

- allocate extra root nodes only when top actions remain ambiguous;
- stop additional allocation once a decision certificate/stability rule passes;
- do not alter leaf evaluation score;
- do not alter alpha/beta mathematically.

Any LMR/RFP/selectivity modulation is a later separate experiment.

## 8. Workstream G — new structural mathematics

New feature families are discovery probes only:

### G1 `TEMPO_PARITY`

- promotion-path parity;
- reserve-tempo parity by wing;
- critical-square parity;
- king opposition parity;
- parity of route-length differences.

### G2 `PROMOTION_FLOW`

Graph-derived:

- disjoint promotion routes;
- min cut blocking all promotion routes;
- articulation squares;
- matching between men and promotion destinations;
- corridor contention.

### G3 `CAPTURE_DAG`

- distinct maximal capture paths;
- distinct semantic child states;
- landing entropy;
- path convergence;
- safe-destination cut metrics.

### G4 `CONTROL_GRAPH`

- controlled-square components;
- contested frontier;
- bottlenecks/articulation squares;
- wing connectivity and rupture distance.

Required path:

```text
offline extractor -> historical sham screen -> fresh confirmation
-> PatternEval absorption probe -> runtime cost probe -> strength prereg
```

## 9. Workstream H — compact factorized PatternEval

Open only if a fresh capacity test shows that nonlinear same-observable models retain teacher signal that linear PatternEval cannot absorb.

Candidate form:

```text
V(s) = sum_i w_i[b_i]
     + sum_{i<j} <u_i[b_i], u_j[b_j]>
     + w_dense^T z(s)
```

with small latent rank (`k=4` or `8` preregistered, no open sweep on confirmation data).

Motivation: represent cross-pattern interactions while retaining sparse lookup, quantization and cheap runtime.

## 10. Workstream I — exact endgame value object

Extend the current WLD seam with explicit exactness/distance metadata only when the database source supports it:

```text
WDL
distance_to_conversion / zeroing
rule-counter sensitivity
exactness
```

MTC/DTW-style distances are local endgame information, not a global pseudo-target. Previous global conversion-gradient target failures remain closed evidence against manufacturing such a gradient broadly.

## 11. Delivery order and dependencies

```text
CURRENT JFI-C terminal
       |
       +-----------------------------+
       |                             |
       v                             v
A1 SearchDecisionTrace          B1 adaptive shadow  <- FIRST PR OF POINT 2
       |                             |
A2/A3 trace validation               B2 shadow confirmation
       |                             |
       +-------------+---------------+
                     v
              B3 real adaptive teacher
                     |
                     v
              C SiblingDataset v2
                     |
                     v
              D WDL + listwise
                     |
            +--------+--------+
            v                 v
       E active acquisition   G structural probes
            |                 |
            v                 v
       F root budget      H capacity-dependent
            |
            v
       equal-node -> equal-time gates
```

Parallelism rule: implementation/tests/docs may proceed while JFI-C runs, but no stage may consume JFI output or launch science that depends on it before the terminal authenticated verdict.

## 12. PR ledger

Planned minimum sequence:

1. `decision-math: adaptive teacher shadow simulator v1` — **this branch/PR**.
2. `search: add passive SearchDecisionTrace v1`.
3. `teacher: confirm/freeze adaptive racing policy` (docs/readout; no real adaptive search yet).
4. `teacher: implement adaptive sibling racing v1`.
5. `data: add SiblingDataset v2 schema + converter`.
6. `train: add parent-listwise PatternEval objective`.
7. `train: add frozen JFI-coordinate anchoring` after JFI terminal.
8. `science: Fisher x decision acquisition factorial`.
9. `search: root uncertainty budget controller` if prior stages pass.
10. feature/capacity PRs only under the gates above.

## 13. Definition of success for the programme

The programme is successful only if it demonstrates a causal gain on fresh data and then in play while respecting compute cost. The ultimate chain is:

```text
more useful information / teacher node
-> better fresh decision agreement / regret
-> candidate survives equal-node gate
-> candidate survives equal-time gate
```

No earlier proxy is allowed to substitute for the later gate.
