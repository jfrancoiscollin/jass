# D3 relational action residual — preregistration amendment v1

Date: 2026-09-07  
Status: **PRE-EXECUTION CORRECTION; NO FIT / NO HELDOUT READ / NO HYPERPARAMETER CHANGE**

## Scope

This amendment corrects one impossible square-index formula in Section 5.1 of `L3_D3_RELATIONAL_ACTION_RESIDUAL_PREREGISTRATION_V1_20260907.md` before any D3 implementation fit or held-out readout.

The authenticated C SiblingDataset-v2 semantic schema encodes playable-square indices in the closed interval **1..50**. The original text incorrectly wrote the white-side 180-degree mapping as `49 - sq`, which maps legal squares outside the playable domain (for example 50 -> -1).

The sole authoritative correction is:

```text
if parent_stm == black: sq_canon = sq
if parent_stm == white: sq_canon = 51 - sq
```

The same mapping applies to every set bit of `captured_square_bitboard`: source bit for square `sq in 1..50` maps to canonical square `51 - sq` when parent STM is white.

## Frozen invariants unchanged

Everything else in the D3 preregistration is unchanged, including:

```text
base action vector width = 158
phase blocks             = 4
trainable width          = 632
WDL_CONTROL coefficient  = 1.0 fixed
L2                       = 1e-3
optimizer                = L-BFGS-B
max_iter                  = 500
maxcor                    = 10
gtol                      = 1e-6
bootstrap replications    = 200000
bootstrap seed            = 2026111201
```

No C valid/test metric, D3 fit, model search, feature search, q-score, SearchDecisionTrace, or full-ladder reference is read to make this correction.

This amendment is authoritative over the single conflicting formula in Section 5.1 of the original preregistration. No other scientific choice is reopened.
