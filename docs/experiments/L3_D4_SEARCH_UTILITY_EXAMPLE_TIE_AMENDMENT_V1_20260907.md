# L3 D4 search-utility — same-split example tie amendment v1

Date: 2026-09-07
Status: **FROZEN BEFORE ANY D4 TEACHER SEARCH / FIT / HELDOUT READ**
Parent preregistration: `L3_D4_SEARCH_UTILITY_ORDERING_PREREGISTRATION_V1_20260907.md`

## 1. Scope

The parent preregistration removes every canonical example key that appears in more than one root split, then ranks remaining examples by SHA256 of `D4-EXAMPLE-2026111502:` plus the canonical example key.

It did not state how to order two distinct **occurrences inside the same split** when their canonical example key is identical. Such occurrences can have different cheap runtime-history features (`killer`, `countermove`, `history`, `conthist`) even though the frozen canonical selection key is the same. Therefore an implementation-specific tie-break could change the fitted dataset and must be fixed before execution.

No D4 candidate root generation, WDL_CONTROL teacher search, beta-cutoff label, D4 fit, VALID/TEST metric, runtime preflight, game or D4 model byte has been generated/read before this amendment.

## 2. Frozen clarification

Cross-split behavior is unchanged:

- if a canonical example key occurs in more than one root split, **all occurrences of that key are removed from all splits**.

Same-split behavior is now explicit:

- multiple occurrences of the same canonical example key **remain eligible**;
- their primary rank remains the exact parent-preregistered SHA256 of `D4-EXAMPLE-2026111502:` plus the canonical example key;
- when that primary digest is equal, order occurrences by ascending integer `(root_index, event_index)`;
- `root_index` is the frozen index from the 4,000-root target-blind manifest;
- `event_index` is the zero-based emission order of eligible beta-cutoff events within that root's deterministic teacher search;
- no feature value, cutoff label, game outcome, candidate score, model metric, phase result, or runtime result participates in the tie-break.

This tie rule applies only to exact same-primary-rank occurrences. It does not alter the canonical key, split definitions, sample counts, feature vector, model, optimizer, bootstrap, gates, seeds, budgets, or runtime contract.

## 3. Scientific invariants unchanged

Everything else in the parent preregistration remains immutable, including:

- 30,000 fresh roots, seed `2026111501`, selector `2026111502:`;
- 4,000 roots split 3200/400/400 before teacher search;
- exact 50,000-node WDL_CONTROL teacher searches;
- exact 96k/12k/12k example counts;
- 24 features × 4 phases = 96 float64 coefficients;
- one zero-init L-BFGS-B fit, L2 `1e-3`, max_iter 500, maxcor 10, gtol `1e-6`;
- TEST bootstrap 200,000 seed `2026111503` and all terminal gates;
- D3 remains closed; no 1857 game outcomes, qscore, SearchDecisionTrace target, 1843 full ladder, new deep-value teacher, tuning, promotion or bake.

This is a pre-execution deterministic-selection clarification only.
