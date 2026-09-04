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

Instrumentation, implementation and historical shadow diagnostics are separated from scientific stages that consume fresh labels, JFI outputs or new compute.

## 1. Programme-wide invariants

1. `CURRICULUM` remains champion until a separately preregistered fresh strength gate says otherwise.
2. Search/teacher/model changes are one-factor-at-a-time unless a factorial is preregistered.
3. Parent cluster is the unit of split, bootstrap and objective weighting.
4. Alpha-beta scores are never treated as exact unless their bound contract establishes exactness.
5. Interrupted iterations never become complete teacher labels.
6. Board identity, rule-state identity and search-context identity are stored separately.
7. Semantic move identity is canonicalized; duplicate capture paths never gain extra weight.
8. Runtime candidates are tested first at equal nodes, then at equal time.
9. Pairwise/listwise agreement is a transfer metric, never a promotion gate by itself.
10. New feature families remain offline probes until independently confirmed and costed.
11. Any use of JFI classes waits for the authenticated terminal JFI-C verdict.
12. No automatic promotion or bake is implied.

## 2. Workstream A — SearchDecisionTrace v1

Add a passive optional `SearchDecisionTrace*` to `SearchLimits`. Record every attempted/completed root iteration and every semantic root action: score, `Exact/Lower/Upper` bound, nodes/eval calls, alpha/beta, cutoff, PVS re-search, PV hash/length and completion state.

Derived intervals:

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

Also derive best-move flips, first stable depth, score volatility, aspiration failures, PVS re-searches and PV churn.

PRs: **A1** passive types/capture/serializer; **A2** bound and semantic-move tests; **A3** exporter/readout.

Hard trace gate: tracing OFF vs ON must have zero mismatch for best move, score, completed depth, nodes, eval calls and PV.

## 3. Workstream B — Adaptive deep sibling teacher

### B1 — historical shadow simulator — first PR of point 2

Input is an existing `deep_sibling_teacher.cpp` `groups.tsv`. No search and no fit are performed.

Frozen shadow policy:

1. Terminal/TB-exact siblings are resolved at zero *simulated* search cost.
2. Every unresolved sibling receives q5k.
3. Promote q5k siblings within `M5=100 cp` of the best, with deterministic row tie-break and at least two survivors where possible.
4. Promote q50 survivors within `M50=60 cp`, again preserving at least two where possible.
5. q200 is never read for a survival decision.
6. If one unresolved survivor remains before q200, choose it without q200 and mark `uncertified_shadow`.
7. Otherwise q200 is paid only for q50 survivors and chooses among them.
8. Historical `full_ladder_nodes` includes all q5k/q50/q200 searches actually recorded by the producer, including exact rows; the shadow numerator may shortcut those exact rows at zero simulated cost.

Primary outputs: full/shadow nodes, node ratio/saving, best-move match vs full q200, mean/p95 retrospective q200 regret, catastrophic-regret rate and survivor patterns.

The margins are reproducible shadow constants only. They do not authorize a real adaptive teacher.

### B2 — policy confirmation

Run B1 on legally reusable historical development tables. A policy may be frozen only before confirmation on a disjoint table. If no legal disjoint table exists, new confirmation compute requires a preregistration.

Required evidence before B3: material node saving, bounded best-move loss/regret and no phase/colour collapse.

### B3 — real adaptive teacher

Only after B2 preregistration/confirmation. Use fresh search state and exact node caps. Eventually prefer a geometric ladder `B0 -> 2B0 -> 4B0 -> ... -> Bmax`. When Workstream A bounds are available, safe dominance may use `U(b) < max_a L(a)`.

Primary efficiency metric: `certified decisions / 1e6 teacher nodes`.

## 4. Workstream C — SiblingDataset v2

Make the parent decision first-class. Each group stores board/rule/context identities, phase/colour/provenance, all semantic actions, child identities, terminal/TB exactness, static baseline, teacher observations by budget, bounds, certified relations, stability, compute and artifact/config SHAs.

PRs: **C1** schema/reader/writer; **C2** converter from existing sibling outputs; **C3** parent-cluster split, symmetry dedup and overlap proof.

## 5. Workstream D — WDL + listwise decision objective

For action `a` of parent `s`, `q_theta(s,a)=-V_theta(child(s,a))`. For exact teacher scores:

