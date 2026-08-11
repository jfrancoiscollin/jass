# M16-P — temporal value targets on PatternEval

Status: **POSITIVE — temporal signal confirmed; major-recovery gate not met.**

M16-P completed as
`home-1321-mini-jass-pattern-m16p-retry-v1`, attempt
`20260810T225346Z-9c7722b4`. The immutable preregistered report and its result
hash are preserved. Its old `FAIL` field answers only the narrower question
"did lambda 0.50 recover at least half of the oracle gap?"; it is not the
retained experience status.

## Question

M15-P showed that a same-state root-search blend carries a small positive
signal but precisely excludes the frozen practical recovery target. Its
`BLEND_50 - OUTCOME` development zero-regret gain was `+0.0013216` (95% CI
`[+0.0008605, +0.0017827]`) while the exact-label gap remained `+0.0122908`.

M16-P asks a distinct question: does information from later in the same
trajectory recover at least half of that PatternEval oracle gap? It preserves
the scalar folded evaluator and the selected `G1_WIDE_OUTCOME` replay source.
It is not the historical M16 L2/MLP experiment.

## Frozen arms

For each of 20 fresh paired seeds (`274001` through `274020`), a shared initial
PatternEval generates one 1,024-game replay. Five arms receive the same retained
train rows, policy/actions, initialization, batch schedule and update count:

| arm | value target | role |
|---|---|---|
| `OUTCOME` | terminal self-play WDL | honest baseline |
| `NEXT_SEARCH` | negated successor root score | exploratory TD(0)-like target |
| `LAMBDA_50` | 50/50 successor-score/later-return recurrence | sole primary |
| `LAMBDA_80` | outcome-heavy temporal recurrence | exploratory control |
| `EXACT_ORACLE` | exact train value | diagnostic upper bound |

For a current row `t`, successor root score `v[t+1]`, later return `G[t+1]`
and fixed lambda, the temporal recurrence is:

```text
G[t] = -((1 - lambda) * v[t+1] + lambda * G[t+1])
```

The last sampled row of each complete game falls back to its honest terminal
WDL. Root scores are clipped to `[-1, 1]`. Returns are built over complete,
contiguous generated trajectories before retaining the immutable train-cohort
rows. No exact value enters any deployable target.

## Preregistered major-recovery gate

The sole confirmatory contrast is `LAMBDA_50 - OUTCOME` on development
zero-regret. A pass requires:

1. the paired Student 95% lower bound to be strictly above zero;
2. the mean to reach the larger of 50% of the within-run exact-label gap and
   the M15-P-frozen absolute target `+0.0061453898`;
3. the exact-label gap itself to replicate with a positive 95% lower bound.

`NEXT_SEARCH` and `LAMBDA_80` are descriptive and cannot rescue the primary.
All 128-pair common-start arenas are descriptive; a static pass authorizes only
a fresh-seed strength replication, never promotion.

## Result and retained interpretation

`LAMBDA_50 - OUTCOME` produced a development zero-regret gain of
`+0.00154924`, with paired Student 95% interval
`[+0.00092823, +0.00217024]`. The signal is therefore positive and precise.
It recovered `10.25%` of the replicated exact-label gap (`+0.01510940`), below
the preregistered 50% major-recovery target (`+0.00755470`).

The descriptive paired arena also moved positively by `+0.00566406`, with 95%
interval `[+0.00372158, +0.00760654]`, 17 positive seeds, three ties and no
negative seed. General value MAE and value-sign diagnostics worsened, so this
is a narrow decision-quality signal rather than a general value-calibration
solution.

The retained scientific classification is therefore:

- experience: `POSITIVE`;
- mechanism: `CONFIRMED`;
- 50% major-recovery gate: `NOT_MET`;
- downstream decision: retain `LAMBDA_50` for controlled composition and a
  fresh-seed strength confirmation, without rerunning M16-P identically.

The machine-readable interpretation is frozen in
[`../artefacts/m16p_temporal_value_target_screen.interpretation.v1.json`](../artefacts/m16p_temporal_value_target_screen.interpretation.v1.json).

## HOME calibration

The configuration reserves seed `274000`, disjoint from the 20 scientific
seeds, for a timing-only HOME probe. It executes the exact one-seed workload
but publishes only phase times and workload counts. No response metric is
published, so the probe cannot change the frozen protocol or expose an interim
scientific result. The full job is queued only after measured HOME sizing and
an explicit post-sizing go.

## Boundaries

- train and development are the only readable cohorts;
- the historical `frozen_test` read count remains one, with zero new reads;
- every deployable target is oracle-blind;
- the exact arm is diagnostic and never promotable;
- no automatic selection, production Jass change or direct 10×10 transfer is
  authorized;
- the persistent HOME Python environment is reused; PyTorch is not reinstalled.
