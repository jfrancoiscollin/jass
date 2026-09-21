# P4 internal root rollout — prospective scientific decision

Public proposal and bounded engineering contract; not a scientific activation.
The original decision below is followed by its normative root-score and
tablebase clarification. The companion JSON is
[`P4_INTERNAL_STOCHASTIC_ROOT_ROLLOUT_V1_PROPOSAL_20260921.json`](P4_INTERNAL_STOCHASTIC_ROOT_ROLLOUT_V1_PROPOSAL_20260921.json).
The standing user mandate permits the separately reviewed synthetic engineering
pass without a new consent request. It does not establish the open feasibility
obligations or admit scientific cases, source generation, matches, promotion or
scale-up through this proposal.

Date: 2026-09-21  
Decision status:
`P4_INTERNAL_ROOT_ROLLOUT_V1_PROSPECTIVE_CONTRACT_DEFINED__ACTIVATION_BLOCKED`

This record defines one mechanism prospectively. It authorizes neither an
implementation nor a fixture run, source generation, scientific compute,
queue admission, model read, match, promotion, or scale-up.

## Decision

The finite feasibility pass does not establish the mechanism, but it does make
a single prospective definition admissible. The current public source still
has caller-owned transposition tables, exact per-search node caps, position
copying, predecessor history, and domain-separated random streams. The missing
fixture and fresh-source proofs are therefore genuine open obligations rather
than evidence of architectural impossibility.

The sole treatment is an **online equal-material root chooser**. It replaces a
fixed part of one root's ordinary search allowance with four independently
seeded, fixed-policy continuations of the two best moves exposed by an initial
base search. It does not fit a model, relabel a corpus, change the evaluator,
restart self-play, or add a search-semantics cell.

## Fixed scientific definition

### P4 eligibility predicate

A root is eligible if and only if all of these conditions hold before any
treatment continuation:

1. the position is legal, non-terminal, and has at least two legal moves;
2. for each side, material is `men + 3 * kings`, and the two values are exactly
   equal;
3. the exact tablebase interface reports that the root is outside its resolved
   domain; an available tablebase result makes the root ineligible;
4. the case identity passes the prospectively sealed freshness and exclusion
   contract below.

There is no phase, score-margin, tactical, conversion, or outcome filter.

### Control and budget unit

Let `R` be the one prospectively pinned **exact-node root allowance**. Its
absolute value is not chosen here: it must be inherited from one named current
control setting before any case or outcome is opened, and it must be divisible
by `128`. Failure to identify such a scientifically relevant current allowance
is a feasibility failure; it is not permission to tune `R`.

The control is the unchanged current evaluator and current search, with one
root search capped at `R`, `NodeLimitMode::Exact`, and one thread.

The treatment has the same maximum authorized root work `R`:

- initial deterministic base search: allocation `R / 2`;
- two root candidates;
- two rollouts per candidate;
- at most 16 continuation plies per rollout;
- each continuation-ply search: allocation `R / 128`.

Thus the four rollout paths contain at most 64 continuation-ply searches and
their allocations sum to `R / 2`. All search calls use the same frozen
evaluator and search semantics as the control.

`R` is a cap ledger, not a demand for padding. A terminal position, forced
move, or other valid early stop may consume less than its allocation. Unused
nodes are recorded and are never transferred, redistributed, or filled with
dummy work. The record must publish every submitted allocation, actual returned
node count, stop reason, total actual nodes, static-evaluation count, and wall
time for both arms. All work needed to rank root candidates is charged to the
base `R / 2`; no hidden ranking search is allowed.

### Root candidates

The base search must expose its final root-move scores without another search.
Candidates are the two distinct legal moves with the best final scores at the
`R / 2` stop. Equal scores are ordered by ascending canonical move encoding.
If the reviewed implementation cannot expose two fully defined final root
scores from that same call, the contract fails; a second ranker or an uncharged
search may not be substituted.

### Continuation policy and independence

