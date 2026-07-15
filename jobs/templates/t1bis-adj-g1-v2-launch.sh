#!/usr/bin/env bash
# Wrapper d'instanciation du runner T1-bis v2.
#
# Il lance les deux gates dès que le candidat est disponible, pendant que le
# runner principal mesure p1-p4. Les manifests sont remplacés atomiquement.
# En cas de retard/échec du worker, les fichiers initiaux n=0 provoquent un
# stop_technical fail-closed — jamais un faux PASS.
set -euo pipefail
cd /root/jass

JOB_ID="${JOB_ID:?export JOB_ID}"
PARENT_PJTW_GZ="${PARENT_PJTW_GZ:?export PARENT_PJTW_GZ}"
FIXED_PJTW_GZ="${FIXED_PJTW_GZ:-$PARENT_PJTW_GZ}"
NSH_GATE="${NSH_GATE:-$(nproc)}"
DEPTH="${DEPTH:-9}"
PAIRS="${PAIRS:-1}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"

W="/root/cw-$JOB_ID"
mkdir -p "$W"

# Manifests techniques initiaux : JSON valide, mais n=0 => promotion rejetée si
# le worker n'a pas fini. Écriture atomique du vrai résultat ensuite.
cat > "$W/gate_parent.json" <<'JSON'
{"wins_a":0,"draws":0,"wins_b":0,"n":0,"rate":null,"ci_low":null,"ci_high":null,"complete":false}
JSON
cp "$W/gate_parent.json" "$W/gate_fixed.json"

python3 jobs/tests/test_run_jass_gate.py >/tmp/test_run_jass_gate.log 2>&1

(
  set -euo pipefail
  # Le runner principal crée ces fichiers après build/fit.
  for _ in $(seq 1 7200); do
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

bash jobs/templates/t1bis-adj-g1-v2.sh
wait "$GATE_WORKER_PID" || {
  echo "WARN: gate worker failed; promotion should already be stop_technical" >&2
  exit 4
}
