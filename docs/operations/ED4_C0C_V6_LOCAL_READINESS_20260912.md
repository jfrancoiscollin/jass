# ED4 C0C V6 — local preparation and remaining admission

Date: 2026-09-12. Technical preparation only; no V6 real-data execution.

The [1927 readback](ED4_1927_PUBLICATION_READBACK_20260912.md) is complete and
merged in Jass PR #929. It identifies 15 aligned count-zero objects outside
V5's permitted partial-tail class. A Sol protocol review authorized preparation
of a new immutable V6 under the existing autonomous campaign mandate; Terra
implements it with root review. Luna handled the bounded 1927 incident work.
The [V6 protocol](../experiments/L3_ED4_C0C_STRUCTURAL_RECOVERY_V6_20260912.md)
remains incomplete until exact canonical allowlist digests and sizing are frozen.

## Pending metadata read

Only the additional metadata object below is needed to calculate the two
canonical row-set digests. The original five 1927 outputs have already been
explicitly authorized and successfully read back.

- Producer: `cpx62-1927-l3-ed4-c0c-v5-inventory-class-readout-v1`.
- Attempt: `20260912T111000Z-26d79792`.
- Result-relative object: `inventory/inventory.json`.
- Bytes: `171848`.
- SHA256: `1e8ebc5ee1c5614390c950e903377a6c3664b8d0c2a08f21c0295b2066f4d599`.
- Intended destination on the producing CPX62 host:
  `/var/tmp/ed4-1927-publication-readback-20260912/source-inventory.json`.

Its descriptor is authenticated in the 1927 result inventory. Automatic
approval review rejected the additional payload fetch because the previous
explicit permission named only five other files. The fetch did not run.
No alternative transport or indirect read has been attempted.

The prepared freeze step verifies this object's exact digest and length,
its zero-read counters, the 231/216/15 partition, and exact equality of the
aligned subset with the already verified 1927 readout. It then hashes the
canonical full and aligned row lists. No position or target record is decoded.
V6 retains non-digest placeholders until this step succeeds; these fail closed.

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

No model, held-out cohort, scientific threshold or alpha allocation changes.
No scientific gain, completed exclusion union, confirmation, scale-up,
promotion or bake is claimed.
