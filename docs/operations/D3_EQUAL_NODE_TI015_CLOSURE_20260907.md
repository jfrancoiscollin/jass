# TI-015 closure — D3 runtime equal-node

Technical attempt `cpx62-1856-l3-decision-math-d3-runtime-equal-node-v1` failed before scientific execution because its preregistration guard searched for the non-existent literal `20,000`.

The plumbing-only repair in PR #848 added an exact fail-closed recovery assertion without changing the frozen D3 science. Immutable rerun `cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1`, attempt `20260907T155344Z-fcdcd217`, completed with exit code 0 and authenticated outputs.

The rerun executed the full frozen equal-node gate: 1700 games, 0 fits, 0 promotions and 0 bakes. Its terminal scientific verdict was `D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1`. This scientific negative result is distinct from TI-015 and constitutes terminal proof that the technical repair itself worked.
