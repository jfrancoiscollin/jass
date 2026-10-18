# P4 internal stochastic root rollout V1 — engineering result

Date: 2026-10-18  
Preregistered proposal: [`P4_INTERNAL_STOCHASTIC_ROOT_ROLLOUT_V1_PROPOSAL_20260921.md`](P4_INTERNAL_STOCHASTIC_ROOT_ROLLOUT_V1_PROPOSAL_20260921.md)

## Result

The one permitted synthetic engineering pass did **not** establish feasibility
for P4 V1. Its fixed native fixture completed, but the same-call certified
top-two selector returned no pair. The preregistered terminal is:

`P4_INTERNAL_ROOT_ROLLOUT_FEASIBILITY_NOT_ESTABLISHED_V1`

This is a failure to demonstrate the required fixture obligation, not evidence
that every possible rollout mechanism is impossible. P4 V1 is closed at this
terminal; it has no scientific evaluation result and was never activated.

## Evidence

PR #1085 merged after CI passed on head
`388410af9e6cd199cca2041ba56a23bfae2a30b0` (squash commit
`903452b2161db8474fc409bf2760197d954d9f2f`). The native suite passed 27,710
assertions; WASM, Python tooling, retirement-readiness and technical-incident
checks passed.

The prospectively fixed fixture used `Position::start_position()`, synthetic
`R=16384`, base cap `8192`, depth `6`, one thread, Exact node-limit mode, null
external model, and separate fresh transposition tables with trace disabled and
enabled. It reported:

```text
status=EXECUTED, identity=true, nodes=5394, stop=None, top2=false,
attempts=6, actions=9, trace_work_nodes=5394
```

The search completed below its cap; Exact is a ceiling and does not pad work.
The observation was kept as produced. No fixture, budget, depth, move order or
case was changed to seek a pair.

## Source boundary

In the current root pass, a move may raise `cur_alpha`; subsequent completed
actions at or below that window are valid `Upper` bounds, not exact scores.
The P4 selector correctly refuses to rank those values as points or combine
attempts. The public trace summary does not expose every action bound, so this
explains why the result is plausible but does not identify the exact predicate
that rejected this fixture.

The `root_order_schedule` API is diagnostic-only, empty by default, and
controlled through mutable HUB state; it is not pinned by P4. Its historical
operational producer is an external Scan root-order oracle for closed 0961.
Using it to force another exact pair is outside the frozen contract.

## Scope

The change and tests are fixture-gated helpers only. No live tablebase,
evaluator, scientific case, R2 payload or CPX job was read or used. The CI and
synthetic receipt tests do not authenticate future real EGDB/evaluator receipts,
prove fresh-source exclusions, establish absolute `R`, sample size `N`, alpha,
or support a scientific superiority or calibration claim. `CURRICULUM` remains
champion. No bake, promotion or scale-up is admitted.

Any new line must be a separately preregistered prospective version. It may not
use the diagnostic order interface or reinterpret `Upper` bounds as exact
values to reopen P4 V1.
