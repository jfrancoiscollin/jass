# M23 — Mix strategy screen and complete self-play optimization program

## Why this milestone exists

M21 produced the first strong evidence that **mixing generations** can improve playing strength at equal unique-data volume: `MIX - G1_WIDE` was strongly positive in arena, while the latest generation alone (`G8_ONLY`) was worse than G1 in arena. The immediate next question is therefore not whether replay exists, but **how temporal memory should be structured**.

At the same time, Mini-Jass is now cheap enough on cpx62 to serve as a systematic self-play laboratory. We should use it to re-evaluate the complete self-play recipe, including parameters that were previously explored only once, underpowered, confounded, or only on 10x10.

This document preregisters both layers:

1. **M23-A: temporal mix strategy** — find the best history/current mixing law at fixed total training dose;
2. **M23-B onward: self-play optimization campaign** — screen and then optimize all major self-play parameters with arena strength as the primary endpoint and the oracle only as a diagnostic microscope.

No result from this program directly authorizes a 10x10 production change. Any winning mechanism must replicate on fresh seeds and later receive a dedicated 10x10 translation gate.

---

# M23-A — temporal mix strategy

## Frozen premise

The mechanism under test is temporal mixture. The total number of unique training samples and optimizer updates must be matched fail-closed across arms. Generation 8 is the current generation; generations 1-7 form history.

The primary endpoint is **paired arena score versus the same frozen initial model**, with a fresh 20-seed family. Learning score is secondary. Oracle WDL exactness is diagnostic only.

## Arms

All arms allocate 50% of the training pool to G8 and 50% to history unless otherwise stated.

1. `UNIFORM_HISTORY_50`
   - 50% G8.
   - Remaining 50% uniformly over G1-G7.
   - Baseline temporal replay.

2. `RECENT_WINDOW_50`
   - 50% G8.
   - Remaining 50% uniformly over G5-G7.
   - Tests short memory / high plasticity.

3. `EXP_DECAY_50`
   - 50% G8.
   - Remaining 50% exponentially weighted by age over G1-G7.
   - Default preregistered half-life: 2 generations.

4. `RESERVOIR_50`
   - 50% G8.
   - Remaining 50% from an unbiased reservoir over all G1-G7 samples.
   - Tests age-neutral long memory at bounded storage.

5. `ANCHOR_50`
   - 50% G8.
   - 25% G1-G2 anchor.
   - 25% uniformly from G3-G7.
   - Tests whether explicit long-term anchors protect useful early structure.

6. `UNIFORM_ALL`
   - Equal weight over G1-G8.
   - Reproduces the broad M21-style mixture as the calibration arm.

7. `CURRENT_ONLY`
   - 100% G8, dose matched with replacement.
   - Negative/control arm for recency-only.

## Dose-response follow-up

If one 50/50 history policy wins, a second stage varies only current-generation share while keeping that history policy fixed:

- 25% current / 75% history
- 50% current / 50% history
- 75% current / 25% history
- 100% current

The purpose is to estimate the stability-plasticity response curve. This stage is not run unless the history-shape screen first identifies a replicated winner or a clear equivalence class.

## Gates

A mix strategy becomes a candidate only if, against `UNIFORM_HISTORY_50` or the preregistered M21 calibration baseline:

- paired arena 95% CI is entirely above zero;
- practical arena gain exceeds the preregistered floor;
- unique-sample count and optimizer update count are exactly matched;
- no oracle field is read during sample construction or training;
- result repeats on a fresh 20-seed replication before any 10x10 translation work.

If multiple strategies are statistically tied, choose the simplest/storage-cheapest strategy rather than the largest point estimate.

---

# M23-B+ — complete self-play configuration search

## Principle

Do **not** run a giant Cartesian grid. The self-play parameters interact and a one-factor-at-a-time search can select a setting that is only good under the current baseline. The campaign therefore uses three stages:

1. **screening** — broad, balanced/fractional-factorial or orthogonal design to identify main effects and large two-way interactions;
2. **local optimization** — response-surface / focused grids only around surviving factors;
3. **fresh-seed replication** — final configuration versus frozen baseline on new seeds.

Every stage uses 20 paired seeds by default. Arena is primary. Learning score, oracle target quality, coverage, entropy, WDL confusion and search diagnostics explain mechanisms but cannot override arena.

## Factor families to re-evaluate

### A. Opponent / population structure

Re-evaluate how self-play opponents are chosen.

Levels to screen:

- mirror self-play: current model vs itself;
- current vs previous champion;
- current vs rolling historical sample;
- deliberately asymmetric strength: current vs weaker historical model;
- deliberately asymmetric strength: current vs stronger available model/teacher where the protocol permits;
- mixed population schedule across the above.

Diagnostics:

- color/role asymmetry;
- win/draw/loss balance;
- state-distribution overlap;
- exploitability/arena transfer;
- whether one side dominates generated targets.

The goal is not merely balanced win-rate. A useful imbalance may expose gradients that mirror self-play misses.

### B. Search resource budget

Screen resource control independently from exploration.

Node-budget candidates should span orders of magnitude rather than adjacent values, for example:

- 4, 8, 16, 32, 64, 128 nodes per root where supported;
- fixed budget versus variable budget sampled from a preregistered distribution;
- per-position phase-dependent budget if a fixed-budget winner leaves a clear phase-specific weakness.

Record consumed nodes, not just requested nodes.

### C. Depth

Depth must be re-evaluated independently of node budget.

Candidate levels:

- shallow / medium / deep fixed depths;
- uncapped depth with node budget as the actual limiter;
- variable depth sampled across games/positions.

Depth comparisons require a common evaluation search in the arena. Never compare arms using their own depth as the probe, which caused the M18 confound.

### D. Move-time / clock budget

