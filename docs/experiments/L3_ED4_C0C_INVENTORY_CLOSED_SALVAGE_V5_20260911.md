# ED4 C0C — inventory-closed salvage V5

Date: 2026-09-11. Status: preregistration before V5 execution.

## Objective

End the iterative malformed-JNNW repair loop without weakening fail-closed semantics. V5 consumes the completed exhaustive structural inventory from `cpx62-1922-l3-ed4-c0c-v4-full-malformed-inventory-v1`, attempt `20260911T181346Z-832b0339`, code `832b0339fe02cbf3b187377ff475a3ddd289e0d6`.

## Frozen rule

The 1922 artifact is used only as an authenticated exact-object allowlist. Every listed malformed object must satisfy all of: uncompressed `jnnw`; invalid reason `jnnw_trailing_bytes`; declared count zero; authenticated `job_id/attempt_id/path/SHA256/size`; at least one complete 38-byte record; incomplete tail length 1..37. If any listed row violates the class, V5 fails closed with `v5_new_malformed_class`.

For an allowed object, V5 re-authenticates the live C0A/C0B descriptor and downloaded bytes against the row's exact SHA256 and size, verifies `JNNW` magic and count zero, then recovers only the complete 38-byte prefix records. Only bytes `[0:33]` of each complete record are decoded as position identity. Bytes `[33:38]` are never decoded or interpreted. The incomplete tail is discarded.

Any malformed candidate encountered by C0C that is absent from the exhaustive 1922 allowlist fails closed with `v5_malformed_not_in_inventory`. At terminal, every allowlisted malformed object must have been encountered exactly once; otherwise `v5_inventory_universe_mismatch`.

## Scientific quarantine

No confirmation target, WDL, qvalue, score, model value, teacher call, search, fit, game, alpha spend, candidate-byte change, threshold change or verdict-gate change is authorized. This is a mechanical source-recovery repair only. V5 does not authorize promotion or bake.

## Terminal

Success terminal: `ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V5_INVENTORY_CLOSED`. A success means the exclusion union is complete under the frozen C0A/C0B universe and the exhaustive 1922 malformed inventory, with all malformed interrupted-writer objects handled in one pass.
