# M19 — What compounds across generations?

## Motivation

M17 established that the frozen M8 L1 recipe can improve between rung 1 and rung 8, but the loop advanced the deployed parent only about once in eight nominal generations. M18 then falsified the simplest causal story: freezing the self-play generator cost essentially zero WDL exactness on the fixed probe, while forced advance produced the most oracle-exact labels and the weakest final arena model.

Therefore M19 does **not** ask again whether WDL labels become more exact. It asks what information accumulates across generations and makes later training useful when label exactness itself is not the mediator.

## Hypothesis

The candidate mechanism is **learning-signal composition**: later generations expose a different mixture of states, search disagreements and policy uncertainty, and those samples contribute gradients that are complementary to the samples already seen. A loop can therefore improve even when its terminal WDL labels do not become monotonically closer to minimax truth.

The oracle remains observer-only. No M19 training target, self-play action, sample-selection rule or promotion decision may read oracle value, DTW or optimal actions.

## Frozen base

- Level: L1, where M8 established learnability.
- Base recipe: M17/M8 search-improved self-play.
- Eight nominal generations.
- Fresh paired seeds, minimum 20 if compute permits; power calculation must be committed before execution.
- Fixed evaluation/probe cohorts, never used to choose samples.

## Primary cell: contribution of generation identity

For every seed, first generate one complete 8-generation trajectory pack and retain each generation's replay samples separately. The scientific arms then train from controlled subsets of that **same generated pack**, so generation identity is the factor while positions/actions/labels generated upstream are fixed.

### Arms

1. `G1_ONLY`
   - Train on generation-1 samples only.
   - Match optimizer updates and total sample draws to the other arms by resampling G1 with replacement.

2. `G8_ONLY`
   - Train on generation-8 samples only.
   - Same sample/optimizer budget as G1_ONLY.

3. `G1_TO_G8_MIX`
   - Equalized mixture from all eight generations.
   - Same total sample/optimizer budget.

4. `G1_PLUS_NOVEL_LATE`
   - Start from the G1 pool, then replace half of the draws with late-generation samples that are novel relative to G1 under the preregistered state/signature definition.
   - Tests whether novelty, rather than recency itself, carries the gain.

5. `G1_PLUS_MATCHED_LATE`
   - Same as arm 4, but late samples are distribution-matched to G1 on preregistered coarse strata (material, side-to-move, legal-move count, oracle-blind search-margin bin).
   - Separates new coverage from merely reweighting familiar strata.

No arm may use oracle exactness to select, reject or weight a sample.

## Observer diagnostics by generation

Before any outcome is inspected, compute oracle-blind descriptors for each generation:

- unique-state coverage and overlap/Jaccard with G1;
- state visitation entropy;
- material/phase distribution;
- legal-action-count distribution;
- search root-score margin and entropy;
- policy-target entropy;
- selected-action rank under search scores;
- network/search disagreement where available;
- replay age and duplicate rate;
- W/D/L class balance.

After protocol and candidates are frozen, the oracle may additionally report:

- WDL exactness and MAE;
- optimal-policy mass of targets;
- value-sign accuracy by generation/stratum;
- which strata contain the learning gain.

These are diagnostics only and cannot alter the primary inference.

## Primary contrasts

Preregister paired contrasts on development and a sealed confirmation cohort:

- `MIX - G1_ONLY`: do multiple generations contain complementary learning signal beyond repeated exposure to G1?
- `G8_ONLY - G1_ONLY`: is recency alone sufficient?
- `NOVEL_LATE - G1_ONLY`: does genuinely new late-generation coverage pay?
- `NOVEL_LATE - MATCHED_LATE`: is the effect attributable to coverage/novelty rather than coarse distribution reweighting?

The primary endpoint is the same combined value/policy learning score used by the frozen L1 gate, with value-sign and optimal-policy-mass deltas reported separately. Arena strength versus the common initial model is secondary but mandatory.

## Interpretation table

- `MIX > G1`, `G8 ≈ G1`, `NOVEL_LATE > G1`: evidence for complementary/novel information accumulating across generations.
- `G8 > G1` and `MIX ≈ G8`: later generator/search quality is sufficient; accumulation is not required.
- `MIX > G1` but `NOVEL_LATE ≈ MATCHED_LATE`: benefit is mainly distribution/reweighting rather than new state coverage.
- all arms flat: M17's apparent composition likely came from sequential optimization/promotion dynamics rather than information added by later corpora; next cell must isolate optimizer continuation.

## Required follow-up if all corpus-composition arms are flat

M20 should hold the complete corpus fixed and compare one long fit against eight sequential fit/replay cycles with identical total optimizer steps. This directly tests whether the compounding mechanism is optimization path dependence rather than data evolution.

## Gates

Before execution, freeze:

- fresh seed family and power target;
- exact sample-count and optimizer-step equalization;
- novelty signature and coarse matching strata;
- primary combined-score effect size and paired 95% CI requirement;
- sealed confirmation policy.

A scientific PASS requires the primary contrast `MIX - G1_ONLY` to be positive with its preregistered practical effect and paired 95% CI entirely above zero on confirmation. Mechanism attribution requires the corresponding secondary contrast(s) to pass; otherwise the result is `PASS_COMPOSITION_MECHANISM_UNRESOLVED`.

## Boundaries

- `promotable: false`
- `production_jass_changes_authorized: false`
- `direct_10x10_transfer_authorized: false`
- Oracle is observer-only.
- M19 may authorize only a fresh-seed replication or the explicitly specified M20 optimizer-path cell.

## Engineering requirements

The implementation PR must include:

- deterministic generation-indexed replay export;
- immutable sample IDs so the same generated pack can feed every arm;
- fail-closed sample/optimizer budget equality checks;
- fail-closed oracle-read audit for generation, selection, training and promotion;
- compact scientific summary below the runner's 64 KiB inline limit;
- phase timings embedded inside that compact summary;
- tests that exercise the full write → publishable-summary transport contract, not only JSON parsing.
