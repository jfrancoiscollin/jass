# B2 exact-zero-cost compatibility after 1827

Date: 2026-09-06

## Incident

Target-data admissibility job
`cpx62-1827-l3-decision-math-b2-recovery-admissibility-preflight-v1`, attempt
`20260906T084808Z-b93d6180`, completed exit 0 and correctly BLOCKED the full B2
statistics before bootstrap.  The first real-data divergence was parent 1216:

```text
classification = PRODUCER_CONSUMER_CONTRACT_MISMATCH
failure_class  = PROJECTION_BINDING_INVALID
failure_stage  = PROJECTION_RECEIPT
message        = full total must be positive
stored receipt == fresh deterministic X receipt byte-for-byte
```

The producer was not stale or corrupt.  The full teacher had executed the frozen
5k/50k/200k searches, but a terminal/TB-exact child may consume zero search
nodes.  A parent whose legal siblings are all independently exact can therefore
legitimately have `full_nodes == shadow_nodes == 0`.

## Normative boundary

The final frozen confirmation preregistration requires full/shadow **aggregate
observations per cell** to be non-zero.  The X statistical preflight helper also
had an over-strict per-parent parser constraint `full_nodes >= 1`.  Repairing the
parser globally or changing the frozen X files would obscure provenance.

The recovery therefore uses a narrow runtime compatibility layer while proving
that the frozen X files remain byte-unchanged:

- only readout sums labelled exactly `full total` may be zero;
- only statistical fields labelled exactly `full_nodes` lower the parser bound
  from 1 to 0;
- `full_nodes == 0` is valid only when `shadow_nodes == 0`;
- the parent remains in its preregistered 500-parent cell;
- all cell/global support checks, bootstrap denominators, estimands, thresholds,
  multiplicity, R=200000 and seed=2026110717 remain unchanged;
- no projection receipt, policy decision, q200 barrier counter, cohort member,
  teacher observation, model, fit, strength game, promotion or bake is changed.

## Architecture rule

Before any further full B2 statistical completion:

1. CI compatibility contract must pass.
2. The target-data admissibility preflight must replay all 4,000 parents and
   publish `B2_RECOVERY_ADMISSIBILITY_PASS`.
3. Only then may the full recovery execute the frozen statistical kernel.

A preflight BLOCKED outcome is technical/contract evidence and never a negative
B2 scientific verdict.
