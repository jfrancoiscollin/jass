# DSSD v1 selection implementation note

This note is implementation-only and does not change `L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md`.

Before any generalized teacher score is read, the direct-R2 selection stage is implemented as follows:

- direct candidate filtering and byte-payload de-dup reuse `tb_frontier_catalog_mine.py`;
- `source_payload_identity` is the already-existing deterministic payload key: `sha256:<declared_sha256>` when a declared SHA is available, otherwise `uri:<r2_uri>`;
- source bucket is exactly `u64_le(SHA256("2026083102:" + source_payload_identity)[0:8]) % 5`;
- the C++ filter reads only JNNW board bitboards + STM; source score/WDL bytes are not read and are zeroed in retained rows;
- eligible parents are 9–40 pieces with 2–16 distinct semantic legal decisions;
- exact + rotate180/colour-swap de-dup uses the already-tested `tb_frontier_symmetry_dedup.py` canonical fingerprint;
- if a canonical parent appears in both source partitions, holdout wins and a deterministic holdout occurrence represents the selected parent;
- phase sampling is exactly SHA256(`2026083101:` + canonical fingerprint), first 2,000 in each frozen P0..P3 phase;
- SQLite is only a memory-bounded implementation detail; no score, WDL, model error, teacher result, or outcome enters the selection database.

The stage emits a zero-target counted JNNW of selected parents plus provenance and a machine-readable receipt. Stable-pair support remains deferred to the preregistered 50k/200k teacher stage.
