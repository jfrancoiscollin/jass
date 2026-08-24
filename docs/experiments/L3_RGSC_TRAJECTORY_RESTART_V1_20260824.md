# L3 RGSC Trajectory Restart v1 — preregistration

**Date:** 24 August 2026  
**Status:** preregistered experiment; no automatic promotion  
**Parent:** CURRICULUM (`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`)  
**Motivation:** test the actual restart mechanism of Regret-Guided Search Control, not the deep-teacher sibling-regret proxy closed by 1549–1552.

## 1. Scientific question

Does restarting a fixed fraction of CURRICULUM self-play from states where its own trajectory value was later contradicted by the terminal result produce a better next-generation evaluator than restarting from arbitrary historical states?

The primary causal contrast is:

```text
ARCHIVE_REGRET - ARCHIVE_RANDOM
```

`NORMAL` is a secondary control for the generic effect of restarting from historical states.

## 2. What 1549–1552 did *not* test

The closed loss-first/search-frontier branch defined regret through a deeper teacher and sibling move comparisons. RGSC instead assigns regret retrospectively from the agent's own selected values and the eventual game result, then changes the distribution of future self-play by restarting from high-regret states.

This experiment therefore uses no deep teacher and no predicted regret model in v1.

## 3. Frozen regret definition

A fresh CURRICULUM source corpus is generated with JSM2 metadata. For every emitted trajectory sample `i` in a resolved game:

```text
score_white = score_stm          if stm == white
              -score_stm         if stm == black
V_i         = tanh(score_white / 400)
z           = terminal game result, white POV, in {-1,0,+1}
```

The scale `400 = 2 * 200` is not tuned: `200` is the existing Jass deep-value scale, and `2*sigmoid(x/200)-1 = tanh(x/400)`.

For the emitted trajectory samples of a game:

```text
R(s_t) = mean_{i >= t} (V_i - z)^2
```

This is the RGSC target evaluated on Jass's emitted trajectory samples. It is explicitly a sampled-trajectory approximation; v1 does not modify the engine solely to densify instrumentation.

Games ending at the Jass ply cap or by material adjudication are excluded from archive construction. EGDB-resolved terminal outcomes are allowed because they improve the truth of `z`; no EGDB value enters `V_i` or the priority directly.

At most one restart candidate is retained per game: the sampled state with maximum `R`, earliest ply breaking an exact tie.

## 4. Archive and restart policy

Fixed constants, chosen before any candidate strength result:

- archive buffer size: **1,600 unique states** (`100 x 16 workers`, matching the RGSC reference scale);
- restart probability: **0.50**;
- priority temperature: **tau = 0.10**;
- source-to-table random seed: **2026082401**;
- precomposed seed-table size: **16,000**;
- old JNNW `score` and `wdl` bytes are zeroed in every published restart seed.

`ARCHIVE_REGRET` keeps the top 1,600 unique per-game maxima and samples restart entries proportionally to:

```text
P(s) proportional to R(s)^(1/tau)
```

`ARCHIVE_RANDOM` takes one deterministic random emitted state per eligible game and then a deterministic random set of 1,600 unique states; restart entries are uniform over that buffer.

The mixed RANDOM and REGRET seed tables contain the same byte-identical normal-start prefix and the same number of restart entries. During generation both use:

```text
--seed-frac 100
--random-open-plies 0
--split-selfplay-rngs
```

with the same generator seed. The opening RNG therefore draws the same seed-table indices in paired games; a normal-table index maps to the same position in RANDOM and REGRET, while a restart index is the intervention.

The EMA update from iterative RGSC is **not** used in v1. It is a compounding mechanism and is authorized only if the one-generation causal restart mechanism first passes.

## 5. Phase S — fresh source archive

Generate **400,000 fresh JNNW rows** driven by CURRICULUM, 16 shards, with:

