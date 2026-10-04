# M21 — What compounds across generations?

> **Numbering.** This cell was drafted as M19 and revised as M20; both numbers
> were taken while it was in review — M19 by the search-ratchet cell
> (`cpx62-1209`, FAIL) and M20 by the label-quality-versus-strength cell
> (`cpx62-1210`). Their verdicts are already published under those numbers, so
> this one is **M21** and its optimizer-path follow-up is **M22**.

## Motivation

M17 established that the frozen M8 L1 recipe can improve between rung 1 and
rung 8, but the loop advanced the deployed parent only about once in eight
nominal generations.

**Both channels of the Scan story are now closed on L1, and this is no longer an
assumption:**

| channel | cell | result |
|---|---|---|
| the generator improving | M18 (`cpx62-1206`) | `+0,0000`, CI95 `±0,027` — a **tight zero** |
| search acting as a ratchet | M19 (`cpx62-1209`) | `−0,0219`, CI95 `[−0,064 ; +0,021]`, sign **against** depth |

M19 matters twice over: it not only closed the second channel, it showed that
M18's version of the question had been asked wrongly. M18's probe inherited each
arm's own search depth, so the shallow arm started 5,3 points lower **before any
training**, and a contrast defined on gains rewarded whichever arm started
lowest. With a common-depth probe the control is exact (rung-0 gap `0,0`) and the
answer is a clean no.

Therefore M21 does not ask again whether the generator or the search is the
mediator. It asks **what information accumulates across generations** and makes
later training useful.

## Hypothesis

The candidate mechanism is **learning-signal composition**: later generations
expose a different mixture of states, search disagreements and policy
uncertainty, and those samples contribute gradients complementary to what has
already been seen. A loop can improve even when its terminal WDL labels do not
become monotonically closer to minimax truth.

The oracle remains observer-only. No M21 training target, self-play action,
sample-selection rule or promotion decision may read oracle value, DTW or
optimal actions.

## Two endpoints, and WDL exactness is not the causal one

⛔ **Playing strength is a co-primary endpoint, not a secondary courtesy.**

M18 and M19 leave the same picture across four arms: `forced_advance` labels
`0,8250` / arena `0,45`; `shallow_depth1` `0,8125` / `0,55`; the reference
`0,7906` / `0,70`; `frozen_generator` `0,7906` / **`0,90`**. Label exactness and
strength appear to move in **opposite** directions. M20 (`cpx62-1210`) is testing
exactly that as a paired single-factor contrast.

The consequence for this cell is direct: **a design that selects on WDL
exactness alone could select the weaker model.** So every contrast below is
reported on both endpoints:

1. **learning score** — the frozen L1 gate's combined value/policy score, with
   value-sign and optimal-policy-mass deltas reported separately;
2. **playing strength** — a **paired arena contrast against the common initial
   model**, same seed, same start schedule, with a paired 95 % CI.

⚠️ **Preregistered now, before any number is seen: what if the two disagree?**
If an arm improves the learning score while losing arena against the initial
model, the cell reports `PASS_LEARNING_BUT_WEAKER_MODEL` and **the mechanism is
not endorsed**. Deciding this after the fact would let us pick whichever endpoint
flatters the hypothesis — and if M20 confirms the anti-correlation, disagreement
is the *expected* case, not an edge case.

## Frozen base

