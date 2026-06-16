#!/usr/bin/env bash
# id: cpx62-0293-depthramp-ab
# description: PETIT A/B (hypothèse "label fixe depth-8 faible sur l'entre-deux 8-21 pièces"). Le creux
# de qualité = late-mid (15-21) + endgame (8-14) : éval la plus faible, depth-8 court, bitbase (≤7) pas
# atteinte. Test : 2 bras IDENTIQUES (king-aware + EGDB, SANS endgame-features → 106 features = compat
# champion 0266 ; jeu piloté par le champion 0266 → parties réalistes), seule variable = le schedule de
# profondeur. Bras A = depth-8 UNIFORME (= 0287). Bras B = --play/--label-depth-by-phase "late-mid=12,
# endgame=16" (la recherche profonde MORD dans la bitbase → labels de transition ancrés-TB). egdb ON en
# génération, OFF en éval (mesure l'éval pure). 1 gen 300k/bras. Compare endgame-rois ET late-mid-rois
# vs Scan. + perft on-box (valide les micro-optims movegen fraîchement mergées).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0293-depthramp-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
SRC=/root/jass/jobs/results/cpx62-0266-kingloop-deepplay/artefacts.src
CHAMP="$SRC/gen8.pjtw"
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base egdb absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

# --- build : king-aware + EGDB, SANS endgame-features (106 features = compat champion 0266) ---
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
JASS=/root/jass/build-prod/jass
./build-prod/jass_tests 2>&1 | tail -1
# perft on-box : garde-fou des micro-optims movegen mergées (coups doivent rester identiques)
P6=$($JASS --perft 6 2>/dev/null | grep -oE 'perft\(6\) = [0-9]+' | grep -oE '[0-9]+$')
[ "$P6" = "167140" ] && echo "perft(6)=167140 OK (movegen opts move-identical)" || { echo "ABORT: perft(6)=$P6 != 167140 (REGRESSION movegen)"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
[ -f "$CHAMP" ] || { echo "ABORT: champion 0266 introuvable ($CHAMP)"; exit 3; }
$JASS --egdb-selfcheck "$APP" 1 >/dev/null 2>&1 || { echo "ABORT: egdb ne s'ouvre pas"; exit 6; }

EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=300000
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

# arm: $1=tag, $2..=extra gen args (depth-by-phase). egdb ON en gen (env inline), OFF ailleurs.
run_arm(){ local tag="$1"; shift
  local PER=$(( (NPER + NCPU - 1) / NCPU )); local CUM="$ART/$tag.jnnw"
  for s in $(seq 1 "$NCPU"); do
    JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=256 \
      $JASS --gen-data-wdl "$PER" "$ART/$tag-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) --nnue "$CHAMP" "$@" >"$ART/$tag-$s.log" 2>&1 &
  done; wait
  python3 - "$ART/$tag" "$CUM" <<'PY'
import struct,glob,sys,re
outp,dst=sys.argv[1],sys.argv[2]; REC=38; body=b""; add=0
for s in sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1))):
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print(f"{dst}: {add}")
PY
  rm -f "$ART/$tag-"*.jnnw
  $JASS --dump-eval-features "$CUM" "$ART/feat-$tag" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$CUM" --scan-eval --king-patterns \
    --eval-features-file "$ART/feat-$tag" --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 \
    --prune --lowmem --full-fold --out "$ART/$tag.pjtw" >"$ART/$tag-train.log" 2>&1
  [ -f "$ART/$tag.pjtw" ] || { echo "ABORT train $tag"; tail -8 "$ART/$tag-train.log"; return 1; }
}
elo(){ local lg="$ART/elo-$1.log"; $JASS --benchmark-scan-eval "$ART/$1.pjtw" hc 9 40 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2) (${W:-0}-${D:-0}-${L:-0})"; }
autopsy(){ local tag="$1"; local out="$ART/autopsy-$tag.txt"
  [ -x "$SCAN_BIN" ] || { echo "(pas de Scan)"; return; }
  local G="$ART/games-$tag"; mkdir -p "$G"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/$tag.pjtw" --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$G" >"$ART/scan-$tag.log" 2>&1
  python3 tools/game_autopsy.py --games-dir "$G" --jass /bin/true --scan "$SCAN_BIN" --scan-depth 11 --scan-bb-size 0 --worst 6 --out "$out" 2>"$ART/autopsy-$tag.err" || echo "(autopsie skip $tag)"
  # king-perte late-mid + endgame
  awk '/late-mid|endgame/{print "    "$0}' "$out" 2>/dev/null | grep -iE 'late-mid|endgame' | head -4
}

echo "=== BRAS A : depth-8 UNIFORME (= 0287) ==="; run_arm "A8" || exit 7
echo "=== BRAS B : ramp late-mid=12, endgame=16 ==="; run_arm "Bramp" --play-depth-by-phase "late-mid=12,endgame=16" --label-depth-by-phase "late-mid=12,endgame=16" || exit 7
ELOA=$(elo A8); ELOB=$(elo Bramp)

echo; echo "=========================================================="
echo "   cpx62-0293 — A/B PROFONDEUR sur l'entre-deux (vs Scan)"
echo "----------------------------------------------------------"
echo "  BRAS A (uniforme-8)        Elo_vs_hc=$ELOA"
echo "  --- autopsie A (king-perte par phase) ---"; autopsy A8
echo "  BRAS B (ramp 12/16)        Elo_vs_hc=$ELOB"
echo "  --- autopsie B (king-perte par phase) ---"; autopsy Bramp
echo "----------------------------------------------------------"
echo "  Si late-mid-rois ET/OU endgame-rois de B < A → approfondir l'entre-deux AIDE"
echo "     (labels de transition ancrés-TB) → schedule à intégrer dans la boucle prod."
echo "  Si ≈ égal → depth-8 uniforme suffit (la recherche mordait déjà la TB / l'éval limite)."
echo "=========================================================="
