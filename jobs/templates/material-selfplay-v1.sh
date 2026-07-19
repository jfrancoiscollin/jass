#!/usr/bin/env bash
# template: fixed-material self-play conversion (Scan vs gen2-mmto) v1
# description: sample N men-only BIGxSMALL positions, self-play each engine
#              (Scan-vs-Scan, gen2-vs-gen2) at fixed depth, tally W/D/L from the
#              material-up side. N_PLAY small = probe (validate + rate); N_PLAY
#              100 = full experiment.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?wrapper must pin the reviewed develop SHA}"
N_PLAY="${N_PLAY:-10}"; NSHARDS="${NSHARDS:-5}"; DEPTH="${DEPTH:-10}"
BIG="${BIG:-20}"; SMALL="${SMALL:-18}"; MAXPLIES="${MAXPLIES:-400}"
SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
CORPUS_PREFIXES=(
  "r2:jass-data/runs/cpx62-0817-l3-c2x1-hhh-control-v1/20260718T221711Z-7a35084f"
  "r2:jass-data/runs/cpx62-0818-l3-c2x1-llh-v1/20260718T222242Z-7a35084f"
)
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; INPUTS="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$INPUTS"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }
RES="$W/RESULTS.txt"; : > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt";
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true;
  rm -rf "$W/build" 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — fixed-material self-play (${BIG}v${SMALL}) Scan vs gen2 — N_PLAY=$N_PLAY d$DEPTH ==="
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
ACTUAL_SHA="$(git rev-parse HEAD)"; [ "$ACTUAL_SHA" = "$EXPECTED_CODE_SHA" ] || die "code SHA $ACTUAL_SHA != $EXPECTED_CODE_SHA"
NPROC="$(nproc)"; FREE_MB="$(df -Pm "$JASS_RESULT_DIR"|awk 'NR==2{print $4}')"; [ "${FREE_MB:-0}" -ge 5000 ] || die "<5GiB free"
[ "$NSHARDS" -le "$NPROC" ] || die "NSHARDS=$NSHARDS exceeds nproc=$NPROC"
say "preflight: nproc=$NPROC free_mb=$FREE_MB nshards=$NSHARDS depth=$DEPTH"

python3 -m py_compile tools/calibrate_vs_scan.py tools/selfplay_material_wdl.py \
  tools/sample_material_fen.py jobs/tools/fetch_result_files.py jobs/tools/fetch_t1bis_inputs.py

# --- gen2-mmto engine: v4 (32cf) geometry + champion flags + gen2 pattern ---
say "stage=build-jass-v4"
for s in src/scan_eval.cpp src/search.cpp src/movegen.cpp; do
  git show "HEAD:$s" > "$W/exp-$(basename "$s")"; cmp -s "$s" "$W/exp-$(basename "$s")" || die "$s differs from pinned HEAD"; done
grep -q g_emasks src/scan_eval.cpp || die "scan_eval guard"; grep -q has_any_capture src/search.cpp || die "search guard"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen-v4.log" 2>&1
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1; grep -q 'EXTERNAL EGDB ENABLED' "$W/cmake.log" || die "no EGDB"
cmake --build "$W/build" -j"${JASS_BUILD_JOBS:-8}" --target jass > "$W/build.log" 2>&1 || die "jass build"
JASS="$W/build/jass"

# --- Scan engine: prebuilt binary from rhalbersma/scan (data + scan.ini included) ---
say "stage=fetch-scan"
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan > "$W/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || die "Scan binary unavailable at $SCAN_BIN"

# --- gen2 pattern ---
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$INPUTS" --report "$ART/verified-inputs.json" > "$W/fetch-inputs.log" 2>&1 || die "gen2 inputs unavailable"
gunzip -c "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"; [ -s "$W/gen2.pjtw" ] || die "gen2 pattern missing"

# --- sample N_PLAY men-only BIGxSMALL positions ---
say "stage=sample-positions"
DATA=(); i=0
for P in "${CORPUS_PREFIXES[@]}"; do
  python3 jobs/tools/fetch_result_files.py --prefix "$P" \
    --file artefacts/g1-selfplay.jnnw.gz=c${i}-g1.jnnw.gz \
    --file artefacts/g2-selfplay.jnnw.gz=c${i}-g2.jnnw.gz \
    --expected-state completed --out-dir "$W" --report "$ART/verified-c${i}.json" > "$W/fetch-c${i}.log" 2>&1 || die "corpus fetch $P"
  gunzip -c "$W/c${i}-g1.jnnw.gz" > "$W/c${i}-g1.jnnw"; gunzip -c "$W/c${i}-g2.jnnw.gz" > "$W/c${i}-g2.jnnw"
  DATA+=("$W/c${i}-g1.jnnw" "$W/c${i}-g2.jnnw"); i=$((i+1))
