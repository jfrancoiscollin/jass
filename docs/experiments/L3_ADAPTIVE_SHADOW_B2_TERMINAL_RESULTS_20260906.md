# L3 adaptive shadow B2 — terminal results

Date : 2026-09-06

Statut : **TERMINAL CONFIRMATORY RESULT**.

## Terminal

```text
job      cpx62-1831-l3-decision-math-b2-statistical-completion-legacy-support-json-compat-v3
attempt  20260906T105358Z-bebadf91
code     bebadf919c25ec295bc41950de8c8fa995e2b574
exit     0
verdict  B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1
```

Scientific implementation remained frozen at:

```text
X = d3657332c3a5609a5501a9ff130f5d5c19488c7f
Y = b382cd4b1d8b9b632bcaf500156a6e827e114527
policy M5/M50/minimum_survivors = 100 / 60 / 2
bootstrap replications = 200000
bootstrap seed = 2026110717
```

## Authenticated terminal facts

- `state=completed`;
- `statistics.status=VALID`;
- `scientific_gates_evaluated=true`;
- `all_gates_passed=true`;
- `bootstrap_replications=200000`;
- `bootstrap_seed=2026110717`;
- statistical elapsed time `518.249262 s`;
- support/authentication/teacher/projection/rich-ledger/sufficient-projection all valid;
- `projection_receipts_changed=0`;
- no new teacher searches, fresh data reads, fits, strength games, promotion or bake in the recovery/readout completion;
- `automatic_downstream_jobs=0`;
- `b3_authorized=false` in the terminal publisher because the B2 preregistration required STOP after B2.

## Exact-zero-cost compatibility

The terminal authenticated six selected parents whose complete historical full-search node total is zero because their legal siblings are already exact:

```text
1216, 1544, 1614, 3510, 3526, 3924
```

For all six:

- `full_nodes=0` implies `shadow_nodes=0`;
- none is `fully_nonexact`;
- the parent remains in its original fixed 500-parent cell;
- all aggregate cell/global support denominators remain valid;
- the frozen projection receipts are unchanged.

This is a producer/consumer compatibility fact, not a scientific retuning.

## Interpretation

B2 supplies the prospective, target-blind confirmation required by the Decision Information plan before implementing a real adaptive sibling teacher. The fixed B1 policy has now cleared all preregistered global and cell-level confirmation gates on the fresh 4,000-parent B2 cohort.

Therefore the next scientific/engineering step may be **B3 real adaptive teacher**, under a new explicit B3 contract. B2 does not itself authorize promotion, baking, model changes, training changes or an automatic B3 job.

## B3 boundary

B3-v1 must preserve the confirmed policy as a one-factor implementation test:

```text
M5 = 100
M50 = 60
minimum_survivors = 2
budgets = 5000 -> 50000 -> 200000 exact nodes
```

The first real-teacher implementation should replay the already-consumed B2 parents only as a technical/causal implementation-parity gate before any fresh B3 corpus. Passive `SearchDecisionTrace` evidence may be recorded, but must not alter B3-v1 allocation. A later bounds-aware allocation is a separate candidate and requires a separate preregistration.
