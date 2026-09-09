# ED4-P1 — published CI and rehearsal admission preparation

The user explicitly approved ED4-P1 publication and P0 PR #884 merge. PR #884
is merged. ED4 code is published in PR #885. The immutable execution SHA is
`93e2fd1f19417bb5076e2013830ec77e999d95bf`; its tree is exactly the approved
and locally tested tree `8f4997790d42e65e8953b4107391197917a8d4fd`.
The workflow blob is identical across local and GitHub publication:
`d9c55d194aad22daef8399b18d4c03220ae2e509`. Later documentation commits do not
replace this execution SHA.

## Published evidence

- Full ED4 contract CI: [34360491615](https://github.com/jfrancoiscollin/jass/actions/runs/34360491615),
  all steps completed successfully on the pinned source: 33 regressions with
  zero failures/errors/skips, actual C++ rehearsal/production and publisher
  roundtrip, then fixed P0 recheck.
- P0 CI `34360491465`, generic admission CI `34360491500`, and native/build CI
  `34360491586` also completed successfully on that source.
- Artifact `10107662852`, `ed4-fit-contract-receipts`, archive SHA256
  `3ccc569ff3ffc9ed0d29ed609f74e165def54c493acc58b9f1d095ee3e1b77cb`:
  downloaded ZIP bytes match GitHub's published digest. Extracted files match
  the archive and were reread. P0 report SHA256 is
  `6377b0cf1eea4b2697210f2ead29a4394f205db2479f8674a27e42084cf55a9d`.

These are synthetic engineering results, not real-candidate convergence or
heldout decision/calibration/search evidence. Earlier local preparation used
17 synthetic optimizer calls; no real fit had run at this readiness checkpoint.

## Target and proposed rehearsal

Read-only CPX62 checks confirm 16 available CPUs, 575790 MiB free on the result
and scratch filesystem, and Python 3.14.4 / NumPy 2.5.2 / SciPy 1.18.0. The
five-minute runner timer is active; the latest observed oneshot tick completed
successfully. A service being inactive between ticks is expected.

Metadata-only ED3 anchors remain 16 seconds for the comparable fit stage and
308 seconds through publication. Estimated ED4 repetition: 5–10 minutes,
solver cap 300 seconds, stage cap 900 seconds, outer cap 1500 seconds, numerical
libraries at one thread. ED4 checks at least 3 GiB free before any input fetch.
The full 512 TRAIN parents and 8192 replay rows are retained; exactly one fit,
zero searches, games or TEST reads. No production is admitted by this note.

Control PR #585 proposes rehearsal `cpx62-1887-l3-ed4-choice-value-fit-rehearsal-v1`.
The stage spec hash is
`33693e4ee2116420e9f05c8eb7684c8d72c08e84fe46c9a30522a270e1ea0886`;
admission hash
`1a332456fbebc6b6f1ae2930c6fc86a6815d59004e6ee721d053bc0ede8d28b3`;
normalized same-mode-independent spec hash
`a3e0a0e11cfb3c7c0794c29e35a2d0d1e186e96e45ac5606b7e3d38157909233`.
The five dispatcher tests pass on the immutable LF archive, including the
proposed pending script and actual stage/admission schema checks.

The first local Windows/WSL dispatcher attempts failed before execution:
Windows lacks `/usr/bin/bash`, and its checkout/export converted LF to CRLF.
Byte comparison proved that ordinary `git archive` inherited this conversion:
the spec had zero CR bytes in Git but one in the archive. Exporting with
`git -c core.autocrlf=false archive` preserves the actual Linux bytes. No stage
spec, hash, scientific parameter or dispatcher source required a change. This
is companion evidence for existing TI-024. Five Linux tests passed in 0.317 s.

The control repository was verified private, owned by the connected account
with ADMIN access before publishing its proposal. Actual launch still requires
control CI and queue merge; production then requires the completed, published,
authenticated same-code rehearsal. No real candidate or scientific gain is
claimed here.
