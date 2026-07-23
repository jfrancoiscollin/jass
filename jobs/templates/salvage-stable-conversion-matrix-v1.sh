#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# No-replay salvage of one pinned 400-ply cap from failed 0908.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?}"
: "${SOURCE_0908_PREFIX:?}"
: "${SOURCE_0908_JOB_ID:?}"
: "${SOURCE_0908_ATTEMPT_ID:?}"
: "${SOURCE_0908_CODE_SHA:?}"
: "${SOURCE_PARTIAL_TAR_SHA256:?}"
: "${EXPECTED_CAP_ARM:?}"
: "${EXPECTED_CAP_POSITION_ID:?}"
: "${EXPECTED_CAP_CELL:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$W/inputs"
RAW="$W/raw"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
mkdir -p "$W" "$ART" "$INPUTS" "$RAW"
: > "$RES"

say(){ echo "$*" | tee -a "$RES"; }
phase(){
  printf 'time_fr=%s\nphase=%s\n' \
    "$(TZ=Europe/Paris date --iso-8601=seconds)" "$1" > "$PROG"
  cp "$PROG" "$ART/PROGRESS.txt"
}
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?
  trap - EXIT
  set +e
  cp "$RES" "$ART/RESULTS.txt"
  cp "$PROG" "$ART/PROGRESS.txt"
  exit "$rc"
}
trap finalize EXIT

say "=== $JASS_JOB_ID -- salvage auditable 0908 sans replay ==="
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${SALVAGE_GO:-0}" = 1 ] || die "SALVAGE_GO=1 missing"
[ "${NO_REPLAY:-0}" = 1 ] || die "NO_REPLAY=1 missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "NO_AUTOMATIC_CONTINUATION=1 missing"
[ "${BOOTSTRAP:-10000}" -eq 10000 ] || die "bootstrap must remain 10000"
[ "${BOOTSTRAP_SEED:-271828}" -eq 271828 ] || die "bootstrap seed drift"

phase preflight
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
NPROC="$(nproc)"
[ "$NPROC" -eq 16 ] || die "CPX62 nproc drift: expected 16, got $NPROC"
FREE_MB="$(df -Pm /root | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -gt 3000 ] || die "free disk below 3 GiB"
say "preflight: nproc=$NPROC free_mb=$FREE_MB"
say "sizing: no games/build; fetch <1MiB + 10000 stratified bootstraps; ETA 2-5min; hard cap 10min"

phase smoke_tests
bash -n "$0"
python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/stable_conversion_matrix.py
python3 jobs/tests/test_stable_conversion_matrix.py > "$W/test-matrix.log" 2>&1 \
  || die "matrix/salvage round-trip tests failed"
python3 jobs/tests/test_salvage_stable_conversion_job.py > "$W/test-job.log" 2>&1 \
  || die "salvage job contract tests failed"
say "smoke: syntax + exact-one-cap salvage + sensitivity tests OK"

phase fetch_failed_source
SOURCE_ARTIFACT="artefacts/stable-top3-causal-matrix-partial.tar.gz"
SOURCE_TAR="$INPUTS/stable-top3-causal-matrix-partial.tar.gz"
python3 jobs/tools/fetch_result_files.py \
  --prefix "$SOURCE_0908_PREFIX" --expected-state failed \
  --file "$SOURCE_ARTIFACT=stable-top3-causal-matrix-partial.tar.gz" \
  --file artefacts/stable-top3.fen=stable-top3.fen \
  --file artefacts/stable-top3.proof.jsonl=stable-top3.proof.jsonl \
  --file artefacts/run-config.json=run-config.json \
  --out-dir "$INPUTS" --report "$ART/verified-failed-0908-source.json" \
  > "$W/fetch.log" 2>&1
[ "$(sha256sum "$SOURCE_TAR" | awk '{print $1}')" = "$SOURCE_PARTIAL_TAR_SHA256" ] \
  || die "pinned partial tar SHA256 mismatch"

python3 - "$SOURCE_TAR" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], "r:gz") as archive:
    members = archive.getmembers()
    if not members:
        raise SystemExit("empty raw matrix tar")
    for member in members:
        path = PurePosixPath(member.name)
        if (
            path.is_absolute() or ".." in path.parts
            or not path.parts or path.parts[0] != "matrix"
            or not (member.isfile() or member.isdir())
        ):
            raise SystemExit(f"unsafe tar member: {member.name!r}")