Each candidate child receives exactly two rollout ordinals. From that child,
each rollout advances for at most 16 plies, stopping earlier at a rule terminal
or available exact tablebase result.

At every non-terminal rollout ply:

1. if exactly one legal move exists, play it without search and leave that
   ply's reserved allocation unused;
2. otherwise search the position once with the frozen evaluator and search semantics,
   one thread, a fresh caller-owned TT, and exact cap `R / 128`;
3. rank legal moves by the final scores exposed by that call, breaking equal
   scores by ascending canonical move encoding;
4. choose uniformly between the first two ranked moves;
5. append the predecessor hash according to the existing history semantics.

Every per-ply call receives a fresh TT. No TT, mutable history buffer, RNG
object, or engine instance may be shared between rollout ordinals or with the
control/base search. Lazy SMP is prohibited.

The random seed is domain-separated from the tuple:

`(contract_version, sealed_run_id, canonical_case_id, color, canonical_root_move, rollout_ordinal, continuation_ply)`.

No scientific outcome or prior consumed seed enters this tuple. Repeated
execution with the same sealed identities must reproduce the same choices.

### Horizon score and aggregator

At a rule terminal or available exact tablebase state, use the engine's
canonical root-player terminal score. At the 16-ply horizon, use one invocation
of the same frozen evaluator's canonical root-player static score. No new
model, learned head, rescaling, clipping, or fitted coefficient is allowed.
Before implementation review can pass, a source-level test must establish that
these terminal and static values share the engine's documented ordering and
that arithmetic comparison is meaningful. Failure of that proof is terminal
for this contract.

For each root candidate, take the arithmetic mean of its two rollout scores.
Choose the candidate with the larger mean. An exact tie returns the higher
ranked candidate from the base search. There is no alternative horizon,
aggregation statistic, rollout count, candidate count, or fallback label.

## What is fixed a priori and what remains unproven

Fixed here without scientific outcomes:

- exact P4 predicate;
- two candidates and their deterministic ranking/tie rule;
- two rollouts per candidate;
- uniform top-two fixed policy;
- 16-ply horizon;
- arithmetic-mean aggregator and tie rule;
- exact-node unit, `R / 2` base allocation, and 64 allocations of `R / 128`;
- one thread, fresh TT per search call, seed-domain tuple, no reallocation;
- no model, label, threshold, or parameter selection from consumed campaigns.

Still unproven and therefore activation-blocking:

- a current public code identity implementing this exact definition;
- fixture PASS for disabled-path identity, isolation, determinism, candidate
  exposure, score ordering, and whole-ledger accounting;
- the absolute `R` inherited from a named current control;
- a genuinely new source and complete consumed-cohort exclusion union;
- the primary match endpoint, smallest effect of scientific interest,
  prospective alpha allocation, blind sample-size calculation, and resulting
  `N`;
- case availability and trigger frequency under the sealed source;
- final run IDs, evaluator identity, seeds, manifests, and readout identities.

Those unresolved fields must be set from control semantics, engineering facts,
source identities, or a target-blind statistical design. They may not be chosen
from LOCAL/WDL/HIER, D4/D4b/D4c, F6/E2, ED4/ED5, PL8, or any P4
candidate/control outcome.

## Prospective fresh-source strategy

No existing artifact is declared fresh by this decision. Before source
generation, a separate identity-only record must enumerate authoritative
manifests for every consumed discovery, selection, fit, panel, and confirmation
cohort relevant to D4/D4b/D4c, F6/E2, ED4/ED5 D, CLS LOCAL/WDL/HIER, and the
historical trajectory/RGSC/DSSD/Joint-TD families. It must construct one
complete exclusion union at both levels:

- canonical board plus side-to-move identity; and
- opening/game-family identity where that lineage exists.

If any required lineage lacks sufficient identities to prove exclusion, fresh
cases are unproven and the contract stops.

