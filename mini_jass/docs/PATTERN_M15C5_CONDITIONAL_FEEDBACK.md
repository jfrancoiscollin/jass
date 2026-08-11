# M15-C5 — conditional information under on-policy feedback

Status: implemented and preregistered for HOME; neither timing probe nor full
cell is queued by this PR.

## Why this is the next Mini-Jass question

M15-C2R established a repeatable positive `CONTEXT_30` target effect. M15-C4
then reconfirmed the static conditional signal while rejecting a separate
conditional-residual optimisation path. The contextual auxiliary-head path was
already tested by C1/C2 and remains rejected. Repeating it would not answer the
open question.

The missing question is feedback: after the conditional target changes the G1
model, does the benefit survive when that model changes the positions that feed
G2 training?

## Paired two-generation design

Twenty-four fresh seeds `278001..278024` start from the same zero PatternEval.
For each seed:

1. Generate one shared 1,024-game G1 replay.
2. Train `OUTCOME_G1` and `CONTEXT_30_G1` from the identical initial model with
   the identical explicit batch schedule.
3. Let each G1 model generate its own paired 1,024-game G2 replay.
4. Continue `OUTCOME_G1` on outcome labels from its replay and
   `CONTEXT_30_G1` on cross-fitted `CONTEXT_30` labels from its own replay.
5. Continue a second copy of `CONTEXT_30_G1` with the same conditional recipe
   on the outcome arm's G2 replay.

The fifth arm is a distribution decomposition. It shares the context G1 parent
with the on-policy context arm, but substitutes the outcome replay. Their
difference estimates the contribution of the changed state distribution rather
than the retained G1 model or target formula.

All conditional predictions are fitted out of fold by complete self-play game.
Targets use terminal self-play WDL only; the oracle never enters training.

## Primary gate

The primary contrast is
`CONTEXT_30_G2_OWN_REPLAY - OUTCOME_G2`. Its paired Student 95% lower bounds
must exceed zero on both development zero-regret and the 512-pair strength
arena. There is no decision effect floor: a precisely positive gain is retained
even if it is small.

`CONTEXT_30_G1 - OUTCOME_G1` is a fresh sanity replication. The G2-minus-G1
difference says whether feedback compounds, preserves or erodes the effect. The
own-replay versus outcome-replay context contrast localises any erosion to the
state distribution.

This is not a promotion cell. It adds no inference parameters and reads train
and development only. `frozen_test` remains sealed.

## Runtime protocol

Probe seed `278000` runs the exact five fits, three 1,024-game generations and
three 512-pair arenas but publishes timing and contracts only. HOME must report
hostname `User`, `nproc=16` and at least 10 GiB free. The wrapper reuses
`/home/jf/.cache/mj-m15p-venv`; it deliberately contains no PyTorch install
path.

The 24-seed cell can be queued only after the measured probe rate and numeric
ETA are reviewed and JFC gives a new post-sizing GO.
