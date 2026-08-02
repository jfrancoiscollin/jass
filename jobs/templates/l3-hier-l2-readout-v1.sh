#!/usr/bin/env bash
# Readout-only de la porte générique HIER vs CONTROL. Aucun jeu ni fit ici.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${SOURCE_RESULT_URI:?}"; : "${EXPECTED_SOURCE_JOB:?}"
: "${EXPECTED_SOURCE_ATTEMPT:?}"; : "${EXPECTED_SOURCE_CODE_SHA:?}"

die(){ printf 'ABORT: %s\n' "$*" >&2; exit 1; }
cd "$JASS_CODE_DIR"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-codex-hier-l2-readout-at-([0-9a-f]{8})-v[0-9]+$ ]] ||
  die "job must use home/codex/hier-l2-readout/at-sha nomenclature"
[ "${BASH_REMATCH[1]}" -ge 1200 ] || die "home job number must be >=1200"
[[ "$EXPECTED_CODE_SHA" == "${BASH_REMATCH[2]}"* ]] || die "visible SHA mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

IN="$JASS_ARTEFACT_DIR/source"; mkdir -p "$IN"
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_RESULT_URI" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=gate-summary.json \
  --out-dir "$IN" --report "$JASS_ARTEFACT_DIR/verified-gate.json" \
  --expected-state completed || die "immutable gate fetch failed"
python3 - "$JASS_ARTEFACT_DIR/verified-gate.json" "$EXPECTED_SOURCE_JOB" \
  "$EXPECTED_SOURCE_ATTEMPT" "$EXPECTED_SOURCE_CODE_SHA" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
expected = {"job_id": sys.argv[2], "attempt_id": sys.argv[3],
            "code_sha": sys.argv[4], "result_state": "completed"}
for key, value in expected.items():
    if r.get(key) != value:
        raise SystemExit(f"source {key}={r.get(key)!r}, expected {value!r}")
PY

OUT="$JASS_ARTEFACT_DIR/hier-l2-verdict.json"
python3 jobs/tools/l3_hier_l2_verdict.py --gate-summary "$IN/gate-summary.json" --out "$OUT"
python3 - "$OUT" "$SOURCE_RESULT_URI" "$EXPECTED_SOURCE_JOB" \
  "$EXPECTED_SOURCE_ATTEMPT" "$EXPECTED_SOURCE_CODE_SHA" "$EXPECTED_CODE_SHA" <<'PY'
import json, sys
path = sys.argv[1]
r = json.load(open(path))
r["source"] = {"result_uri": sys.argv[2], "job_id": sys.argv[3],
               "attempt_id": sys.argv[4], "code_sha": sys.argv[5]}
r["readout_code_sha"] = sys.argv[6]
open(path, "w").write(json.dumps(r, indent=2, sort_keys=True) + "\n")
PY
cp "$OUT" "$JASS_ARTEFACT_DIR/JASS_CONTROL_SUMMARY.json"
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$OUT")
: > "$JASS_ARTEFACT_DIR/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$JASS_ARTEFACT_DIR/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' > "$JASS_ARTEFACT_DIR/AUTOMATIC_NEXT_JOB__NULL"