Only after that union and the experiment record are sealed may a newly
generated source be named. Its code/model identities, generation seed, ordered
selection algorithm, and source hash must be fixed prospectively. Selection is
the first `N` roots in generation order that satisfy the P4 predicate and both
exclusion levels; game result, evaluator score, future trajectory, and arm
outcome cannot filter or reorder cases. `N` comes only from the sealed blind
statistical design. A second readback must reproduce the selected identity
digest and zero overlap before any arm result is opened.

This strategy asserts neither that a suitable generator nor that enough cases
currently exist.

## Next executable action: one synthetic engineering pass

In a new worktree pinned from the then-current public code, implement only a
fixture-gated component and contract tests for the definition above. The test
positions must be generated in memory from fixed legal move sequences or
explicit test-only constructors; they are not scientific cases. A test-local
node constant divisible by 128 is allowed solely to exercise accounting and is
not the future scientific `R`.

The single pass must prove:

1. eligibility truth-table behavior for equal/unequal material, available/
   unavailable tablebase, terminal state, and fewer than two legal moves;
2. mechanism disabled gives the existing control move, score, node count, and
   stop reason byte-for-byte on frozen fixtures;
3. the base call alone supplies the two candidate scores and deterministic tie
   order;
4. every per-ply search uses one thread and a distinct fresh TT, and every RNG
   choice binds the complete declared seed tuple;
5. same inputs reproduce the complete manifest; changing only the rollout seed
   cannot alter control/base-search fields;
6. submitted caps sum to at most `R`, actual work equals the sum of returned
   counts, early-stop slack remains unused, and no hidden call escapes the
   ledger;
7. terminal and horizon scores obey one documented root-player ordering;
8. all required code/evaluator/config/fixture identities appear in the result
   manifest.

A PASS establishes engineering feasibility only. It does not admit source
generation or a scientific run.

## Finite stop and terminal

This contract permits exactly the synthetic engineering pass above and then one
identity-only fresh-source review. Any failure in the fixed mechanism,
score-order proof, current-control `R`, fixture obligations, complete exclusion
union, or fresh-case availability yields:

`P4_INTERNAL_ROOT_ROLLOUT_FEASIBILITY_NOT_ESTABLISHED_V1`

There is no automatic retry, alternate horizon, third candidate, extra rollout,
different policy, score transformation, relaxed exclusion, reused case, or
replacement source. If both passes succeed, the next artifact is a separately
sealed prospective scientific preregistration containing the remaining
statistical and immutable identities. Success still provides no automatic
compute, promotion, or scale-up.

## Evidence and provenance references

Source feasibility report:
`.codex-tmp/p4-internal-root-rollout-source-feasibility-20260921.md`, SHA-256
`f5b777d767e6531ec5d84016cffa68f874c032994f97977257a1700779e3a92b`.
Its source line numbers came from old root checkout
`19553c1cd3cdc2076788dc9fce7d54448ad9364b` and are not current-code pins.

Current-code correction:
`.codex-tmp/p4-source-feasibility-current-code-addendum-20260921.md`, SHA-256
`2a8684de09bbe51a02a06212e33bac2f9e4b189cf4216f69e4b0590b4b704f6e`.
It compares the same 15 paths with public-worktree commit
`c776ebddb2cad1b7e2c000da14ba98f285451bd5` (PR1065 merge
`ddcfbaadb2ca7e56f412267c671db5633a340181`) and confirms only the narrow
current interfaces, not this mechanism or its fixtures. No implementation may
pin the old checkout.

Historical P4 reservation:

- introduction commit `4e67610faec4ee3678038a99983ca6b2454bba17`;
- path `docs/PROJECT_RESULTS_PRE_T3_20260830.md`;
- current readback at public-worktree commit `c776ebddb2cad1b7e2c000da14ba98f285451bd5`,
  blob `8f7a1450ce9511f85ad0544241c9514e7469bbbb`;
- lines 791-792: "Comment traiter P4 matériel-égal sans oracle externe ? La
  piste réservée est / un ensemble de rollouts internes stochastiques.";
- lines 816-817: "Le rollout interne multi-échantillon pour P4 matériel-égal
  n'est pas encore / implémenté."

