#!/usr/bin/env bash
# L3 — sonde de débit contre Scan, avant la matrice de calibration.
#
# calibrate_vs_scan.py joue SÉQUENTIELLEMENT : une partie à la fois. Le
# parallélisme doit donc venir de l'exécution simultanée de plusieurs cellules,
# et le débit par cellule dépend fortement du régime (profondeur fixe contre
# cadence). Les seules ancres disponibles datent d'une autre box ; extrapoler de
# là serait la faute qui a coûté home-0665.
#
# Cette sonde mesure le débit réel des quatre régimes extrêmes sur HOME et
# publie une ETA chiffrée pour la matrice complète. Elle ne produit aucun
# verdict scientifique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SCAN_BIN:?}"; : "${EXPECTED_SCAN_SHA256:?}"
: "${CHAMPION_TRAIN_PREFIX:?}"; : "${EXPECTED_CHAMPION_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/cells"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=20
OPENING_SEED=1414214
PROBE_PAIRS=1
CELL_TIMEOUT=1500
CACHE_MB=128
CHAMPION_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
monitor

stage verify-pinned-scan-runtime
[ -x "$SCAN_BIN" ] || die "Scan binary missing at $SCAN_BIN"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary SHA mismatch — runtime is not the pinned one"
say "  runtime Scan ✓ figé : $EXPECTED_SCAN_SHA256"

stage fetch-champion-model
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=CHAMPION.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-champion-train.json" \
  > "$W/fetch-champion.log" 2>&1
python3 - "$ART/verified-champion-train.json" "$EXPECTED_CHAMPION_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
gunzip -c "$IN/CHAMPION.pjtw.gz" > "$W/CHAMPION.pjtw"
[ "$(sha256sum "$W/CHAMPION.pjtw" | awk '{print $1}')" = "$CHAMPION_MODEL_SHA" ] ||
  die "champion model hash drift"

stage build-and-test-8cf-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"

stage build-probe-opening-pool
"$J8" --gen-opening-pool "$NOPEN" "$W/open-probe.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/open-probe.log" 2>&1
# --gen-opening-pool écrit deux lignes d'en-tête commentées et annote chaque
# position après un '#'. calibrate_vs_scan strippe tout après '#' et ignore les
# lignes vides : on compte donc les positions comme lui, pas avec wc -l.
NPOS=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' \
  "$W/open-probe.fen")
[ "$NPOS" -eq "$NOPEN" ] || die "probe pool count drift: $NPOS != $NOPEN"
say "  pool sonde ✓ : $NPOS positions"

# Une cellule = un régime. Chaque cellule tourne en parallèle des autres, mais
# joue ses parties séquentiellement : c'est le comportement réel de l'outil.
run_cell(){
  local name="$1"; shift
  local start end rc
  start=$(date +%s)
  timeout "$CELL_TIMEOUT" python3 jobs/tools/calibrate_vs_scan.py \
    --jass "$J8" --scan "$SCAN_BIN" \
    --jass-pattern "$W/CHAMPION.pjtw" --jass-search-params "$Q00" \
    --jass-threads 1 --scan-book off --scan-bb-size 0 \
    --openings-file "$W/open-probe.fen" --pairs "$PROBE_PAIRS" \
    --max-plies 260 "$@" > "$W/cell-$name.log" 2>&1
  rc=$?
  end=$(date +%s)
  printf '%s %s %s\n' "$name" "$rc" "$((end - start))" > "$W/cell-$name.timing"
}

stage probe-four-regimes
pids=()
run_cell depth-d12-d12   --jass-depth 12 --scan-depth 12 & pids+=("$!")
run_cell depth-d10-d6    --jass-depth 10 --scan-depth 6  & pids+=("$!")
run_cell time-mt050-mt050 --jass-movetime 0.5 --scan-movetime 0.5 & pids+=("$!")
run_cell time-mt020-mt002 --jass-movetime 0.2 --scan-movetime 0.02 & pids+=("$!")
for pid in "${pids[@]}"; do wait "$pid" || true; done
say "  quatre régimes sondés (les timeouts sont une information, pas un échec)"

stage publish-rate-and-eta
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$NOPEN" "$PROBE_PAIRS" \
  "$CELL_TIMEOUT" <<'PY'
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
nopen, pairs, cell_timeout = (int(x) for x in sys.argv[4:7])
probe_games = nopen * 2 * pairs

cells = {}
for timing in sorted(w.glob("cell-*.timing")):
    name, rc, seconds = timing.read_text().split()
    rc, seconds = int(rc), int(seconds)
    log = (w / f"cell-{name}.log").read_text(errors="replace")
    m = re.search(r"Jass score rate:\s*([0-9.]+)", log)
    played = re.findall(r"^\s*game\s+(\d+):", log, re.M)
    completed = rc == 0
    games_done = probe_games if completed else (int(played[-1]) if played else 0)
    rate = games_done / (seconds / 60.0) if seconds > 0 and games_done else None
    cells[name] = {
        "completed": completed,
        "timed_out": rc == 124,
        "elapsed_s": seconds,
        "games_done": games_done,
        "games_per_minute": round(rate, 3) if rate else None,
        "score_rate": float(m.group(1)) if m and completed else None,
    }

def eta(rate, n):
    return round(n / rate, 1) if rate else None

# La matrice complète joue ses treize cellules en parallèle : le mur d'horloge
# est celui de la cellule la plus lente, pas la somme.
budget = {}
for n in (200, 400):
    per_cell = {
        name: eta(c["games_per_minute"], n) for name, c in cells.items()
    }
    known = [v for v in per_cell.values() if v]
    budget[f"n={n}"] = {
        "minutes_per_cell": per_cell,
        "wall_clock_if_parallel_min": round(max(known), 1) if known else None,
    }

payload = {
    "schema": 1,
    "verdict": "SCAN_PROBE_RATES_MEASURED",
    "code_sha": code_sha,
    "probe": {
        "games_per_cell": probe_games,
        "openings": nopen,
        "pairs": pairs,
        "cell_timeout_s": cell_timeout,
        "tool_is_sequential": True,
        "parallelism": "one process per cell",
    },
    "cells": cells,
    "matrix_budget": budget,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "scan-probe.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__SCAN_PROBE_RATES_MEASURED").write_text(
    "SCAN_PROBE_RATES_MEASURED\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
for name, c in sorted(cells.items()):
    print(
        f"  {name:20s} {'OK ' if c['completed'] else 'TIMEOUT'} "
        f"{c['games_done']:>3}/{probe_games} parties en {c['elapsed_s']:>4}s "
        f"-> {c['games_per_minute']} parties/min"
    )
PY
cp "$W"/cell-*.timing "$ART/cells/" 2>/dev/null || true
stage complete
say "SCAN_PROBE_RATES_MEASURED promotion=false automatic_next_job=null"
