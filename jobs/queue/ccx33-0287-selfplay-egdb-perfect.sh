#!/usr/bin/env bash
# id: ccx33-0287-selfplay-egdb-perfect
# description: CULMINATION du track finale. 0276 (features) a donné +28 Elo mais n'a PAS cassé le
# verrou roi-finale (endgame-rois ~3.06, vs Scan -800). La bitbase est SCELLÉE (self-test natif egdb
# 164/164, job 0286). Hypothèse : le verrou self-play = la recherche jouait les finales avec une éval
# IMPARFAITE → les parties atteignaient de mauvais résultats de finale → l'éval s'entraînait sur ses
# propres erreurs. Ici : réplique EXACTE de 0276 (king-aware + ENDGAME_FEATURES, NMP-off, play depth-8
# UNIFORME, 600k ×8) MAIS la GÉNÉRATION self-play est buildée -DJASS_EGDB=ON + JASS_EGDB_PATH → la
# recherche joue les finales ≤7 pièces PARFAITEMENT (probe TB) → labels WDL de finale = VÉRITÉ EXACTE.
# egdb est ON UNIQUEMENT pour la génération (env inline sur --gen-data-wdl) ; OFF pour TOUS les
# benchmarks (Elo vs hc, vs Scan, dump-features, train) → on mesure si l'ÉVAL elle-même apprend mieux
# les finales (généralisation), pas le TB qui gonfle le jeu. Si endgame-rois chute nettement sous
# 0276 (3.06) → le verrou cède : la couverture-par-jeu-parfait était la clé (≫ labels depth-16 de 0274).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0287-selfplay-egdb-perfect/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
EGDB_DB=/root/egdb_extracted/app
EGDB_CACHE=256

# --- base + sources egdb présentes (sinon on n'a pas le droit de tourner) ---
ls "$EGDB_DB"/db2.idx1 "$EGDB_DB"/db5.idx1 >/dev/null 2>&1 || { echo "ABORT: base egdb absente dans $EGDB_DB"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

# --- build self-play : king-aware + features + EGDB from-source ---
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON \
      -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
grep -q "ENDGAME FEATURES ENABLED" "$ART/cmake.log" || { echo "ABORT: features pas activées"; exit 5; }
grep -q "EXTERNAL EGDB ENABLED"     "$ART/cmake.log" || { echo "ABORT: egdb pas activé"; exit 5; }
grep -q "eg_pieces  = 40" src/search_params.hpp && echo "binaire = NMP OFF" || echo "WARNING: NMP pas off"
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- pré-vol : egdb DOIT s'engager (sinon expérience bidon) ---
echo "=== pré-vol egdb (selfcheck invariant) ==="
"$JASS" --egdb-selfcheck "$EGDB_DB" 3000 2>&1 | tail -4
"$JASS" --egdb-selfcheck "$EGDB_DB" 1 >/dev/null 2>&1 || { echo "ABORT: egdb ne s'ouvre pas"; exit 6; }

EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=600000; NGEN=8; BD=9; EPAIRS=15
CFOLD="--full-fold --king-patterns"
declare -A ELO EGM
echo "PARAMS: play_depth=$PLAY_DEPTH UNIFORME + ENDGAME FEATURES + EGDB-PERFECT play (gen only) + --lowmem  $NPER/gen ×$NGEN"

fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$3.pjtw" >"$3-train.log" 2>&1; }
val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"   # egdb OFF ici (pas de JASS_EGDB_PATH) = éval pure
  $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"
}
# génération : egdb ON via env INLINE sur --gen-data-wdl uniquement (finales jouées parfaites)
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    JASS_EGDB_PATH="$EGDB_DB" JASS_EGDB_CACHE_MB="$EGDB_CACHE" \
      $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) "$@" >"${OUTP}-$s.log" 2>&1 &
  done; wait
  python3 - "$OUTP" "$CUM" <<'PY'
import struct,glob,sys,re,os
outp,cum=sys.argv[1],sys.argv[2]; REC=38
shards=sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1)))
body=b""; add=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
if os.path.exists(cum):
    raw=open(cum,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(cum,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+add)); o.close(); print("cumulative",old+add)
else:
    o=open(cum,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',add)); o.write(body); o.close(); print("cumulative",add)
PY
  rm -f "${OUTP}-"*.jnnw
}

CUM="$ART/cumulative.jnnw"
echo "=== gen0 : seed (300k, play depth-8 EGDB-perfect, l2=3e-2) ==="
gen_and_append 300000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -8 "$ART/gen0-train.log"; exit 7; }
EGM[0]=$(val_endgame "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS"); echo "  gen0 val_endgame=${EGM[0]} Elo=${ELO[0]}"
case "${ELO[0]}" in 0-0-0*) echo "ABORT desync"; exit 8;; esac

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} (play depth-8 EGDB-perfect) avec gen$((g-1)) → cumulé → logistic (features+lowmem) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -8 "$ART/gen$g-train.log"; exit 7; }
  EGM[$g]=$(val_endgame "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS"); echo "  gen$g val_endgame=${EGM[$g]} Elo=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60p) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

# --- verdict + AUTOPSIE FINALE vs Scan (egdb OFF = éval pure) ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone Scan échoué)"; chmod +x "$SCAN_BIN" 2>/dev/null || true; fi
SCAN5=""; AUTOP=""
if [ -x "$SCAN_BIN" ]; then
  GAMES="$ART/games"; mkdir -p "$GAMES"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" \
      --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" \
      --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err" || echo "(autopsie skip)"
  AUTOP=$(sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12)
fi

echo; echo "=========================================================="
echo "   ccx33-0287 — SELF-PLAY EGDB-PERFECT (finales jouées par la bitbase, labels exacts)"
echo "----------------------------------------------------------"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}   val_endgame_mse=${EGM[$g]}"; done
echo "  gen${NGEN} (60p) vs hc : $ELOF   [0276 features-sans-egdb = +230 ; 0266 = +201.7]"
[ -n "$SCAN5" ] && echo "  gen${NGEN} vs Scan mt0.5 : $SCAN5"
echo "----------------------------------------------------------"
echo "  AUTOPSIE FINALE (perte phase×rois vs Scan ; comparer 0276=3.06, 0275 distill=3.22, 0266~3.x) :"
echo "$AUTOP"
echo "----------------------------------------------------------"
echo "  endgame-rois NETTEMENT < 3.06 (0276) → le jeu-parfait-finale CASSE le verrou : la couverture"
echo "     par labels EXACTS était la clé → on garde egdb dans la boucle de prod + on re-baseline vs Scan."
echo "  endgame-rois ~3.06 → même le jeu parfait ne suffit pas : le verrou est la CAPACITÉ de l'éval"
echo "     (le PST/features ne peuvent pas représenter la finale-rois) → piste archi éval."
echo "=========================================================="
