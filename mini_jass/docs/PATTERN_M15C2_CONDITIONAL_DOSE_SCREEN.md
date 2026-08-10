# M15-C2 — conditional-target interior dose screen

Status: preregistered and implemented, not queued.

## Why M15-C2 exists

M15-C established that aligned conditional information changes what the scalar
`PatternEval` learns. At the frozen 50% dose, `CONTEXT_BLEND_50` beat its
marginal-matched shuffled control by `+0.0160159` development zero-regret
(95% CI `[+0.0145843, +0.0174476]`) and raw outcome by `+0.0030931`
(`[+0.0024638, +0.0037224]`), positive on all 20 seeds. The latter missed the
old practical threshold `+0.0039159`, so M15-C's formal status was `FAIL` even
though both confidence intervals excluded zero.

The same run showed that replacing outcome entirely by the conditional
prediction was harmful (`CONTEXT_ONLY - OUTCOME = -0.0189698`). Together with
the zero-dose baseline and positive 50% blend, this implies an interior
optimum. M15-C2 tests that dose hypothesis without changing the architecture,
replay source or conditional estimator.

## Arms and frozen primary

Every fresh paired seed generates one 1,024-game `G1_WIDE_OUTCOME` replay.
Seven models see the same train rows, initialization, explicit batch schedule,
optimizer and update count. Only `ReplaySample.value_target` changes:

| arm | target | role |
|---|---|---|
| `OUTCOME` | terminal WDL | baseline |
| `SHUFFLED_CONTEXT_20` | 80% WDL + 20% shuffled conditional WDL | exploratory matched control |
| `CONTEXT_20` | 80% WDL + 20% aligned conditional WDL | exploratory dose |
| `SHUFFLED_CONTEXT_30` | 70% WDL + 30% shuffled conditional WDL | primary matched control |
| `CONTEXT_30` | 70% WDL + 30% aligned conditional WDL | sole confirmatory candidate |
| `SHUFFLED_CONTEXT_40` | 60% WDL + 40% shuffled conditional WDL | exploratory matched control |
| `CONTEXT_40` | 60% WDL + 40% aligned conditional WDL | exploratory dose |

Alpha `0.30` is fixed before execution from the M15-C observations at alpha
0, 0.5 and 1.0. Alphas `0.20` and `0.40` describe the local dose curve; neither
can rescue the primary decision.

## Conditional estimator and causal control

M15-C2 preserves the leakage-resistant M15-C mechanism. Complete games are
assigned to five deterministic folds. Each row's conditional WDL prediction
comes from a tanh-linear fit that saw only the other four folds' terminal WDL
labels. It uses no oracle target, exact-value coefficient, manual coefficient,
development label or frozen-test row.

Within each held-out fold, the conditional predictions are put in deterministic
hash order and rotated by one row. This keeps the exact prediction multiset and
smoothing dose while breaking state alignment. Therefore
`CONTEXT_30 - SHUFFLED_CONTEXT_30` isolates the information carried by the
correct state-context association rather than generic shrinkage or a changed
target marginal.

## Two independent verdicts

The primary static endpoint is paired development `zero_regret_rate`. There is
no post-hoc practical-effect floor:

1. mechanism `PASS` requires the 95% lower bound of
   `CONTEXT_30 - SHUFFLED_CONTEXT_30` to be strictly above zero;
2. operational `PASS` requires the 95% lower bound of
   `CONTEXT_30 - OUTCOME` to be strictly above zero;
3. the static cell passes only if both conditions pass.

An interval whose upper bound is non-positive fails its axis. An interval that
crosses zero is inconclusive and requires a newly power-sized replication. A
small but precisely positive effect is recorded as positive; practical value
is reported from its magnitude instead of being silently reclassified as no
signal.

Playing strength is deliberately separate. Only `OUTCOME`,
`SHUFFLED_CONTEXT_30` and `CONTEXT_30` receive 512-pair, common-start
development arenas. Strength passes only if both paired arena contrasts have
95% lower bounds above zero. An inconclusive or negative arena cannot overwrite
a valid static-learning result, and a positive arena cannot rescue a failed
static primary.

## Power, evidence pins and boundaries

The cell uses 20 fresh seeds (`273001` through `273020`). Under a conservative
paired standard deviation of `0.0025`, a true `+0.002` contrast has simulated
power `0.92325` for a Student 95% lower bound above zero (`100,000` draws, seed
`44120260813`). This `+0.002` is a sizing reference, not a decision threshold.

The configuration pins the M15-C protocol hash
`74dc555948e0191c09814098918c35e2e23935cf6ff44801c6c09165ad97502d` and
result hash `b63008f3e685c5cf20ae18af4e389fa8f7308ae31aa6525e549244f6f80e499d`.
It fails closed if the observations used to select the interior dose change.

- train and development are the only readable cohorts;
- the historical `frozen_test` read count remains one, with zero new reads;
- all training targets and replay generation are oracle-blind;
- no model is promotable and there is no automatic selection;
- no production Jass change or direct 10×10 transfer is authorized;
- this PR prepares the runner and CPX route but creates no queue job.
