# L3 — SearchDecisionTrace v1 contract

Date: 2026-09-05  
Status: A1/A2 implementation contract; passive instrumentation only.  
Base: `develop` @ `db6e6a5ce88fdd48f8e9b3c998974ceb4f31085e`.

## Scope and invariants

`SearchLimits::search_decision_trace` is an optional caller-owned pointer. Its
default is null. A non-null pointer records work the production search already
performs; it does not change negamax, pruning, move generation, rules, TT
stores, ordering, aspiration windows, node accounting or evaluation. It does
not launch a second search. Lazy-SMP helpers construct their own `SearchLimits`
and deliberately leave this pointer null.

The trace is a diagnostic receipt, not a globally exact teacher label. Every
bound is restricted to the recorded horizon and alpha/beta window. Internal
alpha-beta pruning is compatible with that fail-soft window contract but does
not prove a deeper or game-theoretic value.

Tracing allocates records and reconstructs PV prefixes through read-only TT
probes. That overhead can change where a wall-clock `movetime_ms` limit fires.
The zero-mismatch gate therefore covers deterministic fixed-depth and exact-node
searches with fresh state: best move, score, completed/effective depth, nodes,
evaluation calls and public PV must match with tracing OFF and ON. Existing SMP
searches retain their existing scheduling/TT-race nondeterminism; only the main
thread is traced.

## Bound contract

For a completed call with fail-soft return `score` and original window
`[alpha,beta]`:

```text
score <= alpha  -> Upper
score >= beta   -> Lower
otherwise       -> Exact
```

Equality is deliberately a failure at each boundary. An interrupted action or
attempt is always `None`, including a depth-1 interruption; its integer score
is diagnostic only. A root beta cutoff is a completed `Lower` attempt even
though it did not visit every action. `all_actions_searched` distinguishes that
case from a full root scan. `root_actions` is the complete ordered semantic
catalogue, so an action absent from an attempt's `actions` array is unsearched,
not excluded or dominated.

The semantic move identity is:

```text
(from, to, num_captures, promotes, captured-square bitset)
```

Capture order/path spelling is absent by construction. Several geometric paths
with the same endpoints and captured-square set cannot gain additional action
weight. The trace keeps the move-generator order and never reorders production
search.

## Captured records

Each aspiration attempt stores depth, one-based attempt number, original
alpha/beta, fail-soft score and bound, selected semantic move, cumulative
nodes/evaluation/PVS counters before and after, root cutoff, interruption
completion, root-action coverage and the actions actually searched.

Each searched semantic action stores its own alpha-before/beta window,
fail-soft score/bound, node/evaluation/PVS deltas, root cutoff, completion and a
PV-prefix hash/length. The final receipt stores the public result's move, score,
completed/effective depth, interruption and stop reason, counters and public PV
hash/length. A rule-drawn root is marked `root_rule_draw`; its final receipt
score is the rule score `0` while attempt scores remain the search observations.
A no-legal-move root is marked `no_legal_moves`, has an empty catalogue and no
attempts, and records the normal mate-loss result.

PV extraction only calls the existing const TT probe path and legal move
generation; it performs no TT store. Because only Exact TT entries are walked,
the stored PV can be a prefix. `pv_length` is therefore observed prefix length,
not a completeness claim. The v1 hash is 64-bit FNV-1a, offset basis
`14695981039346656037`, over each semantic move in order. Each move contributes
`from`, `to`, `num_captures`, `promotes` as one byte each, followed by the
64-bit captured-square bitset as eight little-endian bytes.

## Deterministic serialization v1

`serialize_search_decision_trace_v1()` emits one compact UTF-8 JSON object with
fixed key and array order. It imbues the classic C locale, so integers never
acquire locale-specific grouping. All integers are decimal JSON numbers and all
booleans are JSON booleans.

Top-level order:

```text
schema = "jass.search-decision-trace"
version = 1
root_rule_draw
no_legal_moves
semantic_root_actions
root_actions[]
attempts[]
result
```

`semantic_root_actions` equals `root_actions.length`. Move objects use fixed
field order `from,to,num_captures,promotes,captured`. Attempts and actions keep
production observation order. A3 may wrap these objects in JSONL or another
artifact container, but must not reinterpret `None`, missing actions, PV
prefixes or horizon-local bounds as exact values.

## A1/A2 validation

The native C++ suite covers:

- fresh-state OFF/ON identity at fixed depth and an exact node cap;
- fail-soft equality at alpha/beta and interrupted `None` classification;
- a real production aspiration attempt containing an `Upper` action, a
  fail-high `Lower` root cutoff and an `Exact` widened retry;
- depth-1 exact-node interruption, no-legal-move and rule-drawn roots;
- the historical multi-capture path witness as nine unique semantic actions;
- deterministic serialization under a hostile grouped-integer global locale.

This work starts no game, fit, adaptive racing engine, remote job, promotion or
bake. A3 export/readout remains a separate consumer of this v1 contract.
