# L3-PURE — reverse seeds scale4M causal A/B

Date: 2026-07-31
Status: preregistered implementation; launch only after the BLEND50 decision
chain has no incompatible HOME/CPX job in flight
Promotion: false
Automatic next job: null

## Question

Does the positive reverse-seed effect observed at 2M records per arm replicate
when the fitted corpus is doubled to 4M records per arm?

The primary contrast remains:

```text
FAILED_CONVERSION_ROOTS minus MATCHED_RANDOM_ROOTS
```

The 4M stage is a fresh causal A/B. It does not compare holdout losses across
volumes and does not claim that a 4M treatment model is stronger than the 2M
treatment model without an independent force readout.

## Required positive reference

Before generation, the runner authenticates:

- `cpx62-1086-l3-pure-reverse-seed-causal-ab-v1`, including both converged
  2M models and the frozen TURNOVER parent;
- `home-1091-l3-pure-reverse-seed-independent-readout-v2`;
- verdict `L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95`;
- the exact control and treatment model SHA256 values;
- a summed IC95 lower bound above `0.5`.

No partial or failed result is admissible.

## Fixed design

| Parameter | Control | Treatment |
|---|---:|---:|
| Parent | TURNOVER | TURNOVER |
| Seed catalogue | matched random | failed conversion |
| Records | 4,000,000 fresh | 4,000,000 fresh |
| Historical replay | 0 | 0 |
| Seed fraction | 100% | 100% |
| Play / label depth | d8 / d4 WDL | d8 / d4 WDL |
| Exploration | Q00 UNIFORM | Q00 UNIFORM |
| Shards | 6 | 6 |
| Generation base seed | 74453917 | 74453917 |
| Split seed / holdout mod | 577215 / 10 | 577215 / 10 |
| Fit | identical, converged | identical, converged |

The arms are generated sequentially, with at most six producers. The matched
catalogues, parent, Q00 parameters, depths, seeds by shard, split and optimizer
are identical. The only within-stage factor is the root-selection policy.

The generation seed is disjoint from the 2M experiment and its operational
probe. Reusing the authenticated root catalogues is intentional: the tested
factor stays fixed while fresh trajectories are produced from those roots.

## Runtime sizing

The measured CPX62 reference is `cpx62-1086`: 2M records per arm, six
sequential producers per arm, complete build/generation/fits in 79m54s on
`nproc=16`. Doubling both corpora gives a preregistered estimate of
160–210 minutes including larger feature dumps and fits. Per-arm generation
timeouts are 6h, fit timeout is 4h, and the outer timeout is 10h. The job
requires at least 35,000 MiB free.

## Required outputs

- exactly 4M records per arm;
- producer exit codes and paired-generation certificate;
- WDL canary for both corpora;
- identical split contract with positive train and holdout counts;
- coverage, density and Gini diagnostics;
- converged optimizer reports;
- exact SHA256 for both models;
- authenticated positive 2M provenance;
- verdict `L3_PURE_REVERSE_SEED_SCALE4M_CAUSAL_AB_ARMS_READY`;
- `scientific_result=false`, `promotion_authorized=false`,
  `automatic_next_job=null`.

## Independent readout

After valid arms only, compare the 4M treatment directly with the 4M control
on 1,500 new paired openings disjoint from all earlier signal readouts:

- 3,000 Q00 d9 games;
- 3,000 native 0.1 s/move games;
- raw W/D/L, Elo, IC90 and IC95 per view and summed;
- training coverage diagnostics;
- no use of holdout loss for selection.

A positive 4M result establishes replication at the larger corpus size. It
does not by itself authorize a bake. Promotion requires a separate comparison
to the current champion plus Gen2 and P3/P4 conversion guards.