- Level: L1, where M8 established learnability.
- Base recipe: M17/M8 search-improved self-play, unchanged.
- Eight nominal generations.
- **20 fresh paired seeds — a hard floor, not "if compute permits".**
- Fixed evaluation/probe cohorts, never used to choose samples.
- Common-depth probe (M19's fix) so label levels are comparable across arms.

### Why 20 seeds is not a budget question any more

`cpx62-1209` measured the setup/science split for the first time:

```
build_and_ctest    9 s      science (10 runs of 8 generations)   72 s
venv_and_pip      18 s      TOTAL                               106 s
pytest + oracle    6 s
```

**106 seconds of science for 32 minutes of wall clock.** Cross-checked over
three milestones — M17 (5 runs) 33 min, M18 (20 runs) 37 min, M19 (10 runs) 106 s
warm — the setup is 26-34 min and the science is ≈ 7 s per run of eight
generations.

M17, M18 and M19 each returned at least one undecidable criterion for lack of
power — M18 with a mean **above** its practical threshold. At six arms × 20
seeds this cell is ≈ 14 minutes of science. There is no budget argument left.

Use the shared scratch (`$result_root/mini-jass-shared-work`) so the run starts
warm; a per-milestone directory repays 26-30 minutes of cold setup for two
minutes of work.

## Primary cell: contribution of generation identity

For every seed, first generate one complete 8-generation trajectory pack and
retain each generation's replay samples separately. The scientific arms then
train from controlled subsets of that **same generated pack**, so generation
identity is the factor while positions/actions/labels generated upstream are
fixed.

### Arms

1. `G1_ONLY` — train on generation-1 samples only. Match optimizer updates and
   total sample draws to the other arms by resampling G1 with replacement.
2. `G8_ONLY` — generation-8 samples only, same sample/optimizer budget.
3. `G1_TO_G8_MIX` — equalized mixture from all eight generations, same budget.
4. `G1_PLUS_NOVEL_LATE` — start from the G1 pool, then replace half of the draws
   with late-generation samples novel relative to G1 under the preregistered
   signature. Tests whether novelty rather than recency carries the gain.
5. `G1_PLUS_MATCHED_LATE` — as arm 4, but late samples are distribution-matched
   to G1 on preregistered coarse strata (material, side-to-move, legal-move
   count, oracle-blind search-margin bin). Separates new coverage from
   reweighting familiar strata.
6. **`G1_WIDE` — generation 1 only, generated with 8× the games (1024 instead of
   128). Same generator, one generation, same number of UNIQUE samples as
   `MIX`.**

No arm may use oracle exactness to select, reject or weight a sample.

### ⛔ Why arm 6 decides whether this cell can conclude anything

`G1_ONLY` reaches its budget by resampling **with replacement**: it sees roughly
eight repetitions of a small set, while `MIX` sees eight times more **unique**
samples. Any set repeated 8× overfits relative to a same-size draw from a larger
pool — with no generation information involved. So `MIX − G1_ONLY` measures two
things at once, and the second alone can produce a positive.

**`G8_ONLY ≈ G1_ONLY` does not rescue this.** `G8_ONLY` resamples one
generation's worth of unique samples too, so it carries the *same* low diversity
as `G1_ONLY`. The pattern "`MIX > G1_ONLY` while `G8_ONLY ≈ G1_ONLY`" is
therefore **equally explained by** "more unique positions help, regardless of
which generation produced them" — which is precisely the claim it would be
invoked to refute.

With arm 6 the design separates them:

| contrast | isolates |
|---|---|
| `MIX − G1_WIDE` | **generation identity, alone** ← the real primary |
| `G1_WIDE − G1_ONLY` | unique-sample volume, alone (the artefact, quantified) |
| `MIX − G1_ONLY` | the sum of both — kept, but secondary |

Cost: `G1_WIDE` generates 1024 games in one generation, which is what a normal
8-generation run already generates in total — about **one extra run-equivalent
per seed, ≈ 2,4 minutes of science for the whole arm.**

## Observer diagnostics by generation

Before any outcome is inspected, compute oracle-blind descriptors per
generation: unique-state coverage and overlap/Jaccard with G1; state visitation
entropy; material/phase distribution; legal-action-count distribution; search
root-score margin and entropy; policy-target entropy; selected-action rank under
search scores; network/search disagreement where available; replay age and
duplicate rate; W/D/L class balance.

After protocol and candidates are frozen, the oracle may additionally report WDL
exactness and MAE, optimal-policy mass of targets, value-sign accuracy by
generation/stratum, and which strata contain the learning gain. Diagnostics
only; they cannot alter the primary inference.

## Primary contrasts

Preregistered paired contrasts on development and a sealed confirmation cohort,
**each reported on both endpoints (learning score and paired arena)**:

- `MIX − G1_WIDE` — **primary.** Does generation identity add anything once
  unique-sample volume is held equal?
- `G1_WIDE − G1_ONLY` — how much of any `MIX − G1_ONLY` effect is just volume?
- `MIX − G1_ONLY` — the historical framing, now secondary.
- `G8_ONLY − G1_ONLY` — is recency alone sufficient?
- `NOVEL_LATE − G1_ONLY` — does genuinely new late coverage pay?
- `NOVEL_LATE − MATCHED_LATE` — novelty, or coarse reweighting?

## Interpretation table

- `MIX > G1_WIDE`, `G8 ≈ G1_ONLY`, arena agrees: **the strong result.** Neither a
  better generator, nor depth, nor WDL precision — complementary information
  accumulating across generations is what makes the loop work.
- `MIX > G1_ONLY` but `MIX ≈ G1_WIDE`: the effect is **unique-sample volume**,
  not generation identity. Useful, and a completely different lever.
- `G8 > G1_ONLY` and `MIX ≈ G8`: later generator/search quality suffices;
  accumulation is not required. *(Note this would sit awkwardly beside M18's
  tight zero on generator feedback and would need reconciling, not celebrating.)*
- `MIX > G1_WIDE` on learning score but **arena down**: `PASS_LEARNING_BUT_WEAKER_MODEL`
  — mechanism not endorsed, and it corroborates M20's anti-correlation.
- `MIX > G1` but `NOVEL_LATE ≈ MATCHED_LATE`: benefit is distribution
  reweighting rather than new coverage.
- All arms flat: M17's apparent composition likely came from sequential
  optimization/promotion dynamics rather than information added by later
  corpora. Next cell isolates the optimizer path.

⚠️ **`NOVEL_LATE` is a bet on coverage, and L3 refuted that bet.** At 10×10,
`--random-open-plies` bought `+2,83 %` of buckets and **lost `−9,27 Elo`**, CI95
`[−17,9 ; −0,7]`, upper bound below zero (`cpx62-1131`→`1134`); hard-replay v1
lost `−648 Elo` for more coverage still. The rule on the production side is: never
optimise coverage as a proxy. This cell is still worth running — its novelty is
produced **on-policy by the loop itself**, not by random openings, and that is a
distinction L3 could never test — but a `NOVEL_LATE > G1` result **contradicts**
the L3 verdict and requires fresh-seed replication before it is read as anything.
It is not a confirmation.

## Required follow-up if all corpus-composition arms are flat

**M22** holds the complete corpus fixed and compares one long fit against eight
sequential fit/replay cycles with identical total optimizer steps.

⚠️ Note that as written this confounds **optimization path** with **promotion**:
the eight sequential cycles promote, the long fit does not, and M18 showed the
promotion gate is not neutral (`forced_advance` promotes 8/8 and yields the most
exact labels with the *weakest* model). M22 must either add a third
"eight cycles, no gate" arm or state plainly that it measures the pair
`(path, promotion)` and not the path alone.

## Gates

Before execution, freeze: the fresh seed family (20, hard) and power target;
exact sample-count and optimizer-step equalization; the novelty signature and
coarse matching strata; the primary effect size and paired 95 % CI requirement
on **both** endpoints; the sealed confirmation policy.

A scientific PASS requires `MIX − G1_WIDE` to be positive with its preregistered
practical effect and paired 95 % CI entirely above zero on confirmation, **and
the paired arena contrast not to be negative**. Mechanism attribution requires
the corresponding secondary contrasts to pass; otherwise the result is
`PASS_COMPOSITION_MECHANISM_UNRESOLVED`.

## Boundaries

- `promotable: false`
- `production_jass_changes_authorized: false`
- `direct_10x10_transfer_authorized: false`
- Oracle is observer-only.
- M21 may authorize only a fresh-seed replication or the M22 optimizer-path cell.

## Engineering requirements

The implementation PR must include:

- deterministic generation-indexed replay export;
- immutable sample IDs so the same generated pack feeds every arm;
- fail-closed sample/optimizer budget equality checks;
- fail-closed oracle-read audit for generation, selection, training and
  promotion — per row, as in M18/M19, where a single causal read fails the cell;
- a compact scientific summary that **aborts the job** above the runner's 64 KiB
  inline limit rather than hoping to stay under it. `cpx62-1206` exceeded it,
  the runner skipped the file **silently**, and a green job published an
  invisible verdict. See `compact_result()` and the `exit 6` guard;
- phase timings merged into that summary **after** `result_hash` is computed —
  wall-clock is not part of the protocol and must not perturb the identity of a
  scientific result;
- a probe-pairing guard that compares **per seed, across arms** — never a single
  signature across all rows. `probe_seed = seed_base + seed`, so every seed draws
  its own start schedule by construction; the naive version killed `cpx62-1208`
  at the final assertion after 28 minutes of science, on a valid run. See
  `assert_paired_probe_schedules`;
- a determinism control where two arms share a specification, as M20 does with
  `gate_arena` and `depth32`: identical specs must produce identical results, or
  the measured gap contains execution noise;
- tests exercising the full write → publishable-summary **transport** contract,
  with fixtures that reproduce the **variation** of reality and not merely its
  shape. A fixture smoother than reality validates guards that reality violates —
  that is exactly how the `cpx62-1208` bug survived review.
