# ED4 C0C full format diagnostic V1

Date: 2026-09-12. Classification: `TECHNICAL_FORMAT_DIAGNOSTIC_ONLY`.

This prospective, bounded rehearsal diagnoses the complete frozen C0C descriptor
universe after V6 structural recovery stopped on a comment-only FEN input. It makes no
scientific decision and does not change V1--V6, the frozen parent descriptors,
their ordering, the six authenticated zero-byte objects, or the fixed V5/V6
recovery partition.

The stage authenticates all 726 descriptors and accounts for each exactly once,
including the six frozen zero-byte objects and the unchanged 231-row recovery
partition (216 V5 partial rows and 15 V6 aligned rows). It
uses the existing strict V1 parser for every nonempty descriptor outside the
fixed recovery rows. The exact recovery rows retain their existing V5 partial
and V6 aligned rules. A known per-descriptor parser error is normalized to its
stable error code and classification continues; authentication drift, an
unexpected exception, duplicate/missing/extra descriptor, recovery-partition
drift, or a deadline breach fails the entire stage closed.

The sole publication is a deterministic sorted classification with authenticated
descriptor identity, parser kind, byte/row geometry, outcome, and a canonical
digest of the complete failure-row list. Text geometry is limited to UTF-8
validity and physical, blank, comment, and post-V1-comment-stripping payload
line counts. The stage publishes no raw text, comments, positions, identities,
targets, scores, exclusion union, readiness signal, or scientific conclusion.

The fixed stage ceiling is 2100 seconds inside the existing 2700-second outer
budget. The first execution is a bounded same-code rehearsal only. Its terminal
state is technical; it cannot authorize confirmation, alpha expenditure, model
or teacher work, search, fitting, or games.