- play depth 10;
- label depth 10;
- random opening plies 4;
- `--sample-initial`;
- `--sample-meta-format jsm2`;
- `--split-selfplay-rngs`;
- epsilon/top-k exploration off;
- material adjudication off;
- unresolved ply-cap games dropped;
- no external teacher / no Scan.

Shards are merged with game/opening ID namespacing before archive extraction.

Archive construction is allowed to fail for insufficient unique eligible games/states. Such a failure is a support verdict, not permission to reduce the 1,600-state buffer after seeing data.

## 6. Phase G — causal self-play DOE

If archive integrity passes, generate three fresh corpora, **2,000,000 rows per arm**:

| Arm | Starts | Scientific role |
|---|---|---|
| `NORMAL` | precomposed normal starts only | no-restart control |
| `ARCHIVE_RANDOM` | 50% normal / 50% random historical restart table | generic restart control |
| `ARCHIVE_REGRET` | 50% normal / 50% regret-prioritized restart table | RGSC treatment |

All other generation parameters, code, CURRICULUM parent, search depth, target machinery, record count and RNG seeds are identical. Each arm emits JSM2 and a seed-usage audit.

## 7. Phase F — one-generation continuation fit

The sole manipulated factor remains the start-state distribution. Therefore all three arms use the same production-compatible fit recipe:

- PatternEval exact fold;
- tempo-stage;
- **CONTEXT_30 aligned alpha=0.30** target, reconstructed identically per arm;
- `--prior-mean CURRICULUM`;
- `--prior-decay 0`;
- `--l2 1e-5`;
- `--lbfgs-gtol 1e-4`;
- `--lbfgs-maxcor 20`;
- same max iterations/chunk/prune geometry;
- no arm-specific tuning.

Using CONTEXT_30 rather than reopening native-WDL target tuning preserves the current champion recipe while testing only the data-distribution intervention.

A common fresh, game-disjoint normal-distribution holdout is used for loss/calibration guards. Loss alone never selects a winner.

## 8. Strength gate

Primary comparison:

```text
ARCHIVE_REGRET vs ARCHIVE_RANDOM
```

Secondary:

```text
ARCHIVE_RANDOM vs NORMAL
ARCHIVE_REGRET vs NORMAL
all candidates vs CURRICULUM guard
```

Strength uses fresh openings unseen by source/archive/fit construction:

- paired colours;
- native 0.1 s primary;
- Q00 depth 9 diagnostic;
- paired bootstrap by opening, 200,000 resamples;
- no frozen cohort;
- no automatic promotion.

A mechanism is **supported** only when the regret arm has a positive preregistered primary effect against RANDOM without a material CURRICULUM guard regression, and the direction replicates on a second mutually disjoint fresh opening pool. A positive-but-inconclusive first pool permits exactly one unchanged replication; no parameter retuning is allowed.

Terminal mechanism verdicts:

- `RGSC_RESTART_SUPPORTED`
- `RESTART_ONLY_NOT_REGRET_SPECIFIC`
- `RGSC_RESTART_NOT_SUPPORTED`
- `RGSC_RESTART_INCONCLUSIVE`
- `RGSC_ARCHIVE_SUPPORT_NOT_ESTABLISHED`

## 9. If v1 passes

Only after `RGSC_RESTART_SUPPORTED` may v2 add the two compounding mechanisms from the paper:

1. a learned regret-ranking head to avoid waiting for terminal oracle regret;
2. EMA priority updates when replayed states are revisited.

The next memo P0 experiments remain separate: tablebase-frontier exact sibling supervision and a policy head used only for move ordering.

## 10. Safety / interpretation

This experiment does **not** claim that score calibration is correct in absolute terms. The same frozen monotone score-to-value mapping is applied to every source state before terminal-error accumulation, and only its induced restart priority is tested causally.

No result from 1549–1554 is reused to select individual restart states. No strength result is read before archive construction and all three fits are sealed.
