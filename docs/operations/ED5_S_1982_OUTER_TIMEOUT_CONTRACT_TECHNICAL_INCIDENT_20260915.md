# ED5 S rehearsal 1982 — OUTER_TIMEOUT_CONTRACT technical incident

Classification: **TECHNICAL**. Scientific verdict: **none**.

`cpx62-1982-l3-ed5-fresh-s-source-rehearsal-v1` failed before S source science because its immutable stage spec declared `timeouts.stage_seconds=1200`, while the archived control-plane dispatch exported `EXPECTED_LAUNCH_TIMEOUT_SECONDS=1500`. Launch Admission V2 requires the outer timeout to be exactly `stage_seconds + 600`, therefore `1800`, and correctly rejected the launch with `OUTER_TIMEOUT_CONTRACT`.

The repair is control-plane-only. Jass code remains pinned to `9e8eb2a32d80f15491ef1ff6bb5aa3b95edcdc49`; the S stage command/profile, W production input identity, frozen S source semantics/seeds, resources, stage timeout, outputs and zero target/search/fit/alpha budget are unchanged. jass-control PR #686 queues immutable successor `cpx62-1983-l3-ed5-fresh-s-source-rehearsal-v2` with the exact copied 1982 stage spec SHA256 `62decee078647a7431b4b394e26b7172025e1e4c946efdd3acfcf85da74f4877` and corrected outer dispatcher timeout `1800`.

Durable regression coverage is the Launch V2 queue contract test `tests/test_launch_dispatcher_v2.py::DispatcherTests::test_current_pending_scripts_are_canonical_and_hash_bound`, which requires every pending/running dispatch timeout to equal the bound stage spec timeout plus 600 seconds. The incident remains mitigated until the 1983 target-host rehearsal terminates and authenticates successfully.
