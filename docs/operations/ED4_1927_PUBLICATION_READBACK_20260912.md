# ED4 C0C 1927 — publication and readback verification

Date: 2026-09-12. Classification: **TECHNICAL / PUBLICATION READBACK**.

The unchanged queued job `cpx62-1927-l3-ed4-c0c-v5-inventory-class-readout-v1`
ran on CPX62 at attempt `20260912T111000Z-26d79792`, using code
`26d79792d207018982f482bbb8a96520a845c659`. It completed with exit 0. The
result URI is
`r2:jass-data/runs/cpx62-1927-l3-ed4-c0c-v5-inventory-class-readout-v1/20260912T111000Z-26d79792`.

The user explicitly authorized the previously review-blocked readback. The
five published artifacts were fetched and reread successfully: `_SUCCESS`,
the manifest, inventory, and checksums verified, and receipt output hashes
matched the reread bytes. The pinned stage spec SHA256 is
`169273ff8c048b882f8a6fae7dfc847cd275d4b4634b26836f60f1923410f432`.

| Artifact | SHA256 | Bytes |
|---|---|---:|
| `launch-receipt.json` | `1c7b22cdb3e440646a6e755684d156ba81596d7a263b5e3f7138a7dc1eb0d349` | 1302 |
| `execution-evidence.json` | `5a0fce42c1d80c1182d9586b2f09a90e637fe1a4dcdb84d1d5bf9f928496aa92` | 527 |
| `launch-regressions.json` | `9754f75d704be5e1bd081c29bba054300699407f6e7210a4d42810a00997557f` | 229 |
| `ed4-c0c-v5-inventory-class-readout.json` | `e93bb11a3783077955bc2393ca55e219be8e93df92260c42c35484684d4135e1` | 9083 |
| `scientific-summary.json` | `6f675687b61209499b365f0909c12cf2d453bb4748f9b532533bdbf8ffa0aded` | 9387 |

Mode was rehearsal, with verdict `REHEARSAL_EXECUTION_COMPLETE_V2`. The three
phases authenticated inventory, classified structural rows only, and
published the class readout. Thirteen generic-gate and pipeline regressions
completed with zero errors, failures, or skips. All side-effect counters were
zero. Record fields, position identities, targets, WDL and Q values were not
decoded; alpha spent was zero. `scientific_verdict` is null and
`confirmation_authorized` is false.

The readout recorded 231 malformed and 216 interrupted-writer-shape rows. All
15 remaining `jnnw` / `jnnw_trailing_bytes` rows had count 0 and tail 0; two were 73880
bytes with 1944 complete records and thirteen were 82088 bytes with 2160
complete records. This is a publication verification record and makes no
scientific gain or new exclusion-union claim. Raw verified copies and
`verification-report.json` remain at
`/var/tmp/ed4-1927-publication-readback-20260912` on CPX62.

The same authenticated 1927 outer inventory binds its saved source file
`inventory/inventory.json` to SHA256
`1e8ebc5ee1c5614390c950e903377a6c3664b8d0c2a08f21c0295b2066f4d599`,
171848 bytes. These are the 1922 inventory bytes consumed by 1927.
Only this descriptor was read for the additional provenance check.
