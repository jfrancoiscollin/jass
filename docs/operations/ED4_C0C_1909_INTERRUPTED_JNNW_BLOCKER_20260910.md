# ED4 C0C — authenticated interrupted JNNW blocker (1909)

<!-- Ordinary branch commit after incident-register autofeed so required PR checks run on the final head. -->

Date: 2026-09-10. Classification: **TECHNICAL / SOURCE-ARTIFACT INTEGRITY**.

Immutable diagnostic `cpx62-1909-l3-ed4-c0c-jnnw-shape-diagnostic-v1`, attempt `20260910T162746Z-35f0fd1b`, completed with exit 0 and localized the first C0C 1907 parse blocker without decoding any position record or target field.

The authenticated object is:

- producer: `cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1`
- attempt: `20260905T145718Z-d3657332`
- path: `b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw`
- SHA256: `730ee719a651e371c782afd1c1f29a4a95a2c81b2bfdf7f9748aab4d6d7cd576`
- size: `114914` bytes
- JNNW header count: `0`
- failure token: `jnnw_trailing_bytes`

The object sits inside the detached documentary Git worktree created by job 1785. Its embedded historical source job `ccx33-0206-wdl-loop-mt60` failed while the first self-play generation was still running. The historical generator writes `JNNW`, a zero count placeholder, then 38-byte records, and backpatches the count only on normal completion. For this immutable object, `114914 - 8 = 114906 = 3023 * 38 + 32`: it contains 3023 complete record-width chunks followed by a 32-byte partial chunk while the header still declares zero records. This is consistent with an interrupted live writer snapshot, not a valid counted JNNW file.

This finding does **not** authorize a C0C parser recovery. The active C0C V1 preregistration requires exact `JNNW + u32 count + count*38` shape and fail-closed behavior on trailing bytes. Skipping the object, broadening the documentary-worktree exclusion rule, or salvaging complete record-width prefixes would change the frozen post-preregistration interpretation of the 726-candidate C0B set. No such semantic change is made here.

No ED4 confirmation target, score, WDL, q-value or model was read by 1909. `alpha_spent=0`, no fit/search/game occurred, and confirmation remains unauthorized. The safe next step requires an explicit prospective protocol decision/version for how authenticated interrupted historical JNNW snapshots contribute to the over-inclusive exclusion universe; until then C0C remains fail-closed and no C0C requeue is authorized.
