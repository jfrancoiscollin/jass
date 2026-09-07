# L3 Decision Information — D3 runtime move-ordering support amendment v1

Date: 2026-09-07  
Status: **PRE-EXECUTION CONTRACT CLARIFICATION — NO GAME READ**

This amendment applies to `L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md` before any D3 runtime implementation/preflight or game result is read.

## Reason

The frozen D3 relational adapter was fit and validated only on the authenticated C domain:

```text
P0 = 30..40 pieces
P1 = 20..29 pieces
P2 = 12..19 pieces
P3 = 9..11 pieces
```

The runtime preregistration defines the same four phase blocks but did not state what happens after a game reaches fewer than 9 pieces, where no frozen D3 phase exists. Extending P3 to 1..8 would be an unpreregistered extrapolation; inventing a fifth phase would change the model.

## Authoritative support rule

The only admissible interpretation is:

```text
parent pieces 9..40  -> apply the exact frozen D3 move-order score
parent pieces 0..8   -> D3 is unsupported; preserve the exact legacy/control ordering
```

This is a support boundary, not phase gating inside the trained domain. No P0/P1/P2/P3 enable/disable is allowed. Within 9..40 pieces, D3 applies exactly as frozen to every non-authoritative sibling tier.

The value evaluator, adapter bytes, square canonicalization, score formula, seeds, pools, budgets, statistics and gates are unchanged.

## Mandatory guards

Implementation and zero-game preflight must prove:

```text
phase(40)=P0, phase(30)=P0
phase(29)=P1, phase(20)=P1
phase(19)=P2, phase(12)=P2
phase(11)=P3, phase(9)=P3
phase(8)=UNSUPPORTED
```

A D3-enabled binary on a deterministic <9-piece fixture must reproduce control ordering/search semantics exactly because the treatment is dormant there.

No valid/test/strength metric motivated this amendment. No game has been authorized or run under the D3 runtime experiment before this clarification.
