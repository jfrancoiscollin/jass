# TI-016 closure — D3 runtime terminal autopsy

Technical attempt `cpx62-1858-l3-decision-math-d3-runtime-terminal-autopsy-v1` failed before any scientific readout because the consumer generated shard ids `s0..s7` instead of the sealed producer directories `s00..s07`.

The plumbing-only repair in PR #851 replaced width-sensitive shard generation with the exact immutable shard ids and added regression coverage without changing the D3 autopsy science.

Immutable recovery `cpx62-1860-l3-decision-math-d3-runtime-terminal-autopsy-recovery-requeue-v1`, attempt `20260907T164613Z-0beb8796`, completed with exit code 0 and authenticated outputs. It produced terminal diagnostic verdict `D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1`, classification `BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION`, with 0 games, 0 searches, 0 fits, 0 promotions and 0 bakes.

This terminal recovery is the no-recurrence proof for TI-016. The scientific D3 negative remains distinct from the technical incident; D3 stays closed.
