# L3 blind-spot atlas v1

Status: **tool-only diagnostic specification**.

This document defines the first autonomous L3 blind-spot atlas.  It does not
define a training gate, a promotion gate, a model choice or a follow-up job.
The v1 implementation is `tools/blind_spot_atlas.py`.

## 1. Scope

The tool consumes exactly one aligned pair:

- a counted `JNNW` file (`JNNW`, `u32 count`, `count * 38` bytes);
- its counted `JSM1` sidecar (`JSM1`, `u32 count`, `count * 17` bytes).

It uses only:

- the four 50-square bitboards;
- side to move;
- terminal WDL from the side-to-move point of view;
- `game_id`, `opening_id` and `seeded`.

The existing JNNW score is ignored because the base format does not identify
the model, search depth or search configuration that produced it.  No Scan,
EGDB, master corpus, oracle, external teacher or new engine output is accepted
by v1.

## 2. Fail-closed input contract

Before publishing either output, the tool verifies:

1. both magic values, counts, exact record sizes and absence of trailing bytes;
2. equal non-zero JNNW/JSM1 counts;
3. disjoint bitboards restricted to squares 1..50;
4. no white man on squares 1..5 and no black man on squares 46..50;
5. side-to-move, WDL and `seeded` domains;
6. one stable `(opening_id, seeded)` tuple per `game_id`;
7. full lowercase 40-hex `--code-sha`;
8. distinct input/output paths and absent output paths.

The input SHA-256 values cover the complete counted files, including headers.
The opened files are also rejected if their size or modification time changes
while they are read.

Both outputs are staged in their destination directories, flushed, then
published with atomic no-clobber links.  If publication of the second file
fails, the first publication is rolled back.  Existing files and inputs are
never overwritten.

## 3. Objective taxonomy

Every record belongs to exactly one bucket in every dimension.  Empty buckets
are still emitted with zero counts so missing coverage remains visible.

| Dimension | Definition |
| --- | --- |
| `phase` | Piece count: opening >=30, midgame 22..29, late midgame 15..21, endgame 8..14, deep endgame <=7. |
| `material_stratum` | Absolute weighted margin with man=1, king=3: P4=0, P3=1, P2=2..3, P1>=4. |
| `material_leader` | White, black or equal under the same material convention. |
| `stm_material_status` | Side to move ahead, equal or behind under that convention. |
| `king_configuration` | No kings, white only, black only or kings on both sides. |
| `side_to_move` | White or black from the JNNW byte. |
| `source` | `standard` for `seeded=0`, `frontier` for `seeded=1`. |
| `nearest_promotion_distance` | Minimum geometric row distance of any man to its promotion row. |
| `promotion_race` | Comparison of White's and Black's nearest geometric promotion distances. |
| `camp_penetration` | Presence of White pieces on rows 0..4 and/or Black pieces on rows 5..9. |

`nearest_promotion_distance`, `promotion_race` and `camp_penetration` are
geometric descriptors only.  They do not imply that a route is legal, safe,
forced or strategically favourable.

The taxonomy definition is embedded in the JSON and receives its own SHA-256.

## 4. Per-bucket diagnostics

Each `(dimension, bucket)` row contains:

- correlated position-record count and share;
- unique `game_id` count and share;
- unique `opening_id` count and share;
- record-level W/D/L from the JNNW side-to-move point of view;
- record-level terminal winner by colour;
- eligible, converted, drawn and reversed material-lead records.

Conversion means only:

> the colour with greater weighted material in that record is the terminal
> winner recorded for the game.

Records from the same game are correlated, and one game may visit several
buckets.  These rates therefore describe corpus coverage and outcomes; they
are not independent game estimates and cannot authorize a gate.

The JSON states:

- `diagnostic_only=true`;
- `gate_authorized=false`;
- `promotion_authorized=false`;
- `automatic_continuation_authorized=false`;
- `decision=diagnostic_only_no_gate`.

The long-form CSV repeats the diagnostic and gate guards on every row.

## 5. Fixed probe

The probe is a deterministic bottom-k sample over unique 33-byte positions
(four bitboards plus side to move):

```text
selection_sha256 =
    SHA256("JASS-L3-BLIND-SPOT-PROBE-V1\0" || seed_u64_le || position)
```

The lowest `--probe-size` keys are retained.  Selection is independent of
record order and duplicate frequency.  The JSON stores:

- the versioned selection name and seed;
- position bytes in hex;
- position SHA-256 and selection SHA-256;
- board-derived taxonomy tags;
- one aggregate `probe_sha256`.

The input hashes, code SHA, taxonomy hash, probe seed and probe hash together
freeze one reproducible diagnostic probe.  Extending or replacing the source
corpus may legitimately change the bottom-k sample.

## 6. Deterministic outputs

The JSON uses sorted keys, stable indentation and no timestamp or filesystem
path.  Atlas rows and CSV rows are sorted by `(dimension, bucket)`.  Rates are
rounded to 12 decimal places and CSV uses `\n` line endings.  The JSON embeds
the exact CSV SHA-256.

Example:

```bash
python3 tools/blind_spot_atlas.py \
  --data source.jnnw \
  --meta source.jsm \
  --json-out blind-spot-atlas-v1.json \
  --csv-out blind-spot-atlas-v1.csv \
  --code-sha 0123456789abcdef0123456789abcdef01234567 \
  --probe-size 256 \
  --probe-seed 20260728
```

The command refuses to replace either output.  A second run must use new paths
or deliberately remove the first diagnostic outside this tool.

## 7. Deferred sidecar extensions

The following metrics are intentionally absent from v1:

| Metric | Required extension |
| --- | --- |
| Mandatory capture versus quiet | Aligned, versioned QIET/legal-move sidecar. |
| Mobility | Aligned, versioned FEAT or legal-move sidecar. |
| Model disagreement | Two aligned static-score sidecars with model hashes. |
| Depth instability | Two aligned search-score sidecars with pinned depths and search configuration. |
| Terminal surprise | Provenance-bearing score sidecar plus a frozen surprise definition. |

Each future sidecar must have magic, schema version, count, alignment contract,
producer configuration and hashes.  Missing sidecars must remain missing data;
v1 must not synthesize or infer these metrics from the unprovenanced JNNW
score.

## 8. Targeted verification

`jobs/tests/test_blind_spot_atlas.py` covers:

- deterministic byte-identical JSON/CSV output;
- order-independent atlas and probe selection;
- sorted JSON/CSV rows and read-back;
- objective bucket and conversion calculations;
- count/alignment and record-domain rejection;
- per-game metadata consistency;
- input/output path separation and no-clobber;
- rollback when the second atomic publication fails.

No CPX62 job, training step, gate or automatic continuation belongs to this
MVP.
