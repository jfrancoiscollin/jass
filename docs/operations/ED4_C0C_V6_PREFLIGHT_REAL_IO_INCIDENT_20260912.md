# ED4 C0C V6 preflight real-I/O incident

The rehearsal attempt `20260912T121834Z-365f1d00` was stopped and published failed with exit 143. Its code was `365f1d00a129d959253815d690d28eec63f1c98e`.

Cause: the local no-sizing test called the V6 stage without patching its now-configured runtime cap. On CPX62 this entered the real candidate transport path; the test was intended to establish only the fail-closed no-cap guard.

Mitigation: the test now explicitly sets `RUNTIME_MAX_SECONDS=None`, replaces `build_union_v6` with a raising spy, asserts the exact `v6_runtime_sizing_pending` failure, and asserts zero builder calls. This preserves the V6 parser, pins, runtime cap, profile, and scientific contract. A fresh rehearsal is required under a new code SHA.

Authenticated failure readback established exit 143 and reread the following three technical files: regression log SHA256 `08b2b199b711b0b0a20e38beabf00433162268ce225f55648c40081620fedf10` (9250 bytes), metadata SHA256 `032bf951123cdd56b00122bb00e651e253352ba917a7295fdf50a3789d87bd75` (652 bytes), and runner-launch SHA256 `1d9c4fef68f39b3e0e8c62a8edd849eea96e23d0c2d22fe93f54b96f48de78ef` (704 bytes). No stage receipt, execution evidence, or launch receipt was published. The stopped attempt had 136 temporary files totaling 276979640 bytes. Position reads were not measured; this document makes no zero-read claim. Scientific confirmation did not start; classification remains technical.
