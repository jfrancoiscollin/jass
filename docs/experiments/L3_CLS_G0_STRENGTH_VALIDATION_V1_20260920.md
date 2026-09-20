# CLS G0 strength validation V1 — separate study and calibration

Date: 2026-09-20. Status: **CALIBRATION AUTHORIZED; MAIN MATCH NOT YET ADMITTED**.

## 1. Purpose and explicit limited exception

JFC approved the proposal to study HIER versus CURRICULUM in paired games at
fixed time, preceded by a bounded harness/throughput calibration. This is a
NEW study of the relation between a G0 rejection and actual game outcomes,
not continuation or rescue of the rejected candidate in CLS V1.

This document explicitly grants a limited study-only exception to the
no-strength-after-G0-failure clauses in
`L3_CLS_G0_RUNTIME_CATASTROPHE_CONTRACT_V1_20260916.md` sections 8–9 and
`L3_CLS_HIER_L2_NEXT_CANDIDATE_V1_20260918.md` sections 6–7. The exception is
restricted to these two immutable evaluators and this study. It does not
admit LOCAL/WDL/MIXED, another HIER dose, new training, or a new G0 attempt.
The old documents and all their terminal results remain unchanged.

- CURRICULUM: `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.
- HIER: `95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628`.
- Original 2063 attempt: `20260919T155826Z-a6f9fa6f`.
- Original verdict remains `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1` / FAIL.

No study result can promote, bake, reinject or relabel HIER as G0 PASS.
CURRICULUM remains champion. This study is not a general validation of G0:
one deliberately selected rejected candidate cannot estimate the gate's
false-rejection rate across future candidates.

## 2. Evidence motivating the study — not fresh confirmation

2064 found actual depth shortfalls on all 30 missing-receipt roots, but no
overall median-throughput collapse and a positive descriptive mean depth
difference. 2065's independent Scan analysis was mixed. Neither produced a
HIER/CURRICULUM match result. These consumed diagnostics motivate this
case study; none of their root scores or preferences select main openings,
time controls, margins or additional candidates.

The 2013 telemetry explicitly said `future_sprt_sizing_inputs_ready=false`
and `native_search_throughput_available=false`. Its mixed-stage throughput
must not be presented as actual search capacity. Calibration is therefore
required before freezing a costed main game count.

## 3. Stage A — precisely bounded calibration

This stage measures the apparatus; it never compares HIER with CURRICULUM.

| Block | Model on both sides | Openings | Colour-swapped pairs | Games |
|---|---|---:|---:|---:|
| Deterministic sanity, depth 3 | CURRICULUM | 2 | 2 | 4 |
| Deterministic sanity, depth 3 | HIER | 2 | 2 | 4 |
| Timed calibration, 100 ms/move | CURRICULUM | 9 | 9 | 18 |
| Timed calibration, 100 ms/move | HIER | 9 | 9 | 18 |

Total: **44 games**, at most **7,040 player searches**. Exactly one
colour-swapped pair per opening per block. No repetition inflates an
inferential sample: these are calibration games, not confirmation games.

Openings are the nine standard first moves, in order:
`31-26,31-27,32-27,32-28,33-28,33-29,34-29,34-30,35-30`.
The first two serve the deterministic block. They are enumerated without
search or score-based selection and sealed before any game. No freshness
claim is made for this familiar pool. All nine board+STM identities, and
their rotation/colour equivalents, must be excluded from future main starts.

Execution: CPX62's 16-CPU resource contract, four concurrent pair workers,
one thread/player, same newly built native executable, book off,
TT default 16 MiB, ordinary compiled SearchParams (no legacy runner's
implicit 6/6 override), real EGDB path `/root/egdb_extracted/app`, cache
256 MiB/player. New player/referee processes for EVERY game; no state can
leak from one colour order to the next. Native engine, evaluator, movegen,
CMake and pattern code must equal source base
`7b789a0c675ce08868fe4a8fcef0becaa4193286`.

The apparatus uses existing `calibrate_vs_scan` engine/referee/game logic,
with study-local strict wrappers, not edits to historical harnesses:

- explicit model SHA checks before and after each pair;
- real model-load handshake and native EGDB selfcheck before any games;
- protocol errors, illegal moves, missing native telemetry, worker failure,
  and game wall-time caps are TECHNICAL failures, never scores/draws;
- all move requests retain nodes/depth/eval calls and measured response time;
- each game retains the opening, full FEN trajectory, move/capture identities,
  colour, termination reason and outcome;
- ordinary 25-move/threefold adjudication is unchanged;
- at 160 plies, check terminal legality first; only a nonterminal game is a
  separately recorded administrative `ply cap` draw;
- per-game safety cap 60s, per-pair cap 180s, stage 1800s and dispatch 2400s;
  these are safety ceilings, not measured runtime predictions;
- owned worker process groups are killed on failure; partial data never pass;
- outputs are outside Git, with actual game/search counters and phase progress.

Sanity requires each deterministic self-pair to score exactly one point in
two games and reproduce the same complete FEN trajectory. Timed self-play
is NOT required to reproduce byte-identical games: wall-clock search can
vary. Its scores must NOT tune or select anything.

Responses over 250ms are counted as an operational timing-review flag,
NOT forgiven match-clock losses and NOT evidence that 100ms was respected.
There is no inference from this calibration. The full duration distribution,
termination distribution and actual observed pair throughput are published.
Throughput on nine first-move starts is explicitly not asserted to be the
rate of the future independent opening population.

## 4. Stage B — main preregistration barrier

A green Stage A permits **design/sizing**, not execution of a main match.
Before a first cross-model game, a separate immutable main appendix MUST fix:

1. independent opening source, seed, count, complete ordered identity list and
   disjointness evidence against the consumed diagnostic starts and calibration
   starts; selection must not access HIER/CURRICULUM scores;
2. the single fixed cadence and identical engine/resource/EGDB conditions;
3. an operational cadence/termination review and a representative throughput
   check without HIER-versus-CURRICULUM outcome peeking;
4. the smallest important loss margin, power/precision calculation, finite
   pair ceiling, statistical method, confidence levels and alpha accounting;
5. pair/cluster unit (never treat colour-reversed games as independent),
   administrative ply-cap handling, technical aborts and missing-pair handling;
6. three outcomes: substantial loss supported, substantial loss excluded within
   the predeclared margin, or indeterminate at the ceiling;
7. no optional extension, cadence search, result-dependent stopping,
   post-result recalibration, promotion or automatic research continuation.

No particular Elo margin or game count is declared scientifically justified
by this calibration document. They must be explicitly justified and frozen
BEFORE cross-model outcomes. Historical variance is planning information,
not assumed to transport exactly to this new match population. A resource
ceiling that cannot supply the predeclared precision yields an explicit
resource/information limitation, never a fabricated negative result.

The selected-candidate and consumed-data origin of the hypothesis must be
reported even when the main openings are independent. Native Scan centi,
agreement with CURRICULUM 1M and nominal depth are not the main endpoint.

## 5. Admission, outputs and immutable boundaries

Stage A runs under a new Launch-V2 profile, with generic admission suites and
focused whole-path synthetic tests. Real target-host rehearsal comes before
any production-shaped reuse. Its receipt cannot authorize a main-match
profile with a different workload or candidate pair.

Stage A terminal: `CLS_G0_STRENGTH_CALIBRATION_COMPLETE_V1`.
Classification: `TECHNICAL_CALIBRATION_ONLY`; scientific verdict null;
`cross_model_games=0`, `main_match_admitted=false`, `main_sizing_finalized=false`.
Next stage: `FREEZE_INDEPENDENT_MAIN_OPENINGS_AND_STATISTICAL_CONTRACT`.
Actual calibration games are honestly counted in the `strength_games`
execution-effect field (despite their non-inferential role), never reported
as zero games. Fits, new Scan searches, alpha, promotions and bakes remain 0.
No training/self-play corpus is produced or reinjected.

This document does not alter the CLS generation counter or close/reopen
another branch. Reconsidering G0 for future candidates remains a distinct
prospective protocol/version decision.
