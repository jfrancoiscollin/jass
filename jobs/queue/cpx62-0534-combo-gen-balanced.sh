#!/usr/bin/env bash
# id: cpx62-0534-combo-gen-balanced
# description: MATÉRIAU DE BASE combos — génération ÉQUILIBRÉE (demande JFC "équilibré") de combos FORCÉS vérifiés, gradués
# par TEMPI, quota ÉGAL par bin (3→11). 0531 n'avait que 403 combos (trop peu pour un signal d'entraînement) ; ici on scanne
# beaucoup plus de parties Scan-vs-Scan (corpus 0328, milieu 14-40p), --per-bin élevé => corpus combos balancé, réutilisable
# comme socle de la base d'apprentissage (étape 1/3 : matériau ; puis assemblage base+contraste 0328 ; puis fit FM vs linéaire).
# Rappel cadrage : base-résultat SEULE = plate (0329 covariate-shift) ; le levier NON-tenté = concentration combos + FM
# (interactions de motifs, que le linéaire ne peut encoder). AUCUN NNUE. expected_duration: ~2-4 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0534-combo-gen-balanced/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-combobal; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CORPUS=jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
DEEP=16; MAXTEMPI=12; PER_BIN=40; LIMIT=4000; PLO=14; PHI=40

say "=== génération ÉQUILIBRÉE de combos (matériau de base, gradué par tempi) ==="
python3 tools/gen_combinations.py --self-test 2>&1 | tee -a "$RES" || { say "ABORT self-test"; exit 3; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 5; }
[ -f "$CORPUS" ] || { say "ABORT: corpus Scan-selfplay absent"; exit 4; }
NREC=$(python3 -c "import struct;print(struct.unpack('<I',open('$CORPUS','rb').read(8)[4:8])[0])")
say "  corpus ${NREC} pos ; ${NCPU} shards //, limite ${LIMIT}/shard, per-bin ${PER_BIN}/shard (équilibré), deep ${DEEP}"

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
[ "$rc" -eq 0 ] || say "  (un shard a fini en erreur — on fusionne ce qui existe)"
SUITE="$ART/combos_balanced.fen"; cat "$W"/shard_*.fen > "$SUITE" 2>/dev/null || true
NC=$(grep -cvE '^\s*(#|$)' "$SUITE" 2>/dev/null || echo 0)
[ "${NC:-0}" -ge 1 ] || { say "ABORT: aucune combo"; tail -4 "$W"/gen_0.log|sed 's/^/  /'; exit 7; }
say "  suite : ${NC} combos (matériau de base)"
say "  répartition ÉQUILIBRÉE par tempi :"
python3 - "$SUITE" <<'PY' 2>&1 | tee -a "$RES"
import sys,re,collections
c=collections.Counter()
for ln in open(sys.argv[1]):
    m=re.search(r'tempi=(\d+)',ln)
    if m: c[int(m.group(1))]+=1
for t in sorted(c): print(f"    {t:2d} tempi : {c[t]} combos")
print(f"    TOTAL : {sum(c.values())}")
PY

say ""
say "================= SUITE DU PLAN (base d'apprentissage combos) ================="
say "  1/3 [CE JOB] : matériau = combos vérifiés balancés par tempi (artefacts/combos_balanced.fen)."
say "  2/3 : assembler la BASE = combos (concentrés, label attaquant-gagne) + corpus 0328 (contraste résultat) + précurseurs."
say "  3/3 : fm_fitcheck (FM réduit-il le résidu sur cette base ?) -> si oui, fit PJTW v4 (linéaire+FM) -> juge 0440+détection."
say "  Honnête : base-résultat SEULE = plate (0329) ; le pari NON-tenté = concentration combos + FM (interactions de motifs)."
say "==========================================================================="
