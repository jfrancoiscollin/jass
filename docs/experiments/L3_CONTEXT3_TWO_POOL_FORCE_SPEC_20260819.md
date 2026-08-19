# L3 CTX3 two-pool causal force gate (2026-08-19)

## Question

Does the position-aligned CTX3 supervision make a stronger PatternEval than
the same supervision values after the preregistered causal shuffle?

This is the terminal causal comparison for the CTX3 recipe. It is not a test
against the current champion and it cannot authorize promotion.

## Immutable models

The gate reuses, without refit, the two models produced by
`cpx62-1418-l3-context3-paired-patterneval-fit-v1`:

- `ALIGNED`: terminal WDL mixed with the aligned CTX3 mapper prediction;
- `SHUFFLED`: the same prediction values shuffled within cohort, opening fold,
  terminal WDL and tempo quartile.

The fit certificate, target-consumption hashes, convergence receipts and raw
model hashes must all authenticate before a game is played. The two models
must be distinct. The same engine binary and search parameters are used for
both arms.

## Fresh opening evidence

Two deterministic pools of 3,000 unique openings are generated with seeds
`2026081907` and `2026081908`. Each pool must be disjoint from the other and
from the 15 historical evaluation pools preregistered in the job template.
Generation is repeated byte-for-byte and each pool is checked by the standard
selector and provenance validator.

Each opening is played twice with colours reversed. Each view therefore has
6,000 games per pool and 12,000 games over both pools.

## Views and statistics

The primary view is native search at 0.1 seconds. Q00 at depth 9 is reported as
a diagnostic and cannot override the primary decision. Both views use paired
opening-cluster bootstrap with 200,000 samples. No more than 2% of games may be
converted to error draws.

The primary contrast is `ALIGNED - SHUFFLED`. It passes only when all four
conditions hold:

1. both independent native pool point estimates exceed 50%;
2. the two native effects are compatible at 95%;
3. the combined paired-bootstrap native 95% interval excludes 50%;
4. the combined native probability of a rate above 50% is at least 0.975.

The readout always reports W/D/L, rates, paired intervals, error counts,
inter-pool compatibility and the separate Q00 diagnostic.

## Scope guards

The job plays 24,000 games in total. It performs no fit, self-play, frozen
cohort read or promotion, and schedules no automatic successor. A negative or
heterogeneous primary result closes this exact CTX3 recipe; a positive result
establishes the causal value of aligned CTX3 supervision but still does not
promote a model automatically.