PY
tar -C "$RAW" -xzf "$SOURCE_TAR"
mapfile -d '' RESULT_FILES < <(
  find "$RAW/matrix" -type f -name 's*.jsonl' -print0 | sort -z
)
[ "${#RESULT_FILES[@]}" -eq 112 ] \
  || die "expected 112 shard JSONL files, got ${#RESULT_FILES[@]}"
say "source: failed 0908 authenticated; tar_sha256=$SOURCE_PARTIAL_TAR_SHA256; shard_files=112"

phase aggregate_salvage
python3 jobs/tools/stable_conversion_matrix.py salvage-single-ply-cap \
  --pool "$INPUTS/stable-top3.fen" \
  --proof "$INPUTS/stable-top3.proof.jsonl" \
  --inputs "${RESULT_FILES[@]}" \
  --run-config "$INPUTS/run-config.json" \
  --source-tar "$SOURCE_TAR" \
  --source-verification-report "$ART/verified-failed-0908-source.json" \
  --source-prefix "$SOURCE_0908_PREFIX" \
  --source-artifact-path "$SOURCE_ARTIFACT" \
  --expected-source-tar-sha256 "$SOURCE_PARTIAL_TAR_SHA256" \
  --expected-source-job-id "$SOURCE_0908_JOB_ID" \
  --expected-source-attempt-id "$SOURCE_0908_ATTEMPT_ID" \
  --expected-source-code-sha "$SOURCE_0908_CODE_SHA" \
  --expected-cap-arm "$EXPECTED_CAP_ARM" \
  --expected-cap-position-id "$EXPECTED_CAP_POSITION_ID" \
  --expected-cap-cell "$EXPECTED_CAP_CELL" \
  --expected-cap-plies 400 \
  --expected-per-arm 384 \
  --bootstrap-samples "${BOOTSTRAP:-10000}" \
  --bootstrap-seed "${BOOTSTRAP_SEED:-271828}" \
  --output "$ART/stable-top3-causal-matrix-salvage.json"

python3 - "$ART/stable-top3-causal-matrix-salvage.json" \
  "$ART/salvage-decision.json" "$ART/salvage-sensitivity.json" "$RES" <<'PY'
import json, sys
from pathlib import Path

source, decision_path, sensitivity_path, results_path = map(Path, sys.argv[1:])
report = json.loads(source.read_text(encoding="utf-8"))
if (
    report.get("status") != "salvage_complete"
    or not report.get("scientific_matrix_ready")
    or report.get("original_gate", {}).get("gate_ready")
    or report.get("matrix", {}).get("gate_ready")
    or not report.get("matrix", {}).get("derived_analysis_ready")
):
    raise SystemExit("salvage verdict contract failed")
if report.get("adjudication", {}).get("changes_to_raw_games") != 1:
    raise SystemExit("salvage did not change exactly one derived termination reason")

decision = {
    "schema": 1,
    "decision": "SALVAGE_CAUSAL_CONVERSION_MATRIX_READY",
    "original_0908_zero_cap_gate": "FAILED",
    "scientific_matrix_ready": True,
    "replay_performed": False,
    "adjudication": report["adjudication"],
    "authorization": report["authorization"],
}
decision_path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
sensitivity_path.write_text(
    json.dumps(report["sensitivity"], indent=2, sort_keys=True) + "\n"
)

matrix = report["matrix"]
lines = [
    "VERDICT=SALVAGE_CAUSAL_CONVERSION_MATRIX_READY",
    "original_0908_zero_cap_gate=FAILED",
    "replay_performed=false",
    "adjudicated_games=1",
]
for arm in matrix["contract"]["arms"]:
    stats = matrix["arms"][arm]["global"]
    lines.append(
        f"{arm}: n={stats['n']} W/D/L={stats['W']}/{stats['D']}/{stats['L']} "
        f"win={100*stats['win_rate']:.2f}% score={100*stats['score']:.2f}%"
    )
for name, value in matrix["paired_deltas"]["global"].items():
    lo, hi = value["ci95"]
    lines.append(
        f"delta_{name}={value['estimate']:+.6f} "
        f"ci95=[{lo:+.6f},{hi:+.6f}]"
    )
with results_path.open("a", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
PY

phase complete
say "artifacts: full salvage matrix + decision + sensitivity + authenticated source report"
say "training_continuation_authorized=false promotion_authorized=false automatic_next_job=null"
