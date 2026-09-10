# L3 ED4 C0C interrupted-writer class recovery V4

Date: 2026-09-10. Status: preregistered, prospective, technical-only.

## Trigger

Diagnostics 1909, 1911 and 1913 independently localized `sp1-1.jnnw`, `sp1-2.jnnw` and `sp1-3.jnnw` under the same frozen producer `cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1`, attempt `20260905T145718Z-d3657332`, historical path prefix `b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/`. Each authenticated object has JNNW magic, placeholder declared count 0, non-empty body and trailing bytes incompatible with the declared count. All three have the same 114914-byte envelope. No target/WDL/q-value/model field was read by those diagnostics.

Object-by-object amendments stop here. V1/V2/V3 remain immutable historical evidence.

## Prospective class

Before inspecting any further candidate payload, V4 authorizes complete-record recovery only for a candidate satisfying **all** predicates below:

1. frozen source job exactly `cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1`;
2. frozen attempt exactly `20260905T145718Z-d3657332`;
3. path is under exactly `b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/`;
4. candidate descriptor kind exactly `jnnw`;
5. descriptor path, size and SHA256 match the authenticated frozen result inventory before payload interpretation;
6. payload begins with `JNNW` and little-endian declared count is exactly zero;
7. after the 8-byte envelope header, payload contains at least one complete 38-byte record and a non-zero incomplete suffix of 1..37 bytes;
8. only bytes `0:33` of each complete record may be decoded as position identity;
9. bytes `33:38` of every complete record are never decoded, copied into a target structure, summarized, compared or otherwise interpreted;
10. the incomplete suffix is discarded in full and never decoded.

The class is intentionally producer/attempt/path-prefix scoped. It is **not** a generic repair rule for malformed JNNW. Any malformed object outside this exact class remains V1 fail-closed.

## Scientific firewall

Recovery serves only C0C structural exclusion-union construction. It reads position identities solely to prevent confirmation contamination. It authorizes zero confirmation reads, zero WDL/q-value/score reads, zero model reads, zero teacher/search calls, zero fits/games, zero alpha and no promotion.

If any object from the scoped producer/attempt is malformed in a different way (bad magic, non-zero declared count incompatible with body, no complete record, exact multiple of 38 despite count zero, gzip/other kind, inventory drift), V4 fails closed and ED4 stops for a new technical/scientific decision.

## Terminal

Successful union terminal: `ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V4_CLASS`.

The manifest must publish class-matched file count, complete records recovered, discarded tail bytes, per-object authenticated SHA/size, union SHA256 and all zero-read counters. No automatic confirmation continuation is authorized by C0C itself; the existing preregistered ED4 chain decides the next stage.
