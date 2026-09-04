# L3 — SearchDecisionTrace A3 export/readout contract v1

Date: 2026-09-05
Status: implementation contract; diagnostic export and mechanical readout only.
Base: `develop` @ `107be69832111354cd61504aff208458979f26e9`.

## Scope

A3 exposes the passive `SearchDecisionTrace` v1 receipt added by A1/A2 and
derives horizon-local decision diagnostics. It does not change production
search, choose a corpus, define a scientific threshold, fit a model, play a
game, authorize a bake or promote a candidate.

The exporter is a separate native-only executable. The Python readout consumes
only completed export artifacts. Neither component is part of the production
or WASM front-end.

## Export input and search context

`jass_search_decision_trace_export` accepts:

```text
jass_search_decision_trace_export \
  <invocations.tsv> <traces.jsonl> <report.json> <model.pjtw|-> \
  <declared_code_provenance> <max_depth> [max_nodes=0] [tt_mb=16]
```

The finite TSV has the exact header:

```text
invocation_id	fen	halfmove_clock	history_hashes_hex
```

`history_hashes_hex` is an ordered comma-separated list of predecessor
Zobrist hashes, or `-` for no history. Invocation IDs must be unique. The
exporter parses every row before search and fails on an empty input, malformed
FEN, negative rule counter, malformed history or duplicate ID.
The rule counter is capped at `INT_MAX-MAX_PLY` to leave defined increment room
for every supported search horizon.
Numeric fields accept only their documented ASCII digits; in particular,
whitespace, signs, prefixes, empty tokens and trailing history commas fail.
Before opening an output, canonical/equivalent path checks prevent the JSONL
or report from aliasing the manifest, executable, model, present or future
conventional sidecar, or each other. The readout applies the same rule to its
output versus every input JSONL and export report.
After receipt validation it also protects the recorded manifest, JSONL, model,
present or future sidecar and exporter executable, including equivalent
Windows/WSL path spellings. An output below a reserved file path is rejected so
directory creation cannot occupy a future sidecar name.

Every invocation uses:

- a newly constructed transposition table of the recorded size;
- one search thread, no book and no wall-clock limit;
- compiled default search parameters;
- fixed depth when `max_nodes=0`, otherwise exact node-cap mode;
- the recorded halfmove clock and ordered game history;
- either handcrafted evaluation (`model=-`) or the explicitly loaded model.

Runtime environment variables that could hide an evaluator, tablebase,
ordering, accumulator or trace context are rejected. Board identity, rule-state
identity and search-context identity are separate JSON objects. The context
records the actual limits and evaluator used.

The exporter verifies SHA-256 for the input manifest, its executable, the
optional model and conversion sidecar, and the completed JSONL. A caller-supplied
commit/job label remains `declared` with
`declared_verified_by_exporter=false`; it is never presented as authenticated
code provenance. The executable digest is recorded separately as verified
byte identity.

## Export row and report

Each JSONL line is one object with schema
`jass.search-decision-trace-export-row.v1` and contains:

```text
invocation_id
board_identity { canonical_fen, zobrist_hash }
rule_state_identity { halfmove_clock, history_hashes[] }
search_context_identity { evaluation, code_provenance, limits, TT policy }
trace                 # unmodified SearchDecisionTrace v1 object
```

Each derived context retains a source receipt with the input JSONL path,
SHA-256 and physical line plus the matching export-report path and SHA-256.
This stays unambiguous when several exports share an identical search context;
the durable readout does not need its inputs reopened to attribute an
invocation.

The companion `jass.search-decision-trace-export.v1` report binds the JSONL
digest to the input digest, invocation cardinality and common search context.
The readout verifies that every row has exactly that context. It also requires
zero fits, strength games, bakes and promotions and false training, tuning,
model-selection and promotion authorizations.

## Fail-closed readout

The readout requires every JSONL input to have a matching export report. It
rejects malformed JSON, blank lines, empty exports, duplicate invocation IDs,
unsupported schemas, report/digest/cardinality mismatch and quarantine drift.

Within each trace it validates:

- a unique complete semantic root catalogue;
- action membership and uniqueness in every attempt;
- captured-square bitsets limited to 50 squares with population equal to
  `num_captures`;
- `root_rule_draw` equal to the recorded fifty-move counter/repetition history
  predicate;
