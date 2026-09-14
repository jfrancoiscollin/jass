# ED4-FRESH W production 1956 — stale rehearsal spec incident

Date: 2026-09-14.

Job `cpx62-1956-l3-ed4-fresh-w-source-production-v2`, attempt `20260914T062646Z-80167252`, failed before W source execution with launch classification `TECHNICAL` / `STALE_REHEARSAL_SPEC`.

The failure exposed a mismatch between the W source's original engineering rehearsal shape and Launch V2's production-admission invariant. Rehearsal 1953 used the same W source stage but deliberately generated a small 4096-record / 32-opening / 512-position score-free cohort. Production uses the preregistered 40960-record initial budget and requires 512 opening clusters / 8192 positions. Launch V2 intentionally permits only `LAUNCH_MODE` to differ between rehearsal and production; data/budget/spec differences invalidate the rehearsal receipt. Therefore 1953 cannot authenticate a 40960-record production spec, even though both are target-blind.

The repair does not relax Launch V2. Instead, a thin W-source wrapper makes a new rehearsal execute the exact production source shape (40960 records, 512 opening clusters, 8192 zero-target positions) while retaining rehearsal evidence classification. The subsequent production spec is identical except for `LAUNCH_MODE=production`. The underlying W generator, seed `202609120402`, CURRICULUM identity, selection rule, 8 rows/game, 2 games/opening, target-byte sanitization, no-outcome-read barrier, support ladder and alpha accounting are unchanged.

No confirmation target was read by 1956 and no W production cohort was consumed.
