# M15-C6 — separate context channel at decision time

Status: implemented and preregistered for HOME. A timing probe must size the
full 24-seed cell before it is queued.

## Question

M16-P retained `LAMBDA_50` as a small positive temporal signal. M15-C2R
independently retained `CONTEXT_30`. M15-C3 and M15-C4 then closed two ways of
compressing both signals into one scalar target, and M15-C5 showed that the
static conditional target gain does not survive one on-policy feedback step.

M15-C6 changes the causal channel rather than another dose. The temporal value
remains the only search value. Context is represented by a second linear
`PatternEval` table and can act only when the temporal search cannot clearly
separate its best root actions.

## Five arms, five fitted tables

Every seed generates one shared 1,024-game `G1_WIDE_OUTCOME` replay. Five
tables start from the same zero initialisation and consume the same explicit
batch schedule:

1. `OUTCOME`: terminal self-play WDL;
2. `LAMBDA_50`: the retained temporal return;
3. `CONTEXT_30`: the retained scalar conditional reference;
4. `ALIGNED_CONTEXT_HEAD`: pure cross-fitted conditional OOF prediction;
5. `SHUFFLED_CONTEXT_HEAD`: the same fold marginals with row alignment broken.

The two decision agents D and E share the **same fitted `LAMBDA_50` table**.
Only their second context table differs. No temporal/context sum is ever used
as their value target or search score.

## Preregistered decision rule

For a root search, let `V(a)` be the ordinary `LAMBDA_50` search score and
`V* = max_a V(a)`. The eligible band is

```text
V* - V(a) <= delta
```

If fewer than two searched actions are eligible, the temporal action is kept.
Otherwise the action with the highest negated context value of its child is
selected. Terminal children are read from the rules, and exact ties use the
smallest action ID. Context never changes internal search, node allocation,
temporal scores or visits.

`delta` is not tuned on development. For each seed it is the preregistered 25th
percentile (higher order statistic) of the top-two temporal score gaps on 512
unique non-terminal **train-replay** positions. D and E use the same `delta`.
At least 128 valid two-action searches are mandatory.

## Playing-strength gate

Twenty-four fresh seeds `279001..279024` use 512 paired, unique development
starts per matchup and identical search budgets. The two primary contrasts are

```text
ALIGNED_CONTEXT_CHANNEL - SHUFFLED_CONTEXT_CHANNEL
ALIGNED_CONTEXT_CHANNEL - LAMBDA_50
```

Both paired Student 95% lower bounds must exceed zero. There is no minimum
effect floor. Static zero-regret, calibration, credit-assignment and activation
statistics are mechanistic diagnostics only; they cannot rescue a strength
failure.

The power calculation is frozen at 24 seeds, conservative paired SD `0.0025`
and effect `0.0015` for sizing only, giving estimated power `0.80341`. The gate
still retains any precisely positive effect.

## Boundaries

- train and development only; `frozen_test` remains sealed;
- no oracle signal in any training target;
- no MegaCorpus data and no new 10×10 self-play;
- two inference tables are experimental and non-promotable;
- a pass authorises replication, not feedback, 10×10 transfer or production
  promotion.
