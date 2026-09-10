# ED4 C0C V2 — exact authorized complete-record recovery

Date: 2026-09-10. Status: **prospective before additional record decoding**.

## Decision and precedence

JFC explicitly requested recovery of the 3023 complete records, then authorized
completion/merge/launch of PR #913 with "Allez go". This V2 records that narrow
protocol decision. It is not a retroactive technical reinterpretation of V1.
The V1 preregistration, implementation, failed attempts and diagnostic 1909 are
unchanged. The historical blocker document merged by #912 remains intact.

## Frozen inputs and exact exception

Keep the complete 726-candidate C0B set and its order. Parent remains
`cpx62-1897-l3-ed4-c0b-structural-payload-freeze-v2`, attempt
`20260909T210053Z-a3efc988`, code `a3efc988d8ff0b5642ab65fa0bf133897ee2f54c`.
The sealed parent artifact hashes remain:

```text
C0A 0af828dbc84b7103ad2aa54196c2ca18f81b3afab01b4daa6e256ffd87ecb219
C0B c04c5ad0a3c6b98d6d3c86575f1ba5607cdad17e92ae5b1ed4108aeb81274bda
```

The only permitted recovery is the object localized by diagnostic 1909
(`20260910T162746Z-35f0fd1b`). All these predicates must hold together:

```text
job     cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1
attempt 20260905T145718Z-d3657332
path    b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw
kind    jnnw
SHA256  730ee719a651e371c782afd1c1f29a4a95a2c81b2bfdf7f9748aab4d6d7cd576
size    114914 bytes
magic   JNNW
count   0 (little-endian u32 placeholder)
body    3023 complete records of 38 bytes, followed by exactly 32 bytes
```

Authenticate runner identity, inventory, checksum and actual downloaded bytes
before accepting the exception. Decode only offsets 0:33 of each complete
38-byte record using the unchanged V1 board+STM canonicalization. Offsets 33:38
remain uninterpreted. Discard only the final incomplete 32-byte fragment: no
padding, invented STM, repaired source object or regenerated data. The recovered
3023 records need not represent 3023 unique canonical positions.

Every nonmatching candidate uses the unchanged V1 rules. No general salvage,
resynchronization, documentary-worktree exclusion, replacement source, skipped
nonempty file or second malformed-object exception is authorized. Authenticated
zero-size candidates retain the existing zero-identity treatment. If another
candidate is malformed, fail closed and report the blocker; do not broaden V2.

## Outputs and acceptance

Produce the same sorted unique ASCII exclusion-union output and its manifest,
with schema `jass.ed4.c0c_structural_exclusion_union.v2` and terminal token
`ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V2` only after every candidate finishes.
Require exactly one recovered file, 3023 recovered complete records, 32 discarded
partial bytes and a nonempty union. Include per-file recovery provenance and
union hash. A partial union cannot be published as READY.

No confirmation corpus is selected or consumed. No targets, scores, WDL,
q-values, model bytes, teacher/search calls, fits, games, alpha, promotion or bake
are authorized. Preserve the sealed ED4 candidate and all thresholds/gates.
`confirmation_authorized=false` and `automatic_continuation=false` remain in
this stage's output: an exclusion union alone does not authorize confirmation.

## Execution and regression requirements

Use the registered V2 profile and canonical nine-line control dispatcher with
raw file SHA256 pins for code/spec/admission/profile. Start with a bounded
CPX62 rehearsal of this read-only stage. A production admission, if subsequently
required, must authenticate the same-code target-host rehearsal and published
outputs; this document does not waive that gate. Keep the existing resource and
timeout bounds. Allocate a new immutable job ID; never replay historic IDs.

Run existing admission and V1 regressions plus V2 cases covering exact identity,
actual hash/size, zero count and 3023+32 shape, structural-only decoder input,
target/tail invariance on synthetic fixtures, strict handling of every mismatch,
missing recovery, and direct-path startup without PYTHONPATH. Synthetic object
hash substitutions are test-only and must never affect the literal runtime pin.

Keep TI-043 MITIGATED pending authenticated terminal evidence; do not close it on
CI success alone. The next scientific decision remains outside this recovery.
