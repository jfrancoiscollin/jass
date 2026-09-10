# ED4 C0C V3 — exact two-object interrupted-JNNW recovery

Date: 2026-09-10. Status: prospective before additional position decoding.

## Decision

After diagnostic 1911 identified `sp1-2.jnnw` as a second malformed object from the exact same producer 1785 / attempt 20260905T145718Z-d3657332 / historical job 0206 context as the previously authorized `sp1-1.jnnw`, extend recovery prospectively to this second exact authenticated object only. V1 and V2 remain immutable historical protocols.

## Frozen parent and candidate universe

Keep the same 726-candidate C0B set, order and parent `cpx62-1897-l3-ed4-c0b-structural-payload-freeze-v2`, attempt `20260909T210053Z-a3efc988`. Keep all ED4 candidate bytes, thresholds, alpha and confirmation corpus unchanged.

## Exact authorized objects

Both objects must match job `cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1`, attempt `20260905T145718Z-d3657332`, kind `jnnw`, magic `JNNW`, zero little-endian count placeholder, total size 114914 bytes, and body shape 3023 complete 38-byte records plus exactly 32 incomplete bytes.

1. `b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw`
   SHA256 `730ee719a651e371c782afd1c1f29a4a95a2c81b2bfdf7f9748aab4d6d7cd576`
2. `b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-2.jnnw`
   SHA256 `7e1fbd21836db9bb090006b408bb1fb6cecf6ab778baf3c8182a24a18a3fbb4f`

For each complete record decode only bytes 0:33 using unchanged V1 board+STM canonicalization. Bytes 33:38 remain uninterpreted. Discard only the final 32-byte incomplete fragment. No padding, reconstruction, regeneration, resynchronization or generalized salvage is allowed. Every other malformed JNNW fails closed under V1 semantics.

## Acceptance

READY requires exactly two salvaged files, exactly 6046 complete recovered records in total, exactly 64 discarded partial bytes in total, successful authentication of all candidate descriptors/bytes, and a nonempty sorted unique exclusion union. Terminal token: `ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V3`.

No confirmation corpus is selected or consumed; target/WDL/qvalue/model reads remain zero; fits/games/search/teacher calls remain zero; alpha spent remains zero; promotion and bake remain unauthorized. `confirmation_authorized=false` and `automatic_continuation=false`.

A further malformed candidate is not covered by this decision and must fail closed and be reported.
