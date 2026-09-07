# TI-016 — D3 runtime autopsy shard padding incident (1858)

## Classification

`TECHNICAL` only. No scientific verdict was produced by the failed attempt.

## Failed attempt

- job: `cpx62-1858-l3-decision-math-d3-runtime-terminal-autopsy-v1`
- attempt: `20260907T162007Z-e42764d6`
- source D3 equal-node run remained immutable: `cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1`
- scientific side effects before failure: 0 games, 0 searches, 0 fits, 0 promotions, 0 bakes

## Root cause

The read-only autopsy stage had to fetch sealed shard directories named exactly `s00` through `s07`. Its shell loop used:

```bash
seq -w 0 7
```

For the requested range this emitted `0` through `7`, so the constructed R2 paths were `shards/s0/...` through `shards/s7/...`, while the producer contract exposes `shards/s00/...` through `shards/s07/...`.

The failure occurred in input plumbing before the autopsy consumed the scientific JSONL rows. It is therefore invalid as scientific evidence and cannot alter D3's already-terminal `D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1` result.

## Durable invariant

Consumers of a sealed sharded publication must use the producer's exact shard identifiers, not regenerate identifiers via width-sensitive shell formatting. For this contract the only admissible identifiers are the literal list:

`00 01 02 03 04 05 06 07`

Both the source-fetch loop and the local-analysis argument loop use that literal list.

## Regression coverage

`jobs/tests/test_d3_runtime_terminal_autopsy.py` now asserts:

- both stage loops use exactly `00 01 02 03 04 05 06 07`;
- the unsafe `seq -w 0 7` construction is absent;
- the autopsy remains diagnostic-only with zero scientific side effects and no equal-time authorization.

## Recovery rule

The repair changes only plumbing. The preregistered D3 terminal-autopsy question, source attempt, diagnostics and D4-only next-stage authority are unchanged. Recovery must use a new immutable CPX job ID.
