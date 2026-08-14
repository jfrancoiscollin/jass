# Jass MegaCorpus — comparative fits A/B/C

Date: 2026-08-14

## Question

At fixed PatternEval architecture, parent, conditional-target recipe and
optimizer settings, does the authenticated post-fix UNIFORM corpus carry more
useful fit signal than the immutable TURNOVER 2M reference, and does doubling
the authenticated sample from roughly 2M to roughly 4M records help?

This stage produces fit checkpoints. It does not read a frozen cohort, play a
strength match, select a winner or authorize promotion.

## Arms

| Arm | Corpus | Sampling | Purpose |
| --- | --- | --- | --- |
| A `CURRENT_2M` | immutable TURNOVER 2M | all records | retained project reference |
| B `MEGA_EQ_2M` | authenticated HOME1044 UNIFORM 40M | whole games, hash mod 20 = 0 | corpus contrast at approximately equal volume |
| C `MEGA_FULL_4M` | same authenticated source | whole games, hash mod 10 = 0 | volume contrast |

The hash function and seed are identical for B and C, so B is proven to be a
strict record-level subset of C. Every corpus is independently split by
opening, then independently receives leakage-resistant aligned CONTEXT_30
targets. The model architecture is 8cf exact-fold with the production 120
extras. Every fit starts from and is regularized toward the same immutable
L2LOW parent.

## Fixed fit recipe

- target: aligned CONTEXT_30, alpha 0.30;
- loss: logistic;
- geometry: 8cf exact-fold, tempo-stage, 120 extras;
- continuation: `--prior-mean L2LOW --prior-decay 0`;
- L2: 1e-5;
- L-BFGS maxcor: 20;
- gtol: 1e-4;
- maximum iterations: 2000 (cap only; `gtol=1e-4` remains the stopping rule);
- chunk: 20,000 rows.

The three fits run sequentially inside one CPX job. This avoids cross-arm CPU
and memory contention while sharing immutable downloads and a single compiled
binary. The optimizer settings, not wall-clock time, define the fit budget.

The first execution attempt `cpx62-1336` reached the former 300-iteration cap
on A with `gradient_inf_norm=1.282e-3`, above `gtol=1e-4`. It produced no model
and never started B or C. The cap was therefore raised before any cross-arm or
strength result existed. This is a convergence repair, not a post-hoc change to
the objective or a selection based on model quality.

## Interpretation guard

The per-arm holdouts are opening-disjoint but come from different corpus
distributions and have independently fitted CONTEXT_30 mappings. Their raw
losses are diagnostics and must not be used to crown a winner. A later job must
evaluate all checkpoints on the same independent cohort and then run a paired
strength gate with identical openings, seeds and search budgets.

TURNOVER is a legacy pre-fix corpus, while the Mega arms are post-fix. A vs B
therefore measures the complete corpus-generation change, not diversity alone.
B vs C is the clean nested volume contrast.

## About pretrain then fine-tune (arm D)

PatternEval training is a convex linear fit. A fully converged, ordinary
fine-tune on A from checkpoint C should return to the A optimum and cannot test
durable representation learning. Arm D must therefore be separately
pre-registered as either a bounded-update warm start or a non-zero prior around
C. It is not auto-queued by the A/B/C fit job.
