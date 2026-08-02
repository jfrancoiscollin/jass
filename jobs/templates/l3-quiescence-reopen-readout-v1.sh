#!/usr/bin/env bash
# Readout-only recovery of the immutable home-1200 quiescence measurements.
# No game, build, fit, promotion or continuation is permitted here.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_JOB_ID:?}"
: "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SOURCE_RESULT_URI:?}"
: "${EXPECTED_SOURCE_JOB:?}"; : "${EXPECTED_SOURCE_ATTEMPT:?}"
: "${EXPECTED_SOURCE_CODE_SHA:?}"

die(){ printf 'ABORT: %s\n' "$*" >&2; exit 1; }
cd "$JASS_CODE_DIR"
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-codex-.*-at-([0-9a-f]{8})-v[0-9]+$ ]] ||
  die "readout job must use the registered home/codex/at-sha nomenclature"
[ "${BASH_REMATCH[1]}" -ge 1200 ] || die "home job number must be >=1200"
[[ "$EXPECTED_CODE_SHA" == "${BASH_REMATCH[2]}"* ]] || die "visible SHA mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"

IN="$JASS_ARTEFACT_DIR/source"
mkdir -p "$IN/force" "$IN/conversion"
fetch(){ rclone copyto "$SOURCE_RESULT_URI/$1" "$IN/$2"; }
fetch manifest.json manifest.json
fetch inventory.json inventory.json
fetch artefacts/logs.tar.gz logs.tar.gz
fetch artefacts/force/fixed-Q01-vs-Q00.json force/fixed-Q01-vs-Q00.json
fetch artefacts/force/native-Q01-vs-Q00.json force/native-Q01-vs-Q00.json
for arm in Q00 Q01; do
  for stratum in p3_mince p4_egal; do
    fetch "artefacts/conversion/$arm-$stratum.json" "conversion/$arm-$stratum.json"
  done
done

python3 - "$IN" "$EXPECTED_SOURCE_JOB" "$EXPECTED_SOURCE_ATTEMPT" \
  "$EXPECTED_SOURCE_CODE_SHA" <<'PY'
import hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1])
job, attempt, code = sys.argv[2:]
manifest = json.loads((root / "manifest.json").read_text())
expected = {
    "job_id": job,
    "attempt_id": attempt,
    "code_sha": code,
    "state": "failed",
    "exit_code": 1,
}
for key, value in expected.items():
    if manifest.get(key) != value:
        raise SystemExit(f"source manifest {key}={manifest.get(key)!r}, expected {value!r}")

inventory = {
    item["path"]: item["sha256"]
    for item in json.loads((root / "inventory.json").read_text())["files"]
}
local_to_remote = {
    "logs.tar.gz": "artefacts/logs.tar.gz",
    "force/fixed-Q01-vs-Q00.json": "artefacts/force/fixed-Q01-vs-Q00.json",
    "force/native-Q01-vs-Q00.json": "artefacts/force/native-Q01-vs-Q00.json",
}
for arm in ("Q00", "Q01"):
    for stratum in ("p3_mince", "p4_egal"):
        local = f"conversion/{arm}-{stratum}.json"
        local_to_remote[local] = f"artefacts/{local}"
for local, remote in local_to_remote.items():
    path = root / local
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if inventory.get(remote) != digest:
        raise SystemExit(f"immutable source checksum mismatch: {remote}")
PY

tar -xzOf "$IN/logs.tar.gz" ./readout.log |
  grep -Fq 'TypeError: Object of type bool_ is not JSON serializable' ||
  die "source failure is not the registered serialization-only failure"

mapfile -t PARAMS < <(python3 - "$IN" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
fixed = json.loads((root / "force/fixed-Q01-vs-Q00.json").read_text())
conversion = json.loads((root / "conversion/Q00-p3_mince.json").read_text())
print(fixed["search_params_b"])
print(fixed["search_params_a"])
print(conversion["defender_search_params"])
PY
)
[ "${#PARAMS[@]}" -eq 3 ] || die "cannot recover registered fingerprints"

OUT="$JASS_ARTEFACT_DIR/quiescence-reopen-verdict.json"
python3 jobs/tools/l3_quiescence_reopen_verdict.py \
  --fixed-gate "$IN/force/fixed-Q01-vs-Q00.json" \
  --native-gate "$IN/force/native-Q01-vs-Q00.json" \
  --conversion-dir "$IN/conversion" \
  --q00 "${PARAMS[0]}" --q01 "${PARAMS[1]}" --defender-q00 "${PARAMS[2]}" \
  --expected-games-per-view 3000 --min-paired-per-stratum 270 \
  --bootstrap-samples 20000 --seed 20260802 --out "$OUT"

python3 - "$OUT" "$SOURCE_RESULT_URI" "$EXPECTED_SOURCE_JOB" \
  "$EXPECTED_SOURCE_ATTEMPT" "$EXPECTED_SOURCE_CODE_SHA" "$EXPECTED_CODE_SHA" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
report = json.loads(path.read_text())
report["source"] = {
    "result_uri": sys.argv[2],
    "job_id": sys.argv[3],
    "attempt_id": sys.argv[4],
    "code_sha": sys.argv[5],
    "recovery_reason": "numpy.bool_ JSON serialization only",
}
report["readout_code_sha"] = sys.argv[6]
path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

cp "$OUT" "$JASS_ARTEFACT_DIR/scientific-summary.json"
printf '%s\n' "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["scientific_verdict"])' "$OUT")" \
  > "$JASS_ARTEFACT_DIR/VERDICT.txt"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$JASS_ARTEFACT_DIR/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' > "$JASS_ARTEFACT_DIR/AUTOMATIC_NEXT_JOB__NULL"