```text
pi_T(a|s) = softmax(Q_T(s,a)/tau)
pi_theta(a|s) = softmax(q_theta(s,a)/tau)
L = L_WDL + lambda_decision * CE(pi_T,pi_theta)
  + 0.5 * sum_j lambda_j * (theta_j-theta0_j)^2
```

For non-exact actions use only certified order relations. Screen WDL-only, WDL+decision and WDL+decision+Fisher anchor on identical parents. No strength in the screen. Keep the linear PatternEval objective convex/strongly convex where practical.

## 6. Workstream E — Fisher × decision active acquisition

Separate parameter uncertainty from decision ambiguity. First experiment is factorial:

```text
U  uniform
F  Fisher only
D  decision ambiguity only
FD Fisher + decision
```

Identical volume and matched strata. No continuous combined score until an interaction is confirmed. This workstream explicitly depends on authenticated JFI-C outputs.

## 7. Workstream F — uncertainty-controlled root budget

Use uncertainty to decide how much to search, never to bias value directly. First probe is root-only: add nodes when top actions remain ambiguous and stop extra allocation when a frozen stability/certificate rule passes. Do not alter leaf scores or alpha/beta semantics. LMR/RFP modulation is a later separate experiment.

## 8. Workstream G — structural mathematics probes

Offline discovery families:

- `TEMPO_PARITY`: promotion/reserve/critical-square/opposition parity;
- `PROMOTION_FLOW`: disjoint routes, min cut, articulation squares, matching, corridor contention;
- `CAPTURE_DAG`: maximal paths, semantic child states, landing entropy and path convergence;
- `CONTROL_GRAPH`: controlled components, contested frontier, bottlenecks and wing connectivity.

Required path: extractor -> sham historical screen -> fresh confirmation -> PatternEval absorption -> runtime cost -> strength preregistration.

## 9. Workstream H — compact factorized PatternEval

Open only if a fresh capacity test shows nonlinear same-observable signal that linear PatternEval cannot absorb. Candidate:

```text
V(s) = sum_i w_i[b_i]
     + sum_{i<j} <u_i[b_i],u_j[b_j]>
     + w_dense^T z(s)
```

Use only preregistered small latent ranks; no open sweep on confirmation data.

## 10. Workstream I — exact endgame value object

Extend WLD only where the source supports exact metadata: distance-to-conversion/zeroing, rule-counter sensitivity and exactness. MTC/DTW distances remain local endgame information, not a manufactured global pseudo-target.

## 11. Delivery lanes and dependencies

Implementation/historical-diagnostic work is **not** downstream of JFI-C:

```text
IMPLEMENTATION / HISTORICAL LANE (may proceed independently)

A1 SearchDecisionTrace ----> A2/A3

B1 adaptive shadow --------> B2 historical shadow development
                                  |
                                  | requires a separately frozen confirmation
                                  v
                              B3 real adaptive teacher
                                  |
                                  v
                              C SiblingDataset v2
                                  |
                                  v
                              D WDL + listwise
```

JFI-dependent science has a separate gate:

```text
AUTHENTICATED JFI-C TERMINAL
          |
          +----> Fisher-aware anchoring in D
          |
          +----> E Fisher x decision acquisition
                         |
                         v
                    F root budget
```

`G` structural probes may be implemented offline independently, but any fresh confirmation/runtime continuation follows its own preregistration. `H` is capacity-dependent on confirmed evidence.

Therefore B1 in PR #771 never crossed a JFI terminal gate: it is implementation plus replay of already-produced tables only. New compute or science that consumes JFI remains gated by the authenticated terminal.

## 12. PR ledger

1. `decision-math: adaptive teacher shadow simulator v1` — PR #771.
2. `search: add passive SearchDecisionTrace v1`.
3. `teacher: freeze/confirm adaptive racing policy` — no real adaptive search yet.
4. `teacher: implement adaptive sibling racing v1`.
5. `data: add SiblingDataset v2 schema + converter`.
6. `train: add parent-listwise PatternEval objective`.
7. `train: add frozen JFI-coordinate anchoring` only after authenticated JFI terminal.
8. `science: Fisher x decision acquisition factorial`.
9. `search: root uncertainty budget controller` if prior gates pass.
10. Feature/capacity PRs only under their gates.

## 13. Definition of success

```text
more useful information / teacher node
 -> better fresh decision agreement / regret
 -> candidate survives equal-node gate
 -> candidate survives equal-time gate
```

No earlier proxy substitutes for a later causal gate.
