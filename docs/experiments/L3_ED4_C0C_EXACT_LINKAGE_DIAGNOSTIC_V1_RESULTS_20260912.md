# ED4 C0C — exact-linkage diagnostic V1 result

Date: 2026-09-12. Classification: `TECHNICAL_STRUCTURAL_RECOVERY_INVESTIGATION_ONLY`.

The exact-linkage diagnostic completed its five phases. Publication was
authenticated and independently reread successfully. The implementation is
[PR #935](https://github.com/jfrancoiscollin/jass/pull/935), code
`038c7dceb057f8a150459d8d521dda84137ae343`.

The diagnostic examined 21 authenticated failure descriptors: 15 TSV aliases
in four schemas, three FEN aliases, and three JNNW aliases. The aggregate source
sizes were 7,568 parent rows and 49,181 child rows:

| TSV source aggregate | Parent rows | Child rows |
| --- | ---: | ---: |
| Schema 1 | 4,000 | 15,937 |
| Schema 2 | 2,000 | 18,400 |
| Schema 3 | 784 | 7,556 |
| Schema 4 | 784 | 7,288 |
| **Total** | **7,568** | **49,181** |

The exact evidence counts were three comment-only FEN aliases proven as empty,
15 TSV aliases with child linkage proven, and three invalid-side-to-move JNNW
aliases left unresolved fail-closed. The terminal classification was
`ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE`.

The readback authenticated 14 sources and 29 payloads. The authenticated ledger
totals were 227,300,796 opaque hash bytes (two complete hashing passes per
payload), 13 headers,
285,168 allowed structural fields, 728,603 identity prefixes read, 317,903
prefixes validated, and zero forbidden fields. The
invalid nominal total was 671,854: 391,247 zero-STM rows, 19,067 one-STM rows,
and 261,540 other rows; 261,154 were strictly valid under the diagnostic’s
nominal checks.

The stage duration was 80.053468 seconds and publication completed after 129
seconds. All 84 registered preflight regressions passed before execution, and
all five execution phases completed. Artifact causality was not established;
alternate framing, shard-boundary inference, and recovery coverage were not
established either.

The frozen 726-descriptor partition remains unchanged, including 216 V5 rows,
15 V6 rows, and six zero-byte objects. The ED4 candidate remains unchanged;
`scientific_verdict` is null, confirmation authorization is false, and alpha
expenditure is zero. No exclusion union, target, score, WDL, model, q-value,
search, fit, game, promotion, or bake was produced or authorized by this
diagnostic.
