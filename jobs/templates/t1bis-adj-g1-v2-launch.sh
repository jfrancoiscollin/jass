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

# Durcissement runtime du runner principal. Le remplacement est volontairement
# vérifié : si le template diverge, on échoue avant tout calcul scientifique.
python3 - <<'PY'
from pathlib import Path

path = Path("jobs/templates/t1bis-adj-g1-v2.sh")
text = path.read_text(encoding="utf-8")

old_set = "set -euo pipefail"
new_set = "set -Eeuo pipefail"
if text.count(old_set) != 1:
    raise SystemExit(f"template inattendu: set -euo pipefail occurrences={text.count(old_set)}")
text = text.replace(old_set, new_set, 1)

old_diag = '''say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
'''
new_diag = '''say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
'''
if text.count(old_diag) != 1:
    raise SystemExit(f"template inattendu: bloc diagnostic occurrences={text.count(old_diag)}")
text = text.replace(old_diag, new_diag, 1)

old_openings = '''grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"'''
new_openings = '''awk -v limit="$NOPEN" '\n  /^[[:space:]]*#/ { next }\n  {\n    sub(/#.*/, "")\n    if (NF) {\n      print\n      count++\n      if (count >= limit) exit\n    }\n  }\n' data/dilf_combinations.fen > "$W/open.fen"\n[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "openings insuffisantes: $(wc -l < "$W/open.fen")/$NOPEN"'''
if text.count(old_openings) != 1:
    raise SystemExit(f"template inattendu: pipeline openings occurrences={text.count(old_openings)}")
text = text.replace(old_openings, new_openings, 1)

path.write_text(text, encoding="utf-8")
PY
bash -n jobs/templates/t1bis-adj-g1-v2.sh

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
