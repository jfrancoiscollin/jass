#!/usr/bin/env bash
# id: cpx62-0531-combo-scaleup
# description: SCALE-UP du générateur de combinaisons (suite au fix grading-par-tempi, demande JFC). Source = parties de
# SCAN CONTRE LUI-MÊME (corpus 0328), filtrées MILIEU (14-40 pièces). NCPU shards // du générateur -> combos FORCÉS
# (sac -> gain net >=1 homme/dame) GRADUÉS PAR TEMPI (2..12), quota par longueur (--per-bin). Puis TEST DE DÉTECTION jass
# par bin de tempi (élagage ON/OFF, d=tempi/tempi+2/20) = la courbe "capte-t-on les combos de N temps de façon quasi-certaine".
# AUCUN NNUE. expected_duration: ~1-3 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0531-combo-scaleup/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-comboscale; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
CORPUS=jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
DEEP=16; MAXTEMPI=12; PER_BIN=8; LIMIT=600; PLO=14; PHI=40

say "=== SCALE-UP générateur de combinaisons (gradué par tempi) ==="
python3 tools/gen_combinations.py --self-test 2>&1 | tee -a "$RES" || { say "ABORT self-test"; exit 3; }

say "=== build jass (egdb ON) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 5; }
[ -f "$CORPUS" ] || { say "ABORT: corpus Scan-selfplay absent $CORPUS"; exit 4; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ"; exit 4; }
NREC=$(python3 -c "import struct;print(struct.unpack('<I',open('$CORPUS','rb').read(8)[4:8])[0])")
say "  corpus Scan-selfplay : ${NREC} positions ; ${NCPU} shards //, limite ${LIMIT}/shard, per-bin ${PER_BIN}/shard, deep ${DEEP}"

say "=== génère les combos gradués (parallèle, source Scan-vs-Scan milieu ${PLO}-${PHI}p) ==="
SLICE=$(( (NREC + NCPU - 1) / NCPU ))
pids=(); rc=0
for i in $(seq 0 $((NCPU-1))); do
    ST=$(( i * SLICE ))
    python3 tools/gen_combinations.py --scan "$SCAN_BIN" --jass "$J" --jnnw "$CORPUS" \
        --start "$ST" --max-records "$SLICE" --piece-lo "$PLO" --piece-hi "$PHI" \
        --deep "$DEEP" --max-tempi "$MAXTEMPI" --per-bin "$PER_BIN" --limit "$LIMIT" \
        --out-fens "$W/shard_$i.fen" >"$W/gen_$i.log" 2>&1 &
    pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || rc=1; done
[ "$rc" -eq 0 ] || say "  (au moins un shard a fini en erreur — on fusionne ce qui existe)"
SUITE="$ART/combos_graded.fen"
cat "$W"/shard_*.fen > "$SUITE" 2>/dev/null || true
NC=$(grep -cvE '^\s*(#|$)' "$SUITE" 2>/dev/null || echo 0)
[ "${NC:-0}" -ge 1 ] || { say "ABORT: aucune combo générée"; tail -4 "$W"/gen_0.log|sed 's/^/  /'; exit 7; }
say "  suite : ${NC} combos gradués"
say "  répartition par tempi :"
grep -oE 'tempi=[0-9]+' "$SUITE" | sort | uniq -c | sort -k2 -t= -n | sed 's/^/    /' | tee -a "$RES"

say ""
say "=== TEST DE DÉTECTION jass par bin de tempi (élagage ON vs OFF, temps-agnostique) ==="
export JASS="$J" CHAMP="$W/champ.pjtw" SUITE="$SUITE" MAXT="$MAXTEMPI"
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
J=os.environ["JASS"]; CH=os.environ["CHAMP"]; SUITE=os.environ["SUITE"]; MAXT=int(os.environ["MAXT"])
combos=[]
for ln in open(SUITE):
    if '#' not in ln: continue
    fen,meta=ln.split('#',1); fen=fen.strip(); m=dict(re.findall(r'(\w+)=([^\s]+)',meta))
    if 'tempi' in m and m.get('win'):
        combos.append((fen,int(m['tempi']),m['win']))
print(f"  {len(combos)} combos testés")
ELAG={'ON':'', 'OFF':'multicut_min_depth=0,razor_max_depth=0,lmp_min_depth=0'}
def rate(cb, depth, params):
    if not cb: return None
    eng=JassEngine(J, pattern_path=CH, no_book=True, search_params=params) if params else JassEngine(J, pattern_path=CH, no_book=True)
    hit=0
    for fen,t,win in cb:
        try:
            eng.set_position_fen(fen); mv=eng.go(depth=depth)
            if mv is not None and mv.jass_str()==win: hit+=1
        except Exception: pass
    eng.close(); return hit/len(cb)
def f(x): return "n/a" if x is None else f"{x:.2f}"
print(f"  {'tempi':>5} {'n':>4} {'det@T(ON)':>10} {'det@T(OFF)':>11} {'det@T+2(ON)':>12} {'det@20(ON)':>11} {'det@20(OFF)':>12}")
for t in range(2,MAXT+1):
    cb=[c for c in combos if c[1]==t]
    if not cb: continue
    print(f"  {t:>5} {len(cb):>4} {f(rate(cb,t,ELAG['ON'])):>10} {f(rate(cb,t,ELAG['OFF'])):>11} "
          f"{f(rate(cb,min(t+2,20),ELAG['ON'])):>12} {f(rate(cb,20,ELAG['ON'])):>11} {f(rate(cb,20,ELAG['OFF'])):>12}")
PY

say ""
say "================= LECTURE ================="
say "  Objectif JFC : det ~1.00 par bin de tempi à d>=tempi (+ marge) => moteur capte les combos de N temps quasi à coup sûr."
say "  det<1 à d=20 AVEC OFF>ON => trou d'élagage (à réparer). det<1 même OFF => détection tactique manquante (comme 0529)."
say "  Suite gradée réutilisable : artefacts/combos_graded.fen (curriculum contrôlé par tempi + jauge de détection)."
say "==========================================="
