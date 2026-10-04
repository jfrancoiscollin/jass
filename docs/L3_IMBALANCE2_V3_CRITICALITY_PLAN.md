# L3-IMBALANCE2 V3 — difficulty-aware conversion/resilience weighting

Status: **experimental A/B refit design**. This proposal does not alter the
merged L3-IMBALANCE2 V1 runner and must not replace the active lineage before
its current results are interpreted.

## Question

The V1 corpus is resampled from the initial material-up side's terminal result:

- win: `1`;
- draw: `2`;
- loss: `4`.

That makes failed conversions and successful resistance more visible, but it
still gives the same multiplier to every sampled position in the game. It does
not distinguish a forced move, a position with ten equivalent choices, and a
position where only one move preserves the result.

V3 tests the narrower hypothesis:

> On the same source corpus, does adding a bounded multiplier for positions
> with few result-preserving legal choices improve both +2 conversion and -2
> resilience without regressing the balanced/general holdout?

## First experiment: refit, not new self-play

The first V3 experiment is an A/B refit from one immutable completed V1 source
corpus and one immutable parent model.

- **Control**: current deterministic `1/2/4` resampling.
- **Treatment**: the same base `1/2/4` weight multiplied by searched move
  criticality.
- Both arms use the same split, untouched holdout, features, warm start,
  geometry, optimizer and training seed.
- No new self-play is generated in this PR.

This isolates the weighting change. A full V3 self-play lineage is justified
only if the refit treatment passes the gates below.

## Profiling domain

A record is eligible for move criticality profiling only when its current board
has:

- exactly two men of difference;
- equal king counts;
- more than six total pieces.

Positions at six pieces or fewer remain locked to the exact-TB teaching path and
receive no criticality multiplier. Positions outside the exact current +2
material domain keep the V1 outcome weight only.

Profiling every training record would be unnecessarily expensive. The tool
therefore selects a deterministic, bounded subset without replacement. The
selection is stratified by the existing V1 importance weights, so material-up
losses and draws are more likely to be profiled than routine wins. Default:
`25,000` parents.

## How criticality is measured

For each selected parent position:

1. enumerate every legal successor with `jass --dump-children`;
2. search every child with the frozen parent evaluation;
3. negate the child STM score to recover parent POV;
4. rank all legal choices;
5. count how many choices remain within `50` score units of the best.

A move is not credited from the final result alone. The profiler measures the
shape of the local decision:

| Bucket | Default condition | Multiplier |
|---|---|---:|
| forced/terminal | at most one legal move | `1.0` |
| unique | one preserving move and best-second gap >= `75` | `3.0` |
| narrow | preserving fraction <= `0.25`, gap >= `30` | `2.0` |
| contested | preserving fraction <= `0.50` | `1.5` |
| broad | otherwise | `1.0` |

The effective row weight is:

```text
min(8, outcome_weight_1_2_4 * criticality_multiplier)
```

The cap prevents a few rare positions from dominating the fit. A forced move
receives no bonus because it contains no choice to learn.

## Conversion and resilience interpretation

The same local metric covers both roles:

- when the material-up side is to move, a narrow position is a conversion
  decision;
- when the material-down side is to move, it is a resilience decision.

The report records buckets separately for `conversion` and `resilience`. The
terminal result still controls the base importance:

- material-up win / material-down loss: `1`;
- draw: `2`;
- material-up loss / material-down win: `4`.

Thus a unique defensive resource in a drawn or won game receives more weight
than an ordinary defensive position, while a forced defensive move receives no
extra credit.

## Reproducibility and invariants

The implementation must prove:

- source corpus URI and SHA-256 are immutable;
- source metadata URI and SHA-256 are immutable;
- parent model URI and SHA-256 are immutable;
- the split and both resamplers are deterministic;
- output training count is unchanged in both arms;
- holdout records are byte-identical before and after resampling;
- child ordering is stable from parent enumeration through sharded search merge;
- the frozen parent model, not the student under training, scores criticality;
- no Scan or Gen2 label enters training.

## Promotion gates for the refit

The treatment is not accepted merely because its weighted training loss is
lower. It must satisfy all of the following on independent, unweighted data:

1. **Technical**: all manifests align, no missing child scores, holdout hashes
   match, deterministic rerun reproduces the resampling report.
2. **Specialist holdout**: treatment log-loss is not worse than control and the
   paired bootstrap interval excludes a material regression.
3. **Role slices**: no regression on either conversion-to-move or
   resilience-to-move slices.
4. **Full games**: treatment is non-regressed against control on the two-pawn
   benchmark pools using the existing `2L + D` cost from the material-up POV.
5. **Boundary audit**: no score discontinuity or game regression when the
   trajectory leaves exact +2 for +1, +3 or a king imbalance.
6. **General anchor**: no meaningful regression on the frozen general/balanced
   reference suite.

A positive refit result authorizes a separate PR integrating the treatment into
new self-play generations. A negative or ambiguous result stops V3; it does not
change the active V1 lineage.

## Deliberate limitations

This V3 is position-criticality weighting, not policy imitation. It does not
store or directly train the identity of the best move. It makes decisive local
positions more frequent in an evaluation fit. If V3 helps, a later version may
add an explicit pairwise/policy objective for the preferred child versus its
siblings.

The score margins (`50/75/30`) and multipliers (`3/2/1.5`) are hypotheses, not
facts. They are frozen for the first A/B test and may only be changed in a new
pre-registered experiment.