DSSD outside-v1 reference:

- introduction commit `d3a52800935fd39ad136240f040e3a6382b3417b`;
- path
  `docs/experiments/L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md`;
- current readback at public-worktree commit `c776ebddb2cad1b7e2c000da14ba98f285451bd5`,
  blob `9b10ae423747a2d0eda7b3d83d73616c301365a5`;
- lines 257-268, headed "Trajectory-outcome extension (not part of v1
  gate)"; lines 259-266 say a later preregistration may add fixed-policy,
  long-horizon rollouts and list terminal W/D/L, tablebase outcome, material,
  promotion, mobility/blockade, and H4/H8/H16/H32 outcomes; line 268 states
  that v1 instead tests expensive sibling reanalysis.

The prior all-ref inventory was run in the public evaluation worktree but did
not record `HEAD` in the same command, so this memo does not backfill a false
head identity. Its exact bounded commands/scopes were:

- all objects reachable from all **locally present refs** via
  `git rev-list --objects --all`, filtered case-insensitively for
  `rollout`, `material[-_]?equal`, `trajectory`, `rgsc`, `dssd`, or
  `joint[-_]?td` across returned paths;
- committed history reachable from those local refs since 2026-08-30 via
  `git log --all -G 'rollout|stochast'`, path-limited to `docs`, `jobs`, `src`,
  and `pattern_jass`;
- direct inspection of the matched reservation/DSSD commits and nearby
  trajectory implementations.

That inventory establishes a bounded collision check against the local ref
universe available at the time. It is not a remote-universe completeness
claim. The exact current readback head used for the references above is
`c776ebddb2cad1b7e2c000da14ba98f285451bd5`.
# P4 root-score contract — bounded clarification

Date: 2026-09-21  
Applies to:
`.codex-tmp/p4-internal-root-rollout-prospective-decision-20260921.md`,
SHA-256 `e2be4c03f8c7d0eeb553fa9b0b936ee0b1570d6d165a5aec033320eaa7880ce6`.

Status remains:
`P4_INTERNAL_ROOT_ROLLOUT_V1_PROSPECTIVE_CONTRACT_DEFINED__ACTIVATION_BLOCKED`.
This addendum performs no implementation, fixture, outcome read, compute, queue
admission, or activation.

## Source fact requiring clarification

The bounded read used public source commit
`ddcfbaadb2ca7e56f412267c671db5633a340181` in worktree
`.codex-worktrees/p4-internal-rollout-feasibility-20260921`.

`src/search.hpp:65-78` defines an action return as a fail-soft result against
its recorded `[alpha,beta]` window. `Exact`, `Lower`, and `Upper` are bounds;
`None` denotes interrupted work and its integer is diagnostic only.
`src/search.hpp:99-129` separately records the attempt, completeness, the full
root-action catalogue, and per-action traces. In `src/search.cpp:1787-1918`,
`cur_alpha` changes as root actions are searched, an action is classified
against its own window, a beta cutoff may leave actions unvisited, and
`all_actions_searched`/`completed` record different obligations.

Consequently, a complete root attempt does not by itself make every action's
integer an exact and mutually comparable value.

## Meaning of “two best final scores”

The original contract intended **two selected actions whose exact values and
top-two membership are certified by one already-budgeted search call**. It did
not intend raw fail-soft integers to become a policy statistic.

Treating `Lower`, `Upper`, or `None` as exact point estimates would be a new
mechanism variant. It is not authorized by this clarification. No auxiliary
ranking search, widened retry, extra node allowance, or re-search may be added.

## One admissible-attempt rule

Apply this identical rule to the treatment's `R / 2` base search and to every
non-forced `R / 128` continuation-ply search.

An attempt in that one call is **admissible** only if all conditions hold:

1. `attempt.completed == true`;
2. `attempt.all_actions_searched == true`;
3. `attempt.cutoff == false` and `attempt.bound == Exact`;
4. its action catalogue contains every semantic move in `root_actions` exactly
   once and contains no other move;
