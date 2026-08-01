# Self-play coverage levers

These controls are opt-in. Their defaults preserve the historical generator,
and each one can therefore be tested as a single causal factor.

## Phase-aware sampling

`--sample-rate-by-phase` sets a sampling denominator for each fixed piece-count
phase. Missing phases retain the historical `1/4` rate.

```text
--sample-rate-by-phase opening=8,midgame=4,late-mid=3,endgame=2,deep-eg=1
```

The final `SAMPLEPHASE` line reports the configured denominator and the selected
and emitted counts for every phase. The WDL still comes from the played game;
this option only changes which visited positions enter the training corpus.

## Score-softmax Top-K exploration

`--explore-temperature-cp T` changes the selection inside the existing
margin-filtered Top-K set from uniform to:

```text
p(move) proportional to exp((score(move) - best_score) / T)
```

It requires `--explore-topk`. `T=0` preserves the historical uniform selection
and RNG consumption. A causal test must keep parent, openings, volume, depths,
margin, split, fit and all RNG seeds fixed. The `EXPLORATION` line reports the
realised softmax dose and selected ranks.

## Parent-regret restart archive

First score an aligned self-play corpus with the exact parent:

```text
jass --rewrite-scores-with-nnue raw.jnnw parent-scored.jnnw --nnue parent.pjtw
```

Then mine positions where the parent static probability disagreed most with
the terminal result:

```text
python tools/selfplay_frontier.py mine-regret \
  --data raw.jnnw --meta raw.jsm --scored-data parent-scored.jnnw \
  --out regret-seeds.jnnw --manifest regret-seeds.json \
  --max-positions 4000 --score-scale-cp 100 --seed 1
```

The miner:

- authenticates position and WDL alignment between both corpora;
- computes terminal-WDL binary cross-entropy from the parent's static score;
- retains at most one highest-regret position per game;
- round-robins phase/WDL strata to avoid a single regime monopolising seeds;
- adds a colour mirror and zeroes score/WDL before reuse.

The output can be fed to the existing `--seed-file` / `--seed-frac` controls.
It uses no external teacher or oracle. Terminal WDL influences archive
selection only; every continuation must generate a fresh outcome.

## Stochastic master opening pool

`tools/build_master_opening_pool.py` extracts at most one early, quiet,
non-terminal position per historical game, removes duplicates, clears every
score/WDL field and emits FEN only. The generator can then select it with:

```text
--opening-pool master-openings.fen \
--opening-pool-frac 50 \
--opening-pool-post-plies 0
```

The remaining games retain the historical random-8 diversification. Pool
membership is uniform and stochastic, so this is an opening *distribution*,
not a deterministic sequence book. Master outcomes, evaluator labels and
played moves are never copied into training; the child position is continued
by current self-play and receives a fresh terminal WDL. `OPENING_SOURCE`
reports the realised pool dose.

The durable repository source currently available is not a direct FMJD
export. It is Git blob
`4ec127ffc32e2eee9e4a36f656ce4d97fac8d04e` at commit
`34761f9d03d93d5e2ee18a66bbddeef604e49d24`, path
`jobs/results/0014-fetch-master-games/artefacts/master-1600.jnnw`: 1,458,341
positions from 13,266 Lidraughts master games. The DILF PC Blues A1 material
contains only 26 complete games; its much larger combination tables are useful
knowledge but are not complete played games.

## Rolling replay policy

The prepared A/B jobs use a fixed 50/50 mix: 1M fresh records from the tested
generator plus the same deterministic 1M sample from the authenticated
post-root-fix 1017 UNIFORM corpus. Both arms therefore see identical memory;
only the registered coverage lever changes. Opening identifiers are
namespaced by temporal source before the opening-level split so no game family
can straddle train and holdout.

The ratio is a preregistered engineering prior, not a universal optimum.
`replay-ratio-ab.sh` therefore prepares the direct constant-volume comparison:
2M fresh versus a deterministic 1M sample of the same byte-identical 2M fresh
input plus 1M authenticated post-fix replay. Alternate ratios still require
separate causal A/Bs; replay
must not be changed inside another coverage-lever comparison.

## Minimum experiment protocol

Change one lever at a time against an otherwise identical control. Use fresh,
paired openings and split RNG streams. Record the parent/model hashes, WDL
canary, phase coverage, unique bucket coverage, density/Gini, convergence and
an independent Q00/native strength readout with confidence intervals.
