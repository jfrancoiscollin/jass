# M16 — temporal value-target screen

## Question

M14 proved that the L2 network can learn value when the optimizer receives exact
oracle labels. M15 then tested two deployable same-state substitutes:

- bounded-search root score alone recovered **29.9%** of the M14 oracle gain;
- a 50/50 outcome/search blend recovered **41.8%**;
- neither reached the preregistered 50% screen;
- policy optimal-mass changed by less than 0.001 in either M15 candidate.

M16 asks whether the missing information is temporal:

> Does bootstrapping from search values observed later in the same trajectory
> recover at least half of the M14 oracle value-learning gain?

M16 is still an isolated diagnostic screen. It cannot promote a model, change
production Jass or authorize direct 10x10 transfer.

## Frozen entry evidence

M16 is machine-bound to the retained M15 readout:

- M15 result hash:
  `03f15b12a22ca27536efae5342dcc5d862f64a769c2a5afbf77e15a4c99d69b8`;
- status: `FAIL`;
- selected mechanism: none;
- M15 blend recovery fraction: `0.41759226`;
- M15 oracle upper bound: about `+0.0944` value-sign learning on both
  confirmation and development.

The compact evidence lives at
`mini_jass/artefacts/m15_search_value_target_screen.readout.v1.json` and its
SHA-256 is frozen in the M16 config.

## Why a temporal target

The M15 same-state search label asks the new value head to imitate the search
score produced at the same position. That score is useful but poorly calibrated
against exact W/D/L and remains tightly coupled to the current evaluator.

M16 instead uses a successor search value. Mini-Jass has no intermediate
rewards, so the Bellman relation changes only the point of view:

\[
V(s_t) = -V(s_{t+1})
\]

because the side to move alternates. For a trajectory with search root scores
`v_t` and terminal self-play outcome `z_t`, M16 defines the backward recurrence:

\[
G_t^\lambda =
-\left[(1-\lambda)v_{t+1} + \lambda G_{t+1}^\lambda\right]
\]

The final sampled position uses its honest terminal outcome:

\[
G_{T-1}^\lambda = z_{T-1}
\]

Consequences:

- `lambda = 0` is a one-step target `-v_{t+1}`;
- increasing lambda retains more terminal-outcome information;
- `lambda -> 1` approaches the ordinary propagated WDL target;
- no oracle value enters any temporal candidate.

## Arms

All five arms reuse the frozen M13/M14/M15 L2 protocol and the same twenty
paired seeds.

| arm | training value target | oracle used for target | role |
|---|---|---:|---|
| baseline | terminal self-play W/D/L | no | honest control |
| next_search | `-root_score(t+1)`; outcome on final sample | no | TD(0)-like one-step bootstrap |
| lambda_50 | temporal lambda-return, lambda `0.50` | no | balanced local/terminal target |
| lambda_80 | temporal lambda-return, lambda `0.80` | no | outcome-heavy temporal target |
| oracle | exact solved W/D/L | yes | diagnostic upper bound only |

Search scores are clipped to `[-1, 1]` before use.

## Isolation argument

The frozen L2 loop has exactly one generation. For a paired seed, all positions,
actions, policy targets and search traces are generated before training begins.
Changing the value label therefore cannot alter:

- the trajectory;
- root action allocation;
- search scores;
- state or action coverage;
- policy targets;
- sample count;
- optimizer schedule.

The only intended factor is the scalar value target consumed by the optimizer.

The wrapper also fails closed if:

- a generated sample has no corresponding root-search row;
- a trace row is duplicated;
- per-game samples are not contiguous by ply;
- lambda is outside `[0, 1)`.

## Preregistered scientific gate

A non-oracle temporal candidate passes only if all of the following hold:

1. all twenty paired runs complete on `cpx62`;
2. mean confirmation value-sign gain over baseline is positive;
3. mean development value-sign gain over baseline is positive;
4. the paired 95% confidence interval for confirmation gain is entirely above zero;
5. the paired 95% confidence interval for development gain is entirely above zero;
6. confirmation gain recovers at least 50% of the paired oracle upper bound;
7. absolute policy optimal-mass shift is at most `0.005` on confirmation;
8. absolute policy optimal-mass shift is at most `0.005` on development.

The paired confidence interval uses the frozen t19 critical value
`2.093024054408263`.

If several arms pass, M16 selects the one with the greatest oracle-gain recovery,
then the greatest confirmation value gain. Selection means only “candidate for
fresh-seed replication”; no M16 arm is promotable.

## Diagnostics retained

For every arm and paired seed, M16 records:

- confirmation and development value-sign learning;
- confirmation and development policy optimal-mass learning;
- paired value and policy deltas versus baseline;
- paired 95% value-gain intervals;
- fraction of the M14/M16 oracle gain recovered;
- target value MAE against the exact oracle;
- target exact-rate diagnostic;
- whether the arm exceeds the frozen M15 blend recovery.

## Decision after M16

If one temporal target passes, the next milestone must replicate it with fresh
seeds before any isolated 10x10 contract is prepared.

If all temporal candidates fail, the result points away from simple trajectory
bootstrapping. The next screen should then test one of:

- calibration of search scores against training-only outcomes;
- stronger-budget reanalysis after generation;
- multi-budget consensus targets;
- tablebase-anchored calibration where exact labels are available.

Increasing self-play volume alone is not the registered fallback.

## Hard boundaries

- every change remains below `mini_jass/`;
- no root Jass source, build, workflow or job is modified;
- temporal targets never read solved oracle values;
- the oracle arm is diagnostic-only;
- no M16 arm is promotable;
- production Jass changes remain forbidden;
- direct 10x10 transfer remains forbidden.
