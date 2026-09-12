# ED4 C0C exact-linkage diagnostic v1

This rehearsal-only technical diagnostic consumes a private, hash-pinned
21-row manifest. It cannot run without that manifest, and validates it before
any source payload transport. Its purpose is to prove structural linkage for
only the named descriptor rows; it does not construct or publish an exclusion
union, identities, targets, scores, labels, models, or confirmation inputs.

Each TSV is parsed as unquoted tab-separated bytes. The header and only the
manifest-allowed structural columns are decoded. All other cells remain opaque
bytes. Row indices, contiguous parent blocks, parent ranges, sibling identities,
companion SHA256 values, exact JNNW geometry, and source-specific raw/canonical
fingerprints are fail-closed checks. JNNW readers inspect only bytes `0:33` of
each record and never decode bytes `33:38`.

The three malformed-STM aliases remain `unresolved-fail-closed` absent a
complete authenticated reconstruction or covering-source proof. A blocked
technical terminal is a successful execution of this diagnostic, not recovery
and not authorization for V7, a C0C union, confirmation, alpha spending, model
work, search, fitting, games, promotion, or baking.

The stage limit is fixed at 2,100 seconds and attempt-start to published
completion is fixed at 2,700 seconds. Its 21 rows are exactly three
comment-only FEN aliases, fifteen TSV aliases across four source-specific
schemas, and three invalid-STM JNNW aliases. The schemas have, respectively,
43 columns and 4,000/15,937 parent/child rows; 29 columns and 2,000/18,400;
9 columns and 784/7,556; and 9 columns and 784/7,288. Their allowed fields
are frozen in the private manifest: B2 reads row index, parent id, raw parent
fingerprint and parent STM; Home adds sibling identity plus parent and child
raw/canonical fingerprints; ED2 reads row index, sibling identity, child raw
fingerprint, parent id and parent STM.

The evidence table contains only the approved tokens
`exact-comment-only-empty-set-proven`, `exact-tsv-child-linkage-proven`, and
`unresolved-fail-closed`. All 21 complete exact proofs would map only to
`ED4_C0C_V7_EXACT_RECOVERY_PREREGISTRABLE`; any unresolved row, hash/schema or
linkage drift, forbidden read, provenance ambiguity, missing edge coverage or
deadline breach maps to `ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE`.
Payload analysis may be deduplicated by SHA only after every alias is separately
authenticated and accounted. The ledger reports hashed transport bytes, headers
read, allowed structural fields read, identity prefixes read and validated, and
forbidden fields read. The frozen 726 partition, including 216 V5 rows, 15 V6
rows and six zero-byte objects, is preserved. Invalid STM recovery requires a
complete authenticated reconstruction or covering source; alternate framing,
interior-only recovery and inferred shard boundaries are prohibited.