- contiguous depths and one-based attempt numbers;
- fail-soft bound classification, including equality at alpha/beta;
- signed 32-bit windows/scores and unsigned 64-bit counters matching the native
  trace field types;
- `None` for every interrupted action or attempt;
- cutoff, catalogue-coverage and completion consistency, including rejection of
  a completed partial root scan without a beta cutoff;
- sequential action alpha (`max(attempt alpha, prior action scores)`), completed
  attempt score/max and first-best tie reduction;
- cutoff or interruption only on the final observed action;
- monotone cumulative counters, exact action-to-attempt counter sums, a
  contiguous counter chain across attempts and equality with the final receipt;
- a fail bound followed by a same-depth retry that widens only its failed side,
  with `Exact` terminal for that depth and `None` terminal for the trace;
- a completed action PV prefix of length `1..depth`, and the canonical empty
  PV receipt for every interrupted action.

For this exporter’s fixed-depth/exact-node context, the readout also checks
completed/effective depth against the configured maximum, stop reason, exact
cap without overshoot, aborted-iteration state, public PV length/hash and the
final best move/score against the last settled horizon. It does not require
an action PV prefix to equal the public PV because later read-only extraction
may observe a different exact TT prefix.

Any contradiction is a technical contract failure. The readout does not repair
or average contradictory data.

## Bounds and certification

The only merge key is:

```text
(invocation_id, board identity, rule-state identity, search-context identity,
 depth, semantic action)
```

In implementation, every export row is analyzed independently, so bounds can
never cross invocations or contexts. Bounds also never cross depths. Completed
aspiration retries for the same action at the same depth may be intersected:

```text
Exact(v) -> [v,v]
Lower(v) -> [v,+inf)
Upper(v) -> (-inf,v]
```

A missing action, interrupted action or `None` contributes `[-inf,+inf]`: it
adds no finite evidence and can never establish dominance. It does not erase a
valid completed observation from another retry of that same horizon. An
intersection with `lower > upper` fails closed.

A multi-action horizon has a chosen action only when one attempt is complete,
`Exact`, covers the entire catalogue and contains a completed selected action.
Then:

```text
certified_at_current_horizon iff L(a*) > max_{b != a*} U(b)
R_max(a*) = max_b U(b) - L(a*)
```

Certification uses strict inequality. Thus an exact tie can have finite
`R_max=0` while remaining uncertified. If a required endpoint is unbounded,
the JSON uses `null` plus an explicit `UNBOUNDED` status; it never serializes
an infinity as a JSON number.

An empty catalogue is `NO_LEGAL_ACTION`. A singleton catalogue is
`SINGLE_LEGAL_ACTION`: selection is forced by legal support and its decision
regret is zero, but `chosen_value_exact` remains false unless the score interval
itself is exact. Forced selection does not certify the action value.

For a legal-action root with `root_rule_draw=true`, the public result score
remains the rule override zero while attempt scores remain search observations.
The readout labels that scope `RULE_DRAW_SEARCH_OBSERVATION`, reports its counts
separately from ordinary roots and never substitutes public zero into an action
interval or score sequence. A simultaneous no-legal-move root keeps the normal
mate-loss result, default empty move, empty-PV length/hash and zero counters,
and is explicitly `NO_LEGAL_ACTION`.

## Across-depth diagnostics

Only settled horizons enter across-depth sequences. Interrupted or otherwise
partial horizons remain visible but cannot affect:

- semantic best-move flips;
- `first_observed_suffix_stable_depth`, a retrospective description of the
  observed suffix rather than a future stopping guarantee;
- the raw settled-score path, signed steps, range and maximum absolute step;
- chosen-action PV-prefix churn across comparable `(hash,length)` pairs.

Aspiration counts are reported by `Upper`, `Lower`, `Exact` and interrupted
`None`; interruption is not called an aspiration failure. PVS re-searches are
the sum of attempt counter deltas within that horizon. No score threshold,
centipawn interpretation of mate values, confidence gate or terminal verdict
is added.

The output schema is `jass.search-decision-trace-readout.v1`. Its guards state
zero cross-invocation/context/horizon merges, thresholds, fits, strength games
and promotions. This readout is descriptive support for later separately
specified work; it is not a teacher label or promotion gate.
