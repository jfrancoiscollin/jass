#!/usr/bin/env bash
# Launcher T1-bis ADJ+G1 rv3 — runner v3 (code=develop, inputs R2, artefacts→R2).
#
# Rôle identique au v2-launch : manifests de gates n=0 fail-closed, worker de
# gates en parallèle du runner principal, remplacement atomique. S'y ajoutent :
#   * récupération des inputs data depuis R2 + vérification sha256 fail-closed
#     (manifest.json produit par le job de publication des inputs) ;
#   * scratch hors du worktree ET hors des artefacts (les shards ne sont pas
#     publiés ; RESULTS.txt et manifests le sont) ;
#   * en cas d'échec, la queue des logs de travail est copiée dans les
#     artefacts pour être publiée par le finalize du runner.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_OBJSTORE_REMOTE:?runner v3 must provide JASS_OBJSTORE_REMOTE}"
cd "$JASS_CODE_DIR"

JOB_ID="${JOB_ID:?export JOB_ID}"
NSH_GATE="${NSH_GATE:-$(nproc)}"
DEPTH="${DEPTH:-9}"
PAIRS="${PAIRS:-1}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
GATE_WAIT_S="${GATE_WAIT_S:-28800}"
RCLONE="${RCLONE_BIN:-rclone}"
T1BIS_INPUTS_URI="${T1BIS_INPUTS_URI:-${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1}"

SCRATCH_ROOT="${T1BIS_SCRATCH_ROOT:-/var/lib/jass-runner}"
SCRATCH="$SCRATCH_ROOT/t1bis-$JOB_ID"
rm -rf "$SCRATCH"
export T1BIS_W="$SCRATCH/w"
export T1BIS_GEOM="$SCRATCH/geom"
export T1BIS_INPUTS_DIR="$SCRATCH/inputs"
mkdir -p "$T1BIS_W" "$T1BIS_GEOM" "$T1BIS_INPUTS_DIR"
W="$T1BIS_W"

publish_logs_on_error(){
  rc=$?
  set +e
  mkdir -p "$JASS_ARTEFACT_DIR/logs"
  for f in "$W"/*.log; do
    [ -e "$f" ] || continue
    tail -n 120 "$f" > "$JASS_ARTEFACT_DIR/logs/$(basename "$f").tail" 2>/dev/null
  done
  exit "$rc"
}
trap publish_logs_on_error ERR

# --- Inputs R2 : manifest sha256 fail-closed -------------------------------
"$RCLONE" copyto "$T1BIS_INPUTS_URI/manifest.json" "$T1BIS_INPUTS_DIR/manifest.json"
test -s "$T1BIS_INPUTS_DIR/manifest.json"
export T1BIS_INPUTS_URI
python3 - <<'PY'
from __future__ import annotations
import hashlib, json, os, pathlib, subprocess

indir = pathlib.Path(os.environ['T1BIS_INPUTS_DIR'])
uri = os.environ['T1BIS_INPUTS_URI']
rclone = os.environ.get('RCLONE_BIN', 'rclone')
manifest = json.loads((indir / 'manifest.json').read_text())
files = manifest.get('files') or []
if not files:
    raise SystemExit('manifest inputs vide')
for rec in files:
    name, want_sha, want_size = rec['name'], rec['sha256'], int(rec['size_bytes'])
    if '/' in name or name.startswith('.'):
        raise SystemExit(f'nom input invalide: {name}')
    dest = indir / name
    subprocess.run([rclone, 'copyto', f'{uri}/{name}', str(dest)], check=True)
    data = dest.read_bytes()
    if len(data) != want_size:
        raise SystemExit(f'{name}: taille {len(data)} != {want_size}')
    got = hashlib.sha256(data).hexdigest()
    if got != want_sha:
        raise SystemExit(f'{name}: sha256 {got} != {want_sha}')
print(f'inputs vérifiés: {len(files)} fichiers')
PY

# --- Manifests techniques initiaux : n=0 => promotion fail-closed ----------
cat > "$W/gate_parent.json" <<'JSON'
{"wins_a":0,"draws":0,"wins_b":0,"n":0,"rate":null,"ci_low":null,"ci_high":null,"complete":false}
JSON
cp "$W/gate_parent.json" "$W/gate_fixed.json"

python3 jobs/tests/test_run_jass_gate.py > "$W/test_run_jass_gate.log" 2>&1

# --- Worker de gates : démarre dès que le candidat existe ------------------
(
  set -euo pipefail
  for _ in $(seq 1 "$GATE_WAIT_S"); do
    if [ -s "$W/build/jass" ] && [ -s "$W/candidate.pjtw" ] && \
       [ -s "$W/parent.pjtw" ] && [ -s "$W/fixed.pjtw" ] && [ -s "$W/open.fen" ]; then
      break
    fi
    sleep 1
  done
  [ -s "$W/candidate.pjtw" ] || exit 21

  python3 jobs/tools/run_jass_gate.py \
    --jass "$W/build/jass" \
    --pattern-a "$W/candidate.pjtw" \
    --pattern-b "$W/parent.pjtw" \
    --openings-file "$W/open.fen" \
    --search-params "$QS" --depth "$DEPTH" --pairs "$PAIRS" \
    --nshards "$NSH_GATE" --timeout "$SHARD_TIMEOUT" \
    --work-dir "$W/gate-parent" --out "$W/gate_parent.new.json"
  mv "$W/gate_parent.new.json" "$W/gate_parent.json"

  if cmp -s "$W/parent.pjtw" "$W/fixed.pjtw"; then
    cp "$W/gate_parent.json" "$W/gate_fixed.json"
  else
    python3 jobs/tools/run_jass_gate.py \
      --jass "$W/build/jass" \
      --pattern-a "$W/candidate.pjtw" \
      --pattern-b "$W/fixed.pjtw" \
      --openings-file "$W/open.fen" \
      --search-params "$QS" --depth "$DEPTH" --pairs "$PAIRS" \
      --nshards "$NSH_GATE" --timeout "$SHARD_TIMEOUT" \
      --work-dir "$W/gate-fixed" --out "$W/gate_fixed.new.json"
    mv "$W/gate_fixed.new.json" "$W/gate_fixed.json"
  fi
) >"$W/gate-worker.log" 2>&1 &
GATE_WORKER_PID=$!

cleanup(){
  if kill -0 "$GATE_WORKER_PID" 2>/dev/null; then
    kill "$GATE_WORKER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

bash jobs/templates/t1bis-adj-g1-rv3.sh
wait "$GATE_WORKER_PID" || {
  echo "WARN: gate worker failed; promotion should already be stop_technical" >&2
  exit 4
}
rm -rf "$SCRATCH"
