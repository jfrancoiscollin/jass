# Jass Chinook Hybrid causal strength test V1

Date: 21 September 2026
Status: PREREGISTERED / NO PROMOTION AUTHORITY

Causal intervention: use immutable CURRICULUM outside the fixed Chinook gate, and immutable HIER inside it. The gate is exactly 9-19 total pieces, 5-8 legal moves, and side-to-move strictly behind in weighted material (man=1, king=3). No centipawn bonus, blend weight, threshold tuning, or learned amplitude is allowed.

Frozen model SHA256 values:
- CURRICULUM 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
- HIER 95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628

Strength contrast: CHINOOK_HYBRID vs CURRICULUM. Fresh deterministic opening seeds are pool=2026092121 and order=2026092122, with the 1651 cohort and 2066 calibration trajectories excluded. Rehearsal uses 8 representative starts and self-contrasts only. Production uses 288 colour-reversed pairs (576 games), 100 ms/move nominal, one thread, no book, fixed-N paired Hoeffding alpha 0.05, with the existing 100-Elo substantial-loss margin and ply-cap partial-identification rules. No result authorizes promotion, bake, retuning, or wider search.
