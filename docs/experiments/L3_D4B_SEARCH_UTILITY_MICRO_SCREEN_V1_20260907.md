# L3 D4b Search-Utility Micro Screen v1 — 2026-09-07

## Question

Can the D4 beta-cutoff ordering target produce a cheap, measurable search-quality signal before any Elo or self-play campaign?

This is a new exploratory micro-screen after D4 v1 terminated `D4_SEARCH_UTILITY_OFFLINE_INVALID_V1` because the frozen exact/phase support contract could not be satisfied. D4b does **not** reinterpret D4 v1 as a scientific failure and does not retune from D4 outcomes. It keeps the same target, 24 pre-search features, four phase blocks, 96-parameter linear model, baseline logit and one-fit recipe, while shrinking acquisition and removing the exact per-phase dataset quota that caused invalidity.

## Frozen acquisition

Reuse only the already-published 4,000 target-blind D4 root manifest from job `cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1`, attempt `20260907T182914Z-1c779cc8`. No D4 teacher events or outcome labels are reused.

Select 512 roots target-blind by SHA-256 prefix `D4B-ROOT-2026090701:` while preserving the original split: 384 train, 64 valid, 64 test. Run the unchanged WDL_CONTROL teacher at exactly 20,000 nodes/root, threads=1, book off, TT reset per root. Planned teacher cost is 10.24M Jass nodes.

The teacher target and node eligibility are unchanged from D4: observed beta-cutoff-causing move among the first up-to-four legacy non-TT siblings at internal supported nodes.

## Dataset and fit

Canonical cross-split leakage removal remains mandatory. Deterministic example selection uses prefix `D4B-EXAMPLE-2026090702:` and exact counts 8,000 train / 1,000 valid / 1,000 test. Phase counts and per-phase CE are reported, but there is no phase quota gate in this exploratory screen.

Fit exactly once: 24 features × 4 phase blocks = 96 float64 coefficients, zero initialization, L-BFGS-B, L2=1e-3, max_iter=500, maxcor=10, gtol=1e-6. No model, feature, temperature, runtime-scale or seed search.

Offline support requires VALID mean CE gain >0, TEST mean CE gain >0, TEST bootstrap-95% LCB CE gain >0, and TEST top-1 cutoff-label accuracy strictly above the legacy-rank baseline. Bootstrap: 20,000 repetitions, seed 2026090703.

## Conditional Scan Gate0

Only an offline-supported model is rendered into an isolated runtime build. The production source remains CONTROL.

Runtime scope is internal nodes only: ply>=1, 9..40 pieces, remaining depth>=3, legal moves 2..16. TT priority is absolute. Among the first up-to-four legacy non-TT siblings, D4b computes the same frozen 24 features and score `-(legacy_rank-1) + beta_phase·features`, then stable-hoists only the best candidate to the first non-TT slot. Every other sibling retains its relative order. Root ordering is unchanged, preserving iterative-deepening previous-best/PV behavior.

The Scan Gate0 reuses the exact 512 target-blind parents and CONTROL results from completed job `cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1` plus the existing Scan200k sibling oracle. New Scan searches = 0. Candidate cost = at most another 10.24M Jass nodes.

Gate0 support requires positive paired mean Scan-regret improvement, positive bootstrap-95% LCB, Scan top-hit not worse than CONTROL, median candidate/control wall ratio <=1.05, and nonzero runtime eligibility.

## Interpretation

`D4B_MICRO_GATE0_SUPPORTED` means **survivor only**. It authorizes a fresh confirmation cohort, not strength games. Every terminal outcome has strength_games=0, selfplay_games=0, promotion=false and bake=false.
