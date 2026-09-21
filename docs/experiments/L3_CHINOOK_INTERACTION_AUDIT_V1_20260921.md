# Jass Chinook interaction audit V1

Date: 21 September 2026
Status: EXPLORATORY_CONSUMED_DATA / NO CAUSAL CLAIM / NO PROMOTION AUTHORITY

## Objective

Quantify a small, preregistered set of interactions suggested by the completed Chinook V1 singleton mining, without performing a combinatorial search.

The frozen gross-error definition is unchanged: top 64 CURRICULUM regret roots under the existing Scan 2M-per-child reference, tie-inclusive.

## Frozen inputs

- completed 2065 all-512 Scan reference table;
- frozen 1651 siblings catalogue.

No new Jass search, Scan search, fit, self-play, match, promotion or bake.

## Fixed interaction family

Before reading any joint interaction result, evaluate only:

1. CORE = phase in {P2,P3} AND legal_moves bucket == 5-8 AND stm_material_status == behind.
2. CORE_MEN_4_7 = CORE AND white_men in [4,7] AND black_men in [4,7].
3. PHASE_MOBILITY = phase in {P2,P3} AND legal_moves bucket == 5-8.
4. MOBILITY_BEHIND = legal_moves bucket == 5-8 AND stm_material_status == behind.
5. PHASE_BEHIND = phase in {P2,P3} AND stm_material_status == behind.
6. P2_CORE = phase == P2 AND legal_moves bucket == 5-8 AND stm_material_status == behind.
7. P3_CORE = phase == P3 AND legal_moves bucket == 5-8 AND stm_material_status == behind.

For each interaction report support, gross-error count/rate, baseline, lift, mean and median regret, and mean HIER-minus-CURRICULUM Scan delta.

This is descriptive consumed-data analysis only. No threshold crossing authorizes a feature implementation. Any runtime feature must be preregistered separately and tested causally.
