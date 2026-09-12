# ED4 C0C — complete format diagnostic V2 result

Date: 2026-09-12. Classification: `TECHNICAL_FORMAT_DIAGNOSTIC_ONLY`.

The bounded rehearsal of the [V2 diagnostic](L3_ED4_C0C_FULL_FORMAT_DIAGNOSTIC_V2_20260912.md)
completed all five phases. Its publication was authenticated and independently
reread, including the complete descriptor table, recovery membership, canonical
digests, launch receipts, and published completion time. The implementation is
[PR #933](https://github.com/jfrancoiscollin/jass/pull/933), code
`bd9b943ddadf22bd555e33d9fecb331b6fb55837`.

| Descriptor outcome | Count |
| --- | ---: |
| Strict V1 parser passed | 468 |
| Exact V5 partial recovery passed | 216 |
| Exact V6 aligned recovery passed | 15 |
| Authenticated zero-byte object | 6 |
| FEN with no position after comment stripping | 3 |
| Invalid side-to-move value | 3 |
| TSV without a recognized position field | 15 |
| Total | 726 |

The 21 rejected descriptors comprise six distinct content hashes. The three
FEN objects share one content hash and have valid UTF-8, one comment line, and
zero position-bearing lines. The three side-to-move failures share another
content hash. The fifteen TSV failures cover four content hashes. These are
diagnostic classifications, not permission to discard or repair their contents.

The report records 33,142,121 successfully parsed position-row visits, including
repeated sources. This is neither a unique-position count nor a measurement of
all attempted position reads; the latter remains explicitly unmeasured.

The stage took 684.60603 seconds. Attempt start through published completion
took 783 seconds, within the respective 2100- and 2700-second limits. All 66
registered regressions passed both under Linux before launch and on the server.
Nine independent readback tests passed. The readback validates the stage summary
and the exact launch metadata added by the launch controller separately.

No target fields, scores, WDL values, models, or q-values were decoded. No
teacher, search, fit, game, alpha expenditure, promotion, or bake occurred.
No exclusion union was published, and no scientific verdict or confirmation
authorization follows from this technical completion.

The next step is a prospective investigation of the exact rejected descriptors
and their provenance before defining any new recovery version. An invalid
position or a missing TSV field is not evidence of an empty exposure footprint.
The frozen descriptor universe and prior recovery versions remain unchanged.
ED3 remains negative; ED4 still requires fresh decision, independent WDL, and
equal-node search confirmation. No scale-up is authorized by this result.
