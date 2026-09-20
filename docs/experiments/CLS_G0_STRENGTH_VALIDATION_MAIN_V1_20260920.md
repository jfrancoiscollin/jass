# CLS G0 strength validation — main appendix V1

Date: 2026-09-20. Prospective, before any HIER/CURRICULUM game. JFC's
"Reprendre" continues the approved separate case study after calibration 2066.
This appendix completes Stage B of `CLS_G0_STRENGTH_VALIDATION_V1_20260920.md`.
The limited exception applies only to the already sealed HIER/CURRICULUM
pair; it does not reopen CLS-G0 V1, LOCAL/WDL/MIXED, or any promotion path.

## 1. Exact question and fixed estimand

At nominal 100 ms per move, is the selected HIER candidate substantially
weaker than CURRICULUM on the prospectively defined random legal opening
population? This is a bounded **coarse catastrophe case study**, not a
small-Elo superiority test or general calibration of G0's false-rejection rate.

Unchanged identities:
- HIER: `95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628`.
- CURRICULUM: `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.
- Native source is byte-unchanged from `7b789a0c675ce08868fe4a8fcef0becaa4193286`.
- Historical 2063 FAIL remains `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1`.

Both players use the same executable, compiled SearchParams defaults, book
off, one thread, TT 16 MiB and EGDB `/root/egdb_extracted/app`, cache 256 MiB.
Four pair workers; fresh player/referee processes each game; colours reversed
once per opening. No fitted model, teacher, SearchParams, scale or second dose.

## 2. Cadence review and prospectively explicit initialization policy

2066 completed 44 same-model calibration games, zero cross-model games.
It flagged 72 timed responses above 250 ms, 36 per model. Their attribution
is NOT assumed: this stage authenticates the original game-level telemetry
and publishes how many were each player's first request versus later requests.
The source has lazy EGDB initialization and handshake-time bitbase warming;
source inspection alone does not establish the cause of every observed delay.

Before each scored game, each player performs exactly one fixed depth-1
search from standard startpos (`W:W31-50:B1-20`), then resets via the existing
new-game/position path. It is initialization, not a test-opening analysis.
Warmup requests are logged and counted; their moves/scores never select an
opening or parameter. No native code changes are made. This is a prospective
apparatus policy, not an in-place repair/reinterpretation of calibration 2066.

All scored requests are `go movetime 100`. Maximum observed end-to-end
response time is **120 ms**, identically for both models: 100 ms nominal
engine allowance plus a prospectively declared 20 ms process/transport
ceiling. This is NOT a bank-clock 100 ms strict flag-fall match. Report the
nominal cadence and ceiling together. Any excess is TECHNICAL and invalidates
the attempt; it is never scored as a draw/loss or silently forgiven. A ceiling
failure does not authorize increasing it. Warmup and game response telemetry
remain separate, including the complete distribution and exact capture moves.

## 3. Independent opening construction and immutable identity barrier

Use the unchanged native score-free command twice and require identical bytes:

`--gen-opening-pool 1024 <file> 8 32 20 2026092007`

This samples random legal trajectories from startpos, one retained quiet
position per trajectory, 8–32 plies, at least 20 pieces, under the existing
native structural filters. No evaluator is loaded for generation; no search
or score-based balancing is performed. No claim of human-opening
representativeness is made.

Exclude rotation180/colour-swap canonical board+STM identities of:
- all 2,000 parents of immutable selection 1651, covering diagnostic DEEP512;
- every position in the 44 published calibration 2066 trajectories;
- the fixed standard warmup position.

Canonicalization is the exact existing `tb_frontier_symmetry_dedup` rule.
Deduplicate candidates by that identity, sort by the hash of
`[2026092008, canonical_fingerprint]`, and retain exactly the first 296:
**288 main openings, followed by eight disjoint representative openings**.
No replacement, score filtering or seed search. Insufficient coverage fails
closed. No global disjointness from historical training is claimed: freshness
here concerns the documented consumed diagnostic/calibration starts.

Rehearsal publishes `opening-freeze.json` with ALL ordered FENs, canonical
identities, selection SHA, exclusion SHA and count BEFORE any rehearsal games.
Production must read that exact authenticated artifact from the Launch-V2
rehearsal roundtrip. It cannot regenerate, change or select a different list.
If a main start occurs anywhere in a representative rehearsal trajectory,
production is blocked; no replacement is permitted under this version.

## 4. Non-comparative real-host rehearsal

On the eight representative openings, play CURRICULUM/CURRICULUM and
HIER/HIER, colours reversed: **16 pairs / 32 games**, zero cross-model games.
All clock, loading, legality, pairing, output and publication paths are the
same as production. These games do not enter inference. Their scores do not
choose anything. No repeated same-model production calibration is required.

A green rehearsal requires actual native execution, all requested pairs,
no warm scored response over 120 ms, no technical or time-cap game, complete
telemetry/trajectories, and no main-start overlap. The projected main work is
`288 * measured_representative_block_seconds / 16`, including process startup
and observed four-worker throughput. It must not exceed **2,700 seconds**.
Otherwise emit preparation BLOCKED, never modify N/cadence or call it ready.
This is an operational admissibility check, not a prediction guarantee.

Historical 2066 rate was 475.7416 pairs/hour on nine familiar starts. It is
planning context only (about 2,179 seconds of paired work for 288 pairs),
not a transported assertion about the new population. No cross-model peeking
is used for sizing. Same-code, same-profile, same-normalized-spec Launch-V2
rehearsal/publisher proof is required before production.

## 5. Finite main sample, margin and statistical decision

Exactly **288 pairs / 576 games**, one reversed-colour pair per main opening.
No interim inferential decision, SPRT, optional extension or additional cadence.
The important loss for THIS coarse study is prospectively **100 logistic Elo**:

`p_boundary = 1 / (1 + 10^(100/400)) = 0.35993500019711494`.

This is an operational definition of a large degradation, not a claim that
smaller losses are acceptable or undetectable. It deliberately does NOT
answer whether HIER gains Elo or loses 10–50 Elo. Logistic Elo refers only
to the head-to-head score mapping, not federation or external ratings.

Primary analysis uses bounded pair scores and a fixed-N Hoeffding interval.
Its coverage assumes independent sampled opening-pair units (or the standard
fixed-outcome without-replacement sampling interpretation); machine scheduling
noise is not asserted independent by fiat. Shared-hardware artefacts remain
an engineering limitation. The opening population and selected-candidate
status must accompany every conclusion; no population-wide G0 claim is allowed.

For each nontruncated game, score is 0/0.5/1 for HIER. An administrative
160-ply cap is **censored**, not proof of a draw: give it lower score 0 and
upper score 1 for inference. Average the two colours to get pair bounds
`L_i,U_i in [0,1]`. Observed half-point cap scores/pentanomial counts are
published separately as descriptive summaries only.

With study-specific alpha 0.05:

`r = sqrt(log(2/0.05)/(2*288)) = 0.08002689927666005`

`CI = [max(0,mean(L)-r), min(1,mean(U)+r)]`.

Each one-sided Hoeffding error is at most 0.025; their union is at most 0.05.
No historical variance transport or pseudo-independent counting of 576 games
is required. The two colours are NEVER treated as independent observations.
At true mean score 0.5 with no censoring and independent pairs, the bound
`1-exp(-2*N*(0.5-p_boundary-r)^2)` gives approximately **87.46%** probability
of excluding this 100-Elo loss. Censoring widens the bounds and lowers power;
the study may correctly end indeterminate. At observed score 0.5 without
censoring the interval is about [0.4200,0.5800], not a small-gain claim.

Only three terminal statistical conclusions:
- upper bound strictly below boundary: `SUBSTANTIAL_LOSS_SUPPORTED`;
- lower bound strictly above boundary: `SUBSTANTIAL_LOSS_EXCLUDED`;
- otherwise, including equality: `INDETERMINATE`.

This allocates a new study-specific 0.05 interval-error budget, recorded as
`alpha_spent=0.05` only for the complete main readout. It does not overwrite
old CLS/ED4 alpha or turn consumed diagnostics into fresh confirmation.
No main scores may guide technical changes, sample extensions or thresholds.

## 6. Failure, compute and accounting

Existing 25-move/threefold logic and terminal-before-cap order are unchanged.
Illegal moves, no-move with legal moves, protocol errors, missing telemetry,
excess response time, incomplete pairing and game wall-time caps are TECHNICAL,
not evidence of weak play. Record the central incident if a technical failure
occurs. Preserve consumed trajectories; any deterministic repair must retain
this exact science and document the attempt. Do not drop or impute pairs.

Per-game cap 60s, owned pair-process-group cap 180s, stage hard cap 3600s,
canonical dispatcher cap 4200s. These are safety ceilings, not promised ETAs.
Scratch outside Git, 3GiB free-space guard, incremental per-worker counts and
progress, cleanup only of owned process groups. No global cleanup or restart.

Effects: rehearsal <=32 games and 5,184 player searches including warmups;
production <=576 games and 93,312 searches including warmups. All games are
reported honestly in `strength_games`. Zero fits, new Scan searches, training
self-play, promotions, bakes and confirmation-target reads.

## 7. Final decision boundary

Even `SUBSTANTIAL_LOSS_EXCLUDED` means only that a large loss was excluded in
this case and cadence under stated assumptions. It is neither G0 PASS nor
superiority, promotion, reinjection, or permission to loosen G0 retrospectively.
CURRICULUM remains champion. On completion stop for interpretation; do not
automatically open another candidate, cadence or research direction.
