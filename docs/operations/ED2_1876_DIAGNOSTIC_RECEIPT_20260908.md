# ED2 1876 diagnosis and independent publication-cleanup proof

2026-09-08. Read-only bookkeeping in the user's diagnostic/repair/relaunch task.

Source: `jass-control/status/cpx62-1877-l3-ed2-1876-failure-diagnostic-v1.json`,
attempt `20260908T185207Z-e7b9320a`, completed exit 0 at 18:57:13Z.
This diagnostic authenticated failed 1876 / 20260908T182614Z-27c30b3f, its
manifest/inventory/checksums and selected original artifacts.

## Numerical incident (TI-022)

The exact POINT error is `STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT`.
Its training labels remain sealed, with no published model or TEST data.
N1 repair PR #875 is merged as d71679e96d78609b6d32052be80ca78c0deaece0;
control #575 queues 1878 on that immutable code. TI-022 remains MITIGATED,
not CLOSED: CI and synthetic numerical tests are not CPX terminal proof.
The original scientific question still has no terminal learning verdict.

## Publication incident (TI-021) — terminal cleanup proof

The authenticated `scratch-cleanup.json` from 1876 reports:

- removed reproducible source scratch: 39,703 files / 948,400,007 bytes;
- removed build scratch: 300 files / 8,114,078 bytes;
- scientific artifacts modified: false;
- inputs and other work files preserved: true;
- retained native probe: 76,704 bytes, SHA256
  b6f5ce3beceba1e121286ab3662447c53f2f7f062d5c6e023461dec2cfddc1f4;
- archived probe SHA256:
  dc7ac01724b4fd6a15a02f1202ae5265b28867dab2432cbb5200fb6a90acf2c3.

The failed fit and successful narrow publication cleanup are separate facts.
This closes TI-021's remaining cleanup-proof requirement. It does not establish
that excessive scratch publication caused all of P0 1875's earlier elapsed time.
No new searches/fits, changed scientific artifacts, changed thresholds, altered
historical terminal verdict, promotion or bake is introduced by this document.
