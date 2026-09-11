# ED4 C0C V4 next-failure diagnostic V1

Date: 2026-09-11. Status: preregistered, structural-only, DIAGNOSTIC_ONLY.

Purpose: after technical failure of `cpx62-1914-l3-ed4-c0c-v4-class-structural-exclusion-union-v1`, locate the first malformed JNNW not handled by the already-preregistered V4 interrupted-writer class.

The diagnostic authenticates frozen C0A/C0B inventories, downloads candidate JNNW/JNNW.GZ objects one at a time, inspects only envelope structure (magic, declared count, body length, complete 38-byte record count, incomplete-tail byte count), skips malformed objects that satisfy the exact V4 class, and stops at the first malformed object outside that class.

It must not decode record fields, position identities, bytes 33:38, scores, WDL, q-values, model outputs, confirmation targets, search results, fits or games. Alpha spent is zero. No automatic scientific continuation is authorized.

Output is strictly technical: job_id, attempt_id, path, kind, SHA256, size, envelope shape and failure reason. The result determines whether 1914 exposed an implementation bug, another instance of the same authenticated interrupted-writer mechanism, or a genuinely new anomaly class requiring a separate decision.
