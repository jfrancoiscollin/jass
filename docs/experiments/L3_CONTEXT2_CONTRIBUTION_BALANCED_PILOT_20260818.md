# CTX2 contribution-balanced seed pilot — preregistration

Date: 18 August 2026  
Status: prepared, not authorized to launch

## Audited starting point

The source autopsy is `cpx62-1412-l3-context2-intervention-contribution-autopsy-v1`,
attempt `20260818T203156Z-2d6e9599`, code
`2d6e95994ca055bfd942d59c2c6c696323944c9a`. Its read-only audit is
`cpx62-1413-l3-context2-contribution-autopsy-readout-v1`, attempt
`20260818T204712Z-2d6e9599`.

The global concentration was reproduced with zero reported error. The existing
six-cell quota family is closed:

- `10,673` WDL-admissible quota mixtures were enumerated at step `0.05`;
- `199` mixtures were rejected by the distribution guards;
- `0` mixtures passed all three contribution guards;
- `quota_only_rescue_predicted = false`.

The best admissible mixture was already extreme:

| Cell | Record weight |
|---|---:|
| BASE | 30% |
| TOPK3M30 | 50% |
| ROP16 | 5% |
| EPS16 | 5% |
| DECAY120 | 5% |
| DEPTH10 | 5% |

It still produced top-1 `0.560177`, top-3 `0.769375`, effective component
count `2.895`, and a worst normalized gate ratio of `1.210397`.

`TOPK3M30` is the only existing intervention that moves all three metrics in
the desired direction against BASE: top-1 `-0.021649`, top-3 `-0.014675`,
effective count `+0.195`. `ROP16` is strongly counterproductive: top-1
`+0.056978`, top-3 `+0.031343`, effective count `-0.425`. Removing ROP16 from
the observed corpus improves top-1 by `0.016112`, top-3 by `0.009358`, and
effective count by `0.125`.

The conditional mapper is dominated by `men_delta`, which receives
`0.591086` of total absolute logit contribution. Its contribution is sourced
mainly by ROP16 (`37.1817%`) and EPS16 (`25.5803%`). The five weakest
components are:

| Component | Absolute logit share |
|---|---:|
| `king_safe_mobility_delta` | 0.006711 |
| `legal_capture_option_delta` | 0.006714 |
| `center_presence_delta` | 0.007683 |
| `king_centrality_delta` | 0.011718 |
| `blocked_man_delta` | 0.012013 |

The next experiment must therefore create states enriched in those five
directions. Changing only the proportions of BASE/ROP16/EPS16/DECAY120/
TOPK3M30/DEPTH10 is not an admissible rescue.

## Scientific question

Can fresh self-play trajectories started from states selected for weak CTX2
contributions produce a corpus whose aligned conditional mapper is less
concentrated than CURRENT, without changing the parent, label formula,
PatternEval architecture, or WDL distribution?

This is a corpus-support experiment. It is not a search-parameter sweep and it
does not test playing strength.

## Fixed sources

- Parent for all generated games: certified `CURRICULUM` champion.
- Seed discovery source: the immutable 2M-position corpus from `1409`.
- Diagnostic scorer: the six certified alpha `0.30` mappers from `1411`,
  replayed without refit.
- CTX2 implementation: the production 30-channel phase+tactical dumper.
- Split key: `opening_id`.
- Weighting: `game_equal`.

No frozen data may be read.

## Stage 1 — deterministic target seed mining

Recompute CTX2 and the fixed-mapper local contributions for every legal state
in `1409`. Canonicalize positions under board/color symmetry and remove
duplicates before ranking.

Build six mutually disjoint seed pools:

1. one pool for each of the five weak components listed above;
2. one matched neutral anchor pool.

Each target pool contains exactly `4,096` unique positions. A target position
must satisfy all of the following:

- its target component is in the top decile of normalized absolute local
  contribution within its phase/piece-count stratum;
- `men_delta` is below the median normalized contribution in that stratum;
- both signs of the target component contribute between `45%` and `55%` of
  the pool;
- no source game contributes more than two positions;
- opening IDs are disjoint across the six pools;
- all positions round-trip through the production JNNW parser.

Strata are the Cartesian product of:

- the four registered CTX2 phase bins;
- side-to-move W/D/L;
- men/kings piece-count buckets used by the activation audit.

