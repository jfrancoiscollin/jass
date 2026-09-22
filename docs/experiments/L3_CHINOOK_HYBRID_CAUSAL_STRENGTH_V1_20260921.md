# Jass Chinook Hybrid causal strength test V1

Date: 21 September 2026
Status: PREREGISTERED / RUNTIME IMPLEMENTED / REHEARSAL TECHNICAL FAILURE / NO SCIENTIFIC VERDICT / NO PROMOTION AUTHORITY

Causal intervention: use immutable CURRICULUM outside the fixed Chinook gate, and immutable HIER inside it. The gate is exactly 9-19 total pieces, 5-8 legal moves, and side-to-move strictly behind in weighted material (man=1, king=3). No centipawn bonus, blend weight, threshold tuning, or learned amplitude is allowed.

Frozen model SHA256 values:
- CURRICULUM 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
- HIER 95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628

Strength contrast: CHINOOK_HYBRID vs CURRICULUM. Fresh deterministic opening seeds are pool=2026092121 and order=2026092122, with the 1651 cohort and 2066 calibration trajectories excluded. Rehearsal uses 8 representative starts and self-contrasts only. Production uses 288 colour-reversed pairs (576 games), 100 ms/move nominal, one thread, no book, fixed-N paired Hoeffding alpha 0.05, with the existing 100-Elo substantial-loss margin and ply-cap partial-identification rules. No result authorizes promotion, bake, retuning, or wider search.

## Pause checkpoint — 23 September 2026

Runtime implementation commit:
`7a3a13679274079055262241c3829f4d1077d1d7`.

The first representative rehearsal was:

- job `cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1`;
- attempt `20260921T200839Z-7a3a1367`;
- exit code `2`;
- classification `TECHNICAL`;
- failure `STAGE_FAILED:EXECUTE / ValueError`;
- last phase `build-runtime`.

Recorded stack: `chinook_hybrid_strength.py:151 main` ->
`cls_g0_strength_calibration.py:157 build` ->
`cls_g0_strength_calibration.py:109 command` ->
`cls_g0_strength_calibration.py:49 need`.

The failure occurred before the paired strength phase. It is therefore **not a
scientific negative result**. No rehearsal READY terminal exists, the production
main was not admitted, and no CHINOOK_HYBRID-vs-CURRICULUM strength verdict exists.

Restart rule: diagnose and repair only this technical build-runtime failure while
preserving the preregistered models, fixed gate, seeds, opening rules, cadence,
sample sizes, confidence rule and verdict mapping. Rerun the exact representative
rehearsal. Admit the frozen 288-pair / 576-game main only after
`CHINOOK_HYBRID_STRENGTH_REHEARSAL_READY_V1`, `production_ready=true`, and
the required published Launch V2 round-trip.

Canonical pause handoff:
[L3_CHINOOK_PAUSE_HANDOFF_V1_20260923.md](L3_CHINOOK_PAUSE_HANDOFF_V1_20260923.md).