5. every action has `completed == true` and bound in `{Exact, Upper}`;
   `Lower` and `None` are inadmissible;
6. at least two actions have bound `Exact`;
7. sort exact actions by descending score, then ascending canonical move
   encoding; call the first two `c1` and `c2`;
8. every non-selected `Exact` action sorts no earlier than `c2` under that
   same ordering;
9. every `Upper` action has a recorded upper bound **strictly less** than
   `c2.score`.

The strict inequality in condition 9 is required because an upper bound equal
to `c2.score` does not reveal whether the action is truly tied; its canonical
tie position therefore cannot be certified.

Conditions 6-9 certify that `c1` and `c2` themselves are exact and that no
other action can displace either from the deterministic top two. An `Upper`
integer is used only as an upper-bound certificate below `c2`; it is never
averaged, ranked as an exact value, or returned as a rollout score.

Among admissible attempts already present in the call trace, use the one with
the greatest `(depth, attempt)` pair lexicographically: deepest depth first,
then last attempt at that depth. A later interrupted, cut-off, or otherwise
inadmissible depth is ignored; work it consumed remains charged. Actions and
bounds may not be combined across attempts or depths.

For the treatment base call, `c1` and `c2` are the two root candidates. For a
continuation-ply call, uniformly sample between that attempt's `c1` and `c2`
using the already fixed domain-separated stream. A forced one-legal-move state
still follows the original no-search rule and needs no catalogue proof.

## No-admissible-attempt behavior

If the `R / 2` base call contains no admissible attempt, candidate selection is
undefined. If any required `R / 128` call contains no admissible attempt, that
rollout policy step is undefined.

In either case:

- do not consume the raw fail-soft integers;
- do not use the public best move as a substitute for a certified pair;
- do not re-search, widen a window, change depth, add nodes, transfer unused
  allocations, skip/replace the case, or fall back to one candidate;
- record the complete call receipt and stop the P4 mechanism without a
  scientific verdict.

During the synthetic engineering pass this yields the already declared
terminal:

`P4_INTERNAL_ROOT_ROLLOUT_FEASIBILITY_NOT_ESTABLISHED_V1`

The current alpha-raised root-pass design may make two exact action values
unavailable even when the overall search completes. That is an acknowledged
feasibility limit of this fixed contract, not permission to reinterpret a
bound or introduce a second ranker.

## Fail-closed non-EGDB predicate

The original phrase “the exact tablebase interface reports that the root is
outside its resolved domain” means a positive **domain proof**, not a failed
probe.

The P4 root is non-EGDB only if an authenticated, pinned tablebase capability
or domain descriptor classifies the canonical root as outside the exact
domain. A disabled tablebase, missing files, unavailable backend, uninitialized
handle, I/O error, generic `no result`, or an interface that cannot distinguish
out-of-domain from operational failure does not satisfy the predicate.

If the reviewed implementation cannot provide that distinction, or if the
capability identity/domain descriptor is not pinned, P4 eligibility is
unproven and the same feasibility terminal applies. A root proven inside the
domain is simply ineligible, regardless of whether a runtime result happened
to be returned.

This clarifies the previously fixed `non-EGDB` condition; it does not expand
the case universe or replace the tablebase predicate with piece count alone.

## Effect on the next action

The single synthetic engineering pass remains the next action. Its candidate
and rollout-policy fixtures must exercise:

- one admissible exact-pair trace;
- rejection of `None` and `Lower`;
- rejection of an `Upper` bound at or above the second exact score;
- acceptance of an `Upper` bound strictly below it;
- rejection of incomplete catalogues, cutoffs, duplicates, and interrupted
  later depths without losing their work from the ledger;
- positive out-of-domain proof versus disabled/error/generic-unavailable
  tablebase states.

If current source cannot produce and expose the admissible exact-pair contract
within the existing caps and without an extra search, the finite investigation
ends at `P4_INTERNAL_ROOT_ROLLOUT_FEASIBILITY_NOT_ESTABLISHED_V1`.
