# M15 — deployable value-target screen

## Question

M14 established a large causal gap between the honest L2 self-play outcome target
and an exact-oracle value target while leaving policy learning essentially
unchanged. M15 asks the next operational question:

> Can a value label available in a normal unsolved search loop recover a useful
> fraction of the M14 oracle gain without consulting the oracle?

M15 is a screening experiment. It does **not** authorize production Jass changes
or direct 10x10 transfer.

## Frozen evidence entering M15

M14 uses the same twenty M13 seeds. Replacing only the training value target from
`selfplay_outcome` to `exact_oracle` changed mean value-sign learning by about
+9.4 percentage points on both development and confirmation while policy-mass
learning was effectively unchanged. The oracle arm is therefore treated as an
upper bound, not as a deployable recipe.

## Arms

All arms reuse the frozen M13/M14 L2 protocol and seeds.

| arm | training value target | oracle required | role |
|---|---|---:|---|
| baseline | terminal self-play W/D/L | no | honest control |
| search | bounded-negamax `root_score` at that exact state/ply | no | deployable candidate |
| blend | `0.5 * root_score + 0.5 * terminal_outcome` | no | lower-variance candidate |
| oracle | exact solved W/D/L | yes | diagnostic upper bound only |

The search score is already produced by the oracle-blind bounded negamax used by
self-play. It is clipped to `[-1, 1]` before becoming a value label.

## Why this is a clean paired experiment

The frozen L2 loop has exactly one generation. Therefore the model is not
updated until after all self-play positions and root search results for that run
have been generated. For a given seed, changing the training value target cannot
feed back into the trajectory, root search, policy target, state coverage or
sample count.

The experiment therefore changes only the scalar value label consumed by the
optimizer. Policy targets remain `score_softmax`; behavior remains greedy as
selected by M10/M11; search budget, split, model, optimizer and evaluation
cohorts remain frozen.

## Pre-registered success rule

A non-oracle candidate passes the M15 screen only if all of the following hold:

1. confirmation value-sign learning improves over the self-play-outcome baseline;
2. development value-sign learning also improves over baseline;
3. the confirmation improvement recovers at least 50% of the M14 oracle upper-bound gain;
4. the absolute policy optimal-mass shift versus baseline is at most 0.005 on both development and confirmation;
5. all twenty paired runs execute successfully on cpx62.

The 50% threshold is intentionally demanding: M15 is not looking for any tiny
positive effect but for a practical substitute for a meaningful part of the
oracle advantage.

## Target-quality diagnostics

For each arm M15 retains:

- value-sign learning on development and confirmation;
- policy optimal-mass learning on development and confirmation;
- mean target value MAE versus the exact oracle (diagnostic read only);
- mean exact W/D/L target rate where meaningful;
- all twenty paired seed deltas;
- fraction of the M14 oracle gain recovered.

Oracle labels are used only for evaluation and for the explicit oracle upper
bound arm. Search and blend target construction itself is oracle-blind.

## Decision after M15

If `search_root_score` or the 50/50 blend passes, the selected mechanism must be
replicated in a fresh non-oracle gate before any 10x10 contract is prepared.
M15 itself promotes no candidate.

If neither arm recovers 50% of the oracle gain, the next experiment should test
a more informative non-oracle temporal target (for example n-step/TD(lambda) or
reanalysis) rather than increasing self-play volume blindly.

## Hard boundaries

- every change remains below `mini_jass/`;
- no root Jass build/source/workflow is modified;
- no M15 arm is promotable;
- the oracle arm is diagnostic-only;
- direct 10x10 transfer remains forbidden;
- production Jass changes remain forbidden.
