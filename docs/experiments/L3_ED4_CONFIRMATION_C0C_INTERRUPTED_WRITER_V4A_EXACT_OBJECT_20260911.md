# L3 ED4 C0C interrupted-writer V4A exact-object extension

Date: 2026-09-11. Status: preregistered, prospective, technical-only.

## Trigger

Terminal diagnostic `cpx62-1920-l3-ed4-c0c-v4-next-failure-diagnostic-v1` completed successfully after skipping 8 already-authorized V4 interrupted-writer instances. It then stopped on the next malformed JNNW:

- producer job: `cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1`
- attempt: `20260905T145718Z-d3657332`
- path: `b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0297-saturate-loop/artefacts/sp0-1.jnnw`
- SHA256: `bb556ce4b75a16e2123c2413346bb2abe34375c46d53531079d9ca324cc9aeea`
- size: `98498` bytes
- structural diagnostic: JNNW, declared count `0`, `jnnw_trailing_bytes`
- arithmetic shape: `(98498 - 8) = 2591 * 38 + 32`

Diagnostic counters were all zero for target/WDL/qvalue/score/model decoding and alpha spent.

## Prospective authorization

Extend the existing V4 recovery policy to this **single authenticated object only**. Do not authorize the `ccx33-0297-saturate-loop` directory, a filename family, a prefix, or any sibling object.

Recovery remains identical to V4:

1. authenticate producer job, attempt, path, SHA256 and size against the frozen inventory;
2. require JNNW magic and placeholder declared count `0`;
3. recover only the complete 38-byte prefix records;
4. use only the first 33 bytes of each recovered record for position identity;
5. never decode or interpret bytes `33:38` of any complete record;
6. discard the final 32-byte incomplete tail;
7. publish zero-read counters and fail closed on any identity or shape drift.

Expected structural recovery for this object is exactly 2591 complete records and 32 discarded tail bytes.

## Fail-closed boundary

Any sibling such as `sp0-2.jnnw`, any different SHA/size, another job/attempt, bad magic, non-zero declared count, zero complete records, or zero tail is **not** authorized by V4A and must stop C0C for a new structural diagnostic.

## Scientific invariants

V4A changes no ED4 candidate bytes, threshold, alpha, confirmation corpus, WDL/qvalue target, verdict gate, fit, search, game count, promotion rule, or confirmation authorization. It remains structural exclusion-union plumbing only.
