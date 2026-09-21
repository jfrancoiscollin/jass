# CLS panel audit — final publication collision, 21 September 2026

## Observed failure and authenticated evidence

Job `cpx62-2071-l3-cls-g0-panel-historical-audit-retry-v2`, attempt
`20260920T201519Z-4ba9cfbf`, code
`4ba9cfbf4637df25affe67318a43ba77093803a4`, remains **FAILED / exit 2**.
Its control status blob is `e2dcda3ce552df11c9bcf8fb51e4506486b39937`.
The R2 `_FAILED`, manifest, inventory, checksums and ten selected result files
were independently read back on 21 September using the pinned repository fetcher.

The exact failure is `NO_CLOBBER` at the final `scientific-summary.json` write.
`StageEvidence` had already created that file as a `jass.launch_progress.v2`
checkpoint. The final writer incorrectly treated that owned progress file as an
unrelated immutable output. This is a publication defect, not a scientific loss.

Authenticated artifact SHA256 values:

| Artifact | SHA256 |
|---|---|
| audit-failure.json | `662a773ea295d31f95a1afe1f3d17c7435461e661f688f914ec50e211eb4ad2d` |
| execution-evidence.json | `04841bcdb4a0977b844bb1d87e8d18ee9d388b1afd1265b9d61617ea05d6630d` |
| historical-2069-raw-audit.json | `dd5fd56e6782fc89459fbff936d127029b602fa648ab494d7ca50cc819c9f389` |
| historical-g0-all-roots.tsv | `4edf02242ceb8e1307a8d47babfafd9f44931240dbad22abc28ec28f63790217` |
| g0-descriptive-summary.json | `24a685c459a4cc76a0c032b62996e556c89f17bdb3669e6f29ead74b2f2470fc` |
| stage-receipt.json | `101cbd7d314503211c273d94541e74ad3896f928ac20598ac16a1d8605e02e0b` |

Four phases completed before publication: source/model authentication, native
continuity, historical replay and all G0 roots. The raw report records 576 games,
60,314 moves, 62,005 requests, ten censures and the unchanged 2069 interval
`[0.41389671183445104, 0.5913116214988823]`. Both G0 tables contain all 512 roots:
56 target-depth failures and 456 exact receipts per model. No receipt is imputed.
These are authenticated intermediate results of a **failed** attempt; they do
not admit readiness, establish a successful launch receipt or close the audit.

## Narrow repair and regression

The final-summary writer may replace only the current running progress summary
owned by the same execution evidence. Foreign, finalized or inconsistent
summaries and symlinks remain rejected. The general no-clobber writer is unchanged.
A regression runs all five stage phases with the real `StageEvidence`, substituting
fixtures only for historical data/native work, and checks the final artifacts,
manifest and evidence. It also checks rejected replacement paths. This is a
synthetic publication test, not real archive/native proof.

The test is part of the existing raw-audit suite, already mandatory in the unchanged Launch-V2 profile and dedicated CI. Native sources,
models, historical G0 verdicts, roots, budgets of searches/games, statistical
rules and the frozen panel contract remain unchanged. CURRICULUM remains champion.

## Fresh mandate and bounded admission

On 21 September JFC requested **"poursuivre la campagne cls"**. This fresh mandate
authorizes the necessary corrected same-scope technical retry. It does not reuse
the earlier exhausted one-retry authorization or authorize any automated loop.
After reviewed code and successful current-head CI, use exactly one new job and
attempt, replaying the entire audit without reusing 2070/2071 partial outputs.
No readiness or comparative matches are included in this admission.

Keep the previous conservative debit of 400 seconds for 2070. For 2071, the
stage lasted **55.73672 seconds**; runner start to terminal status was 382 seconds,
and attempt timestamp to the done commit was 390 seconds. Conservatively debit
another **400 seconds**, including publication, against both accounting envelopes.
The done commit is `4122577d394c77704f62bdd3b99ba4bc3c817db3`.

The sole new attempt gets **100 stage seconds**, the existing 30-second termination
grace, and the canonical **700-second dispatcher limit** (100 + 600). Therefore
`400 + 400 + 100 = 900` stage seconds and `400 + 400 + 700 = 1500` dispatcher
seconds preserve the original audit envelopes; the whole panel's 9900/12300
accounting ceilings are unchanged. These debits deliberately overcount stage
time and are not CPU-second measurements. Termination/publication overhead belongs
to the dispatcher reserve; existing outer-publisher controls still apply and
actual elapsed publication time must be recorded separately.

The measured anchor is the same full audit on CPX62 with 16 available CPUs:
55.73672 seconds for the stage and 390 seconds through publication. Expected
order of magnitude is about one minute of stage work and 6–7 minutes through
publication. The 100/700-second allowances are hard admission limits, not a
promise of success. No data, phase or validation may be dropped to meet them.

Before queue merge: recheck pending/running and duplicates, validate canonical
nine-line dispatch and newline-sensitive spec/admission hashes, successful
current-head CI, and the five dispatcher tests. All actual-effect ceilings remain
zero. A successful fresh R2 publication and readback are required for closure.
A further failure yields `G0_PANEL_BLOCKED_NO_JOINT_VERDICT_V1` with no additional
retry, budget increase, partial-output salvage or downstream game under this
admission. Preserve all prior failed attempts and all scientific history.