Add explicit wall-clock self-play modes:

- fixed move time per move (e.g. short / medium / long);
- variable move time sampled per game;
- chess-clock-like total time + increment schedules;
- phase-dependent move time;
- mixed time-control curriculum.

Because wall-clock search is hardware/scheduler sensitive, these cells must run on the same cpx62 host class and record realized nodes, time, NPS and timeout counts. Move-time is a **different causal resource policy**, not a disguised node-budget comparison. Any apparent time-control winner must be checked against a realized-node-matched control.

### E. Exploration / move selection

Re-evaluate the complete behavior-policy family:

- greedy top-1;
- top-K uniform for K = 2, 3, 4 where legal branching permits;
- epsilon-greedy at several epsilon levels;
- softmax over search scores with temperature schedule;
- visit-distribution sampling where available;
- mixed strategy: exploratory opening phase then greedy;
- margin-conditioned exploration: explore only when top moves are close.

Important: distinguish **Top-K** from **uniform over all legal moves**. Full-uniform is an extreme negative/control, not a default exploration candidate.

### F. Root allocation / search allocation

Re-evaluate:

- balanced root allocation;
- best-first / score-proportional allocation;
- uncertainty/margin-aware allocation;
- uniform minimum floor plus adaptive remainder.

Measure actual node allocation per legal move and its interaction with Top-K/softmax behavior.

### G. Start-state / opening distribution

Screen:

- canonical initial state;
- random train-split restarts;
- opening-randomized starts;
- phase-stratified starts;
- curriculum from broad restarts toward natural initial-state games;
- mixture of natural and restart positions.

Coverage alone is not a success endpoint; M21/L3 already warn that more novelty need not produce more strength.

### H. Game horizon / termination

Re-evaluate:

- max plies / safety draw handling;
- exact terminal/tablebase termination where available;
- adjudication thresholds;
- whether truncated games are dropped, drawn, or separately labelled.

This family is lower priority where previous Mini-Jass cells already showed no truncation, but it must remain in the final recipe audit.

### I. Replay / temporal memory

Use the M23-A winner as the default history policy, then screen:

- history fraction;
- history horizon/window;
- age weighting;
- reservoir size;
- whether replay is stratified by generation or sampled globally;
- generation-balanced batches versus sample-balanced batches.

Do not re-open arbitrary priority by oracle exactness. Oracle cannot drive sample weights.

### J. Self-play diversity across resource regimes

Once single-resource policies are understood, test **mixtures of game types** rather than a single fixed control:

- mixed node budgets;
- mixed depths;
- mixed move times;
- mixed opponent strengths;
- mixed exploration temperatures;
- mixed time controls.

This directly tests the hypothesis that a heterogeneous self-play distribution generalizes better than a single optimized regime.

---

# Screening design

## Stage S1 — categorical/main-effect screen

Freeze M23-A winner for replay. Use an orthogonal/fractional design covering the highest-value factors:

- opponent structure;
- resource policy (node-limited vs time-limited);
- low/high resource dose;
- depth cap mode;
- behavior policy family;
- exploration intensity;
- root allocation;
- start-state source.

Use enough arms to estimate main effects and preselected two-way interactions, especially:

- resource × exploration;
- resource × opponent imbalance;
- depth × node budget;
- exploration × root allocation;
- opponent × replay mix;
- start-state × exploration.

Do not interpret non-estimable interactions.

## Stage S2 — numerical response surfaces

For factors surviving S1, fit local curves rather than selecting the best discrete point. Examples:

- node budget on log2 scale;
- epsilon / temperature;
- current/history fraction;
- opponent-strength gap;
- move time on log scale.

Prefer interior optima that replicate over boundary maxima.

## Stage S3 — heterogeneous-regime test

Compare the best fixed recipe with a distribution over good regimes. Example:

`BEST_FIXED` vs `MIXED_BUDGETS` vs `MIXED_TIME_CONTROLS` vs `MIXED_OPPONENTS` vs `MIXED_ALL_SAFE`.

This stage answers whether diversity itself is a training signal.

## Stage S4 — final recipe replication

Freeze one complete configuration and compare it with the current Mini-Jass reference on at least 20 fresh paired seeds, with:

- paired arena CI;
- arena versus initial and versus prior reference;
- sealed confirmation learning metrics;
- oracle diagnostics post-hoc;
- compute-normalized strength report;
- exact config hash and deterministic schedule where applicable.

Only after S4 may a separate PR propose a 10x10 translation experiment.

---

# Metrics and guardrails

Primary:

- paired arena strength on a common evaluation search and common starts.

Mandatory secondary:

- value-sign learning;
- policy optimal mass;
- WDL target exactness/MAE;
- state and trajectory diversity;
- draw rate and decisive conversion;
- realized nodes, depth, time, NPS;
- per-generation contribution;
- color/role asymmetry;
- training sample count and unique count.

Rules:

- no selection on oracle metrics;
- no changing the arena search between arms;
- no post-hoc winner without fresh-seed replication;
- 20 seeds default; increase when power analysis says an observed practical effect needs more;
- batch many scientific arms into one CPX attempt to amortize runner/worktree overhead;
- compact result must remain below the GitOps inline limit and include phase timings;
- failed transport/summary publication is a failed experiment even if science completed.

---

# Expected output of the program

The final deliverable is not a collection of individually winning knobs. It is a **fully specified self-play distribution**:

- opponent population policy;
- temporal replay policy;
- node/time/depth resource distribution;
- move-selection/exploration policy;
- root allocation;
- start-state distribution;
- termination policy;
- optional heterogeneity schedule across game types.

That configuration should be the first Mini-Jass recipe chosen primarily by replicated arena strength while using the exact oracle only to understand mechanism and failure modes.
