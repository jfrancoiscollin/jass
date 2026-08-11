# L3 — transfer of Mini-Jass conditional targets to full Jass

Status: external-target support, conditional target builder and HOME timing
probe implemented. No job is queued by this PR. No new full-size self-play is
generated in the first stage.

## Question and cheapest causal ordering

Mini-Jass establishes that target construction can make information already
present in the position easier for scalar PatternEval to learn. The first 10×10
question is therefore not whether more self-play helps. It is whether the
retained `CONTEXT_30` recipe helps on the same immutable corpus and production
architecture.

The order is intentionally cheap:

1. Reuse TURNOVER's immutable 2,000,000-position Jass/Jass corpus.
2. Fit aligned and shuffled conditional targets on exactly those rows.
3. Measure convergence time, then refit two candidates from the same L2LOW
   parent under the current champion recipe.
4. Play an independent same-pool causal gate.
5. Generate new full-size on-policy self-play only if the offline aligned arm
   beats both the marginal-matched shuffle and L2LOW.

This prevents an expensive generation from confounding target quality with a
new position distribution.

## Frozen inputs and fit recipe

Corpus:

```text
r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/
  20260726T071254Z-336bb984/artefacts/turnover1to1.{jnnw,jsm}.gz
```

Parent:

```text
L2LOW sha256 ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4
r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/
  20260803T060626Z-209eb56b/artefacts/control.pjtw.gz
```

Both arms use the champion fit recipe:

```text
--exact-fold --prior-mean L2LOW --prior-decay 0
--l2 1e-5 --lbfgs-gtol 1e-4 --tempo-stage
```

The build must expose exactly 120 extras with endgame, king-mobility, Scan
parity and tempo-stage flags. The opening-level split is reproduced with seed
`577215`; its expected tail is 199,204 rows.

## Conditional target construction

The mapper consumes only the production FEAT dump. Eleven black-minus-white
components are derived from the paired 120-extra layout: men, king count,
mobility, balance, king centrality, king proximity, safe king mobility, denied
king mobility, men skew, has-king and extra-king. Positive RMS scaling is fitted
on train rows only; no mean centring breaks odd colour symmetry.

Complete JSM games are assigned to five deterministic folds. Every train row
receives a prediction from a mapper that never saw any row from its game.
Holdout predictions come from a mapper fitted only on the train prefix. A hard
guard rejects any game crossing the train/holdout boundary.

The two black-POV probability sidecars are:

```text
ALIGNED  = (0.70 * terminal_WDL + 0.30 * conditional_prediction + 1) / 2
SHUFFLED = (0.70 * terminal_WDL + 0.30 * within_fold_permutation + 1) / 2
```

The permutation stays within cohort and fold, has no fixed row and preserves
every prediction multiset exactly. Thus the arms have the same target marginal;
only state alignment changes. No oracle, EGDB label or search score enters the
target.

`train_stream --target external` loads a strict aligned float32 `.npy` vector in
`[0,1]`, validates but never clips or normalises it, and emits an atomic
provenance report. Without that explicit mode, the historical WDL/value path is
unchanged.

## Stage 0 — HOME timing probe

The probe performs the real source fetch, split, 120-feature dump, complete
target build and two concurrent 25-iteration L-BFGS fits. It reports target
builder seconds and seconds per iteration for each arm. Non-convergence at 25
iterations is expected and cannot become a scientific verdict.

Historical HOME anchor for an ordinary 2M arm is 8.58 seconds per iteration.
This is only a provisional estimate: external soft targets may change the
iteration count, so the full ETA must be computed from this same-workload probe.
The probe requires hostname HOME, `nproc=16`, more than 10 GiB free, bounded
target/fit timeouts, progress publication, architecture guards, and a post-sizing
human GO. Its persistent NumPy/SciPy venv is bootstrapped once and then reused;
PyTorch is not involved.

## Later scientific gates

The first causal contrast is aligned versus shuffled on an independent game
pool. Its two-sided 95% interval must have a positive lower bound; there is no
minimum Elo floor. The aligned candidate must then beat current L2LOW on the
same gate before the recipe can seed new self-play.

Only a double pass authorises a distinct on-policy experiment. That later job
will generate paired full-size Jass self-play from L2LOW and the aligned model,
hold game schedule and search budget fixed, and test whether the target gain
survives feedback as in M15-C5. No automatic continuation or promotion is
authorised here.