done
python3 tools/sample_material_fen.py --input "${DATA[@]}" --big "$BIG" --small "$SMALL" \
  --count "$N_PLAY" --out "$ART/positions.fen" > "$W/sample.log" 2>&1 || die "position sampling failed"
say "  $(cat "$W/sample.log")"

run_engine(){ # $1 = jass|scan
  local eng="$1"; local -a pids=() outs=(); local sh t0 t1
  t0=$(date +%s)
  for sh in $(seq 0 $((NSHARDS-1))); do
    local out="$W/${eng}.wdl.${sh}.json"; outs+=("$out")
    if [ "$eng" = jass ]; then
      python3 tools/selfplay_material_wdl.py --engine jass --jass "$JASS" --jass-pattern "$W/gen2.pjtw" \
        --positions "$ART/positions.fen" --big "$BIG" --depth "$DEPTH" --max-plies "$MAXPLIES" \
        --shard "$sh" --nshards "$NSHARDS" --out "$out" > "$W/${eng}.${sh}.log" 2>&1 &
    else
      python3 tools/selfplay_material_wdl.py --engine scan --jass "$JASS" --scan "$SCAN_BIN" \
        --positions "$ART/positions.fen" --big "$BIG" --depth "$DEPTH" --max-plies "$MAXPLIES" \
        --shard "$sh" --nshards "$NSHARDS" --out "$out" > "$W/${eng}.${sh}.log" 2>&1 &
    fi
    pids+=("$!")
  done
  local fail=0; for p in "${pids[@]}"; do wait "$p" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$eng: $fail shard(s) failed"
  t1=$(date +%s)
  python3 - "$eng" "$((t1-t0))" "$ART/${eng}-wdl.json" "${outs[@]}" <<'PY'
import json,sys
eng,wall,out=sys.argv[1],int(sys.argv[2]),sys.argv[3]; shards=sys.argv[4:]
tally={"W":0,"D":0,"L":0}; per=[]
for s in shards:
    d=json.load(open(s))
    for k in tally: tally[k]+=d["tally_up_side"][k]
    per+=d["per_position"]
n=sum(tally.values())
rep={"engine":eng,"n":n,"wall_s":wall,"sec_per_game":round(wall/n,2) if n else None,
     "tally_up_side":tally,"pct_up_side":{k:round(100*v/n,2) for k,v in tally.items()} if n else {},
     "per_position":sorted(per,key=lambda x:x["index"])}
json.dump(rep,open(out,"w"),indent=2,sort_keys=True)
print(json.dumps({k:rep[k] for k in("engine","n","wall_s","sec_per_game","tally_up_side","pct_up_side")},sort_keys=True))
PY
}

say "stage=selfplay-scan"; SCAN_LINE="$(run_engine scan)"; say "  SCAN: $SCAN_LINE"
say "stage=selfplay-gen2"; JASS_LINE="$(run_engine jass)"; say "  GEN2: $JASS_LINE"

python3 - "$ART/scan-wdl.json" "$ART/jass-wdl.json" "$ART/material-selfplay-summary.json" "$ART/c0-decision.json" "$BIG" "$SMALL" "$DEPTH" <<'PY'
import json,sys
scan=json.load(open(sys.argv[1])); gen2=json.load(open(sys.argv[2]))
summ={"experiment":f"material-selfplay-{sys.argv[5]}v{sys.argv[6]}","depth":int(sys.argv[7]),
      "perspective":"material_up_side","scan":{k:scan[k] for k in("n","tally_up_side","pct_up_side","sec_per_game")},
      "gen2_mmto":{k:gen2[k] for k in("n","tally_up_side","pct_up_side","sec_per_game")}}
json.dump(summ,open(sys.argv[3],"w"),indent=2,sort_keys=True)
json.dump(summ,open(sys.argv[4],"w"),indent=2,sort_keys=True)  # allowlisted inline
print(json.dumps(summ,sort_keys=True))
PY
cat "$ART/material-selfplay-summary.json" | tee -a "$RES"
say "=== material self-play complete ==="
