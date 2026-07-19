# L3 role-aware V2 — specialist and generalist integrations

Status: **prepared only; no scientific job launched**.

## 1. Shared weighting rule

Both integrations use the same position-local classifier:

- exact specialist domain: `abs(white men - black men) == 2`;
- equal number of kings for both sides;
- role is recomputed from current material and side to move;
- side at `+2`: win/draw/loss = `1/2/4`;
- side at `-2`: win/draw/loss = `4/2/1`;
- outside the exact domain: weight `1`;
- final holdout: never resampled.

The two lineages share the calculation code but do not share runners, manifests or promotion decisions.

## 2. Specialist integration — L3-IMBALANCE2-ROLE-V2

The specialist starts every game in a predefined `n v n+2` stratum. Its dedicated runner is:

```text
jobs/templates/l3-imbalance2-runner-v2.sh
```

Prepared jobs target ccx33 and include a reduced non-promotable probe before full P1. P2–P4 require an immutable parent URI and SHA-256. The external Gen2/Scan gate remains plateau-only.

## 3. Generalist integration — L3-PURE-ROLE-V2

The original L3 starts from balanced material. Its dedicated runner is:

```text
jobs/templates/l3-pure-role-v2-runner-v1.sh
```

It reuses the frozen Q00 C1-Q1 self-play runner and changes only the post-split training corpus. A position is reweighted only after self-play naturally reaches the exact `±2 men, equal kings` domain. Earlier balanced positions and later positions outside the domain remain anchors of weight `1`.

The historical runner `l3-pure-runner-v4.sh` remains unchanged and continues to train on the unweighted fit corpus.

## 4. Paired generalist tests

Two independent A/B pairs are prepared. These are comparison jobs, not promotion jobs.

### ccx33 primary pair

- control: Q00, seed `271828`, unweighted fit corpus;
- treatment: Q00, seed `271828`, role-aware V2 corpus;
- two generations, 150,000 source records/generation, eight shards.

### cpx62 replication pair

- control: Q00, seed `161803`, unweighted fit corpus;
- treatment: Q00, seed `161803`, role-aware V2 corpus;
- two generations, 150,000 source records/generation, eight shards.

Within each box, the initial model, search settings, seeds and volume contract are identical. G1 self-play is directly matched. From G2 onward, trajectories may diverge because the treatment creates a different G1 student; this is part of the causal treatment effect. Across boxes, the second seed provides an independent replication rather than a duplicate hardware-only rerun.

## 5. Required analysis

For each pair, compare:

- non-weighted holdout log-loss;
- full W/D/L and Elo against the same reference;
- source and resampled counts for `up_win`, `up_draw`, `up_loss`, `down_win`, `down_draw`, `down_loss`;
- fraction of naturally generated positions entering the exact domain;
- conversion cost `2 × loss + draw` for the advantaged side;
- draw and win rate for the disadvantaged side;
- regression on balanced-position pools.

A treatment is not promotable merely because defensive outcomes improve. Conversion, general strength and the untouched holdout must remain non-regressed. A separate reviewed evaluation/gate is required before any promotion decision.

## 6. Execution order

1. review and merge the code PR;
2. run the ccx33 specialist probe;
3. run one generalist A/B pair only after explicit approval;
4. inspect domain density and memory before starting the second pair;
5. do not launch a later phase or external gate automatically.

The future critical-defence V3 — deep teacher, unique drawing move and move-level credit — remains outside this PR.
