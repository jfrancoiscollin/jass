# ED4 C0C V6 — authenticated freeze and remaining admission

Date: 2026-09-12. Authenticated metadata freeze complete; no V6 real-data execution.

The [1927 readback](ED4_1927_PUBLICATION_READBACK_20260912.md) is complete and
merged in Jass PR #929. It identifies 15 aligned count-zero objects outside
V5's permitted partial-tail class. A Sol protocol review authorized preparation
of a new immutable V6 under the existing autonomous campaign mandate; Terra
implements it with root review. Luna handled the bounded 1927 incident work.
The [V6 protocol](../experiments/L3_ED4_C0C_STRUCTURAL_RECOVERY_V6_20260912.md)
has its exact canonical allowlist digests frozen below. Runtime sizing remains
the sole outstanding admission item.

## Authenticated freeze

The authorized CPX62 readback of the 1927 inventory and class readout completed
with exit 0. The exact canonical row-set pins are:

- Full 231-row allowlist: `f56fda00c0ce815eaeac924ede0ce78840bed60f68360b57de9b801fb8885f95`.
- Aligned 15-row subset: `7721b29bcbb65a0dc070def901bdb03b9738ca399bf146d2a5a156338dd4fb47`.

The earlier approval review rejection below was resolved by the user's explicit
authorization for the V6 R2→CPX62 reads and the subsequent authenticated freeze.

## Authenticated metadata read

The additional metadata object required to calculate the two canonical row-set
digests was explicitly authorized and successfully read back, alongside the
already authenticated class readout.

- Producer: `cpx62-1927-l3-ed4-c0c-v5-inventory-class-readout-v1`.
- Attempt: `20260912T111000Z-26d79792`.
- Result-relative object: `inventory/inventory.json`.
- Bytes: `171848`.
- SHA256: `1e8ebc5ee1c5614390c950e903377a6c3664b8d0c2a08f21c0295b2066f4d599`.
- Intended destination on the producing CPX62 host:
  `/var/tmp/ed4-1927-publication-readback-20260912/source-inventory.json`.

Its descriptor is authenticated in the 1927 result inventory. Automatic
approval review initially rejected the additional payload fetch because the
previous explicit permission named only five other files. That historical
rejection was resolved by explicit authorization for all V6 R2→CPX62 reads;
the authenticated fetch and canonical freeze then completed.

The completed freeze step verifies this object's exact digest and length,
its zero-read counters, the 231/216/15 partition, and exact equality of the
aligned subset with the already verified 1927 readout. It then hashes the
canonical full and aligned row lists. No position or target record is decoded.
The digest placeholders have now been replaced by the frozen pins above. The
runtime cap remains unset, so the stage still fails closed before launch.

## Runtime evidence and limits

CPX62 reports 16 available CPUs. A single-process synthetic probe of the
existing V1 canonical decoder processed 50,000 33-byte records in
0.5540532729996812 seconds (90,244.02965674525 records/second). Each synthetic
row occupied all 50 squares across disjoint bitboards. No real source artifact,
target, teacher, search, fit or game was accessed.

This measures decoder work only, excluding transport, decompression, descriptor
verification, hash-set growth, sorting, regressions and publication. The old
1922 JNNW-envelope scan took 30m44s on CPX62. These observations do not establish
a full V6 runtime. The runtime cap remains unset, so the stage cannot launch.
A bounded target-free sizing/rehearsal and publication reserve must establish
the campaign's maximum 2700-second job duration before real V6 admission.

## Completed local validation

The exact registered five-suite profile passed **49 tests**, zero failures,
errors or skips, under Linux on the LF-preserving archive of source commit
`41089b4ec8409694bb8c0f986ea1d35c6caaba6e`. This includes the generic
stage/publisher/readback fixture and the V1/V2/V6 boundary suites. The
[regression report](ED4_C0C_V6_LOCAL_REGRESSIONS_20260912.json) has SHA256
`323039f7917b71a7754738f6e986418fbe53d5163aa2fea8b7e3d13f72c62d95`.
The profile contract, compilation and whitespace checks also passed.

The V6 tests perform two complete synthetic 231-object union builds with
identical output bytes. They exercise malformed and unlisted objects,
missing/duplicate encounters, real invalid position bytes, metadata identity
and counter guards, unchanged V5 rejection of aligned count-zero files, and
phase evidence on failure. Earlier Windows-only generic runtime fixture
failures were resolved by executing the unmodified suite in Linux.
These are synthetic technical checks, not a real-data rehearsal or timing proof.

No model, held-out cohort, scientific threshold or alpha allocation changes.
No scientific gain, completed exclusion union, confirmation, scale-up,
promotion or bake is claimed.
