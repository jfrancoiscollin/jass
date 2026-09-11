# L3 ED4 C0C full malformed JNNW inventory V1

Date: 2026-09-11. Status: preregistered, structural-only diagnostic.

## Purpose

Replace iterative first-failure debugging with one exhaustive pass over every authenticated candidate JNNW in the already-frozen C0A/C0B source universe. The diagnostic publishes all malformed JNNW envelopes at once so a single exact-object recovery table can be preregistered prospectively before the next C0C run.

## Allowed reads

For each candidate descriptor, authenticate result inventory identity, path, SHA256 and size, fetch the exact object, and inspect only JNNW envelope structure: magic/header, declared count/body-length consistency and trailing-byte shape. For interrupted-writer classification, complete-record count and partial-tail length are derived from authenticated file size using 8-byte header + 38-byte record geometry.

## Forbidden reads

No record field is decoded. In particular: no position identity bytes, no final five target bytes, no WDL/q-value/score/model field, no teacher/search calls, no fit/game, no confirmation target, no alpha spend.

## Output

`ed4-c0c-v4-full-malformed-inventory.json` lists every malformed object with exact job_id, attempt_id, path, SHA256, size, declared count, structural reason, complete-record count derived from size, partial-tail bytes derived from size and interrupted-writer-shape boolean. It also publishes global zero-read counters and whether all malformed objects share the interrupted-writer shape.

This diagnostic itself authorizes no salvage and no ED4 continuation. A follow-up preregistration must freeze the exact authenticated object table before C0C is rerun.
