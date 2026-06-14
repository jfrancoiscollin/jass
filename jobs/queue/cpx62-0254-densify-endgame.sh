#!/usr/bin/env bash
# id: cpx62-0254-densify-endgame
# description: BOUCLE DE DENSIFICATION FINALE — pousser la classe linéaire king-aware en
# attaquant la phase faible (finale) sur les DEUX fronts que les diagnostics ont validés :
#   * 0251 : la classe RANGE bien la finale sur labels parfaits (spearman 0.73-0.79) → PAS
#     class-limited ; notre éval self-play est juste MAL ENTRAÎNÉE en finale (labels depth-4).
#   * 0252 : la finale est SEARCH-BOUND — éval pure (depth-1) catastrophique (perte 7.25),
#     la recherche profonde rattrape (mt2.0 = 1.71). deep-eg plafonne ~mt0.5 (plancher éval).
# Paramétrisation (vs 0241 qui plafonnait +229.5 @5M, labels depth-4 uniformes) :
#   PROFONDEUR  : labels par phase — base depth-6 (ouverture/milieu déjà ≈Scan, on garde
#                 le volume), endgame=12, deep-eg=14 (≈qualité mt0.5-1.0, là où la finale
#                 est search-bound ; coût faible car peu de pièces = faible branching).
#   RATIO FINALE: --phase-weight endgame=3,deep-eg=4 (le fit PRIORISE les lignes finale ;
#                 l'ouverture reste quasi-parfaite, données massives + intrinsèquement faciles).
#   MT          : le play self-play reste depth-4 (rapide, chaque ply) ; le « plus de
#                 recherche » de la finale est INJECTÉ dans le SIGNAL via les labels profonds ;
#                 le VERDICT se mesure au movetime vs Scan (mt0.5 & mt1.0), budget réaliste
#                 où la recherche rattrape (cohérent 0252).
# Trainer --lowmem (0244 a OOM en full-batch >8M). Sélection = val-loss (proxy retiré).
# Métrique-clé = val/phase mse en FINALE (doit chuter gen-après-gen) + Elo réel vs hc/Scan.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0254-densify-endgame/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

# --- build KING-AWARE binary (occupancy = men|kings) ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: build pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns ; KING-AWARE build"

# --- PARAMÈTRES OPTIMISÉS (cf. en-tête) ---
EVAL_DEPTH=6; PLAY_DEPTH=4; NPER=600000; NGEN=8; BD=9; EPAIRS=15
LABEL_PHASE="endgame=12,deep-eg=14"      # PROFONDEUR : labels profonds en finale (0252)
PHASE_W="endgame=3,deep-eg=4"            # RATIO FINALE : sur-pondère les lignes finale (0251)
CFOLD="--full-fold --king-patterns"      # full-fold + ROIS dans les patterns (= le binaire)
declare -A ELO EGM
echo "PARAMS: label-depth-by-phase=[$LABEL_PHASE]  phase-weight=[$PHASE_W]  lowmem  base depth=$EVAL_DEPTH play=$PLAY_DEPTH  $NPER/gen ×$NGEN"

# train : logistic full-fold king-aware, lowmem, PONDÉRÉ PAR PHASE
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --lowmem $CFOLD \
            --phase-weight "$PHASE_W" --out "$3.pjtw" >"$3-train.log" 2>&1; }
# extrait le val_mse global + la perte val en FINALE (la métrique de densification)
val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
val_mse(){ grep -oE 'mse=[0-9.]+' "$1-train.log" | tail -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc "$BD" "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local L=$(grep -oE 'NNUE=[0-9]+'      "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+'     "$lg"|tail -1|cut -d= -f2)
  local E=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=${E:-NA}"
}
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
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
echo "=== gen0 : seed (300k self-play, labels profonds finale, l2=3e-2) KING-AWARE $CFOLD ==="
gen_and_append 300000 "$ART/sp0" "$CUM" --label-depth-by-phase "$LABEL_PHASE"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; tail -8 "$ART/gen0-train.log"; exit 7; }
EGM[0]=$(val_endgame "$ART/gen0"); ELO[0]=$(elo_vs_hc "$ART/gen0.pjtw" "$EPAIRS")
echo "  gen0 val_mse=$(val_mse "$ART/gen0")  val_endgame=${EGM[0]}  Elo_vs_hc=${ELO[0]}"
case "${ELO[0]}" in 0-0-0*) echo "ABORT: gen0 0-0-0 → binaire/train désync"; exit 8;; esac

PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : +${NPER} self-play (labels profonds finale) avec gen$((g-1)) → cumulé → logistic pondéré ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw" --label-depth-by-phase "$LABEL_PHASE"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; tail -8 "$ART/gen$g-train.log"; exit 7; }
  EGM[$g]=$(val_endgame "$ART/gen$g"); ELO[$g]=$(elo_vs_hc "$ART/gen$g.pjtw" "$EPAIRS")
  echo "  gen$g val_mse=$(val_mse "$ART/gen$g")  val_endgame=${EGM[$g]}  Elo_vs_hc=${ELO[$g]}"
  PREV="$ART/gen$g"
done
echo "=== gen${NGEN} vs hc précis (60 paires) ==="; ELOF=$(elo_vs_hc "$ART/gen${NGEN}.pjtw" 60); echo "  $ELOF"

# --- VERDICT vs Scan au MOVETIME (budget réaliste, finale search-bound : 0252) ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  echo "=== Scan absent → install ==="; rm -rf /root/jass-scan
  git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone Scan échoué — verdict vs Scan sauté)"
  chmod +x "$SCAN_BIN" 2>/dev/null || true
fi
SCAN5=""; SCAN1=""
if [ -x "$SCAN_BIN" ]; then
  echo "=== gen${NGEN} vs Scan @ mt0.5s (pairs=3) ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" \
      --scan-bb-size 0 --movetime 0.5 --pairs 3 >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  echo "  mt0.5 : $SCAN5"
  echo "=== gen${NGEN} vs Scan @ mt1.0s (pairs=3) ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/gen${NGEN}.pjtw" \
      --scan-bb-size 0 --movetime 1.0 --pairs 3 >"$ART/scan-mt1.log" 2>&1
  SCAN1=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt1.log" | tr '\n' ' ')
  echo "  mt1.0 : $SCAN1"
fi

echo; echo "=========================================================="
echo "   cpx62-0254 — DENSIFICATION FINALE (king-aware, labels profonds + ratio finale)"
echo "   PARAMS : label[$LABEL_PHASE]  phase-weight[$PHASE_W]  lowmem  base d$EVAL_DEPTH  $NPER/gen"
echo "----------------------------------------------------------"
for g in $(seq 0 "$NGEN"); do echo "  gen$g  Elo_vs_hc=${ELO[$g]}   val_endgame_mse=${EGM[$g]}"; done
echo "  gen${NGEN} (60p) vs hc : $ELOF"
[ -n "$SCAN5" ] && echo "  gen${NGEN} vs Scan mt0.5 : $SCAN5"
[ -n "$SCAN1" ] && echo "  gen${NGEN} vs Scan mt1.0 : $SCAN1"
echo "----------------------------------------------------------"
echo "  LECTURE : val_endgame_mse DOIT chuter gen-après-gen (l'éval apprend la finale)"
echo "            ET Elo monter au-dessus de 0241 (+229.5 @60p) = densification finale gagnante."
echo "  gen${NGEN}.pjtw conservé pour autopsie king-aware vs Scan (comparer 0250 : endgame king 3.6)."
echo "=========================================================="