The neutral anchor is sampled from the same stratum counts and the same
source-game cap, but without conditioning on component contribution. It is
therefore a distribution-matched control, not generic BASE data.

Fail closed if any target pool cannot reach `4,096` positions. Thresholds and
pool sizes may not be relaxed after looking at the result.

## Stage 2 — fresh targeted self-play pilot

Generate exactly `600,000` new positions, `100,000` per seed pool, with a
fresh preregistered RNG seed. Every cell uses the same generator configuration:

- parent `CURRICULUM` on both sides;
- `--seed-file <cell>.jnnw --seed-frac 100`;
- TOPK3M30 exploration, because it is the only existing knob with a favorable
  three-metric direction in 1412;
- identical play/search budgets, random-open settings, maximum plies, and
  producer count across cells;
- strict `cpx62`, `16` CPUs, `12` producers.

Only the seed pool differs between cells. ROP16, EPS16, DECAY120, and DEPTH10
must not be mixed into this pilot.

Before volume generation, run exactly `10,000` positions per cell. Abort before
the full pilot if any cell fails parsing/distribution guards or if projected
wall time exceeds `45` minutes. The preflight output is diagnostic only and is
not included in the `600,000` positions.

## Stage 3 — activation and fixed-mapper screen

The first screen performs no fit. It recomputes the 30 CTX2 channels and
replays the fixed mapper from `1411` on the new corpus.

All conditions below must pass:

1. exactly `600,000` valid positions and the six exact `100,000` quotas;
2. 30/30 raw channels and 15/15 base components materially active;
3. phase recomposition error at most `1e-5`;
4. WDL side skew at most `0.02` and relative draw-rate shift versus the
   matched neutral cell at most `0.15`;
5. in each target cell, the named weak component's absolute contribution
   share is at least `1.50x` its matched-neutral share;
6. in each target cell, the `men_delta` share is lower than in the matched
   neutral cell;
7. in the six-cell aggregate, top-1 is at most `90%` of CURRENT, top-3 at most
   `95%` of CURRENT, and effective component count at least `125%` of CURRENT.

As a causal control, shuffle target-cell identity within the fixed
phase/piece-count/WDL strata and recompute the same contrasts. The aligned
target enrichment must exceed the median of `10,000` deterministic stratified
shuffles for all five targeted components. The shuffle does not alter or
regenerate positions.

PASS requires every condition. There is no partial PASS and static activation
alone cannot rescue a failed contribution screen.

## Stage 4 — mapper-only confirmation, conditional on Stage 3

Only after Stage 3 passes, fit the same six small alpha `0.30` conditional
mappers used in 1411:

- five OOF folds by `opening_id` plus one final mapper;
- fold-local RMS normalization;
- `game_equal` weighting;
- identical convergence criteria;
- aligned and WDL/phase-stratified shuffled targets.

No PatternEval is fit. The aligned mapper must pass the same three CURRENT
concentration guards on OOF predictions and must beat its shuffled control on
the preregistered conditional attribution diagnostic.

Only that result may authorize preparation of a PatternEval A/B/C experiment:

- A: unchanged CURRICULUM;
- B: full refit on the contribution-balanced corpus with aligned CTX2;
- C: identical full refit with stratified shuffled CTX2.

Even then, B-vs-C native strength on two fresh disjoint pools remains primary;
B-vs-A is secondary and no promotion is automatic.

## Proposed job sequence — not launched

- `cpx62-1414-l3-context2-contribution-seed-miner-v1`: read-only seed mining
  and pool certification.
- `cpx62-1415-l3-context2-contribution-balanced-pilot-v1`: preflight plus
  600k-position fresh self-play.
- `cpx62-1416-l3-context2-contribution-balanced-screen-v1`: activation,
  fixed-mapper contribution, and stratified-shuffle screen.
- `cpx62-1417-l3-context2-contribution-balanced-mapper-v1`: mapper-only fit,
  conditional on 1416 PASS.

These identifiers reserve the causal order; this document does not queue any
of them.

## Forbidden actions

Until the relevant gate explicitly passes: no PatternEval fit, no force game,
no frozen read, no promotion, no reuse of an evaluation opening pool, no
threshold relaxation, and no automatic continuation to the next stage.

