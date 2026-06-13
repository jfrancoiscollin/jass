#!/usr/bin/env bash
# id: cpx62-0214-depth-mt30
# description: DEBUG Nœud 2ter·B5 — le mur ~0.46 est-il la PROFONDEUR DE JEU ? Les boucles
# 0210/0211 plafonnent à ~0.46 en jouant DEPTH4 (parties/labels faibles). Ici : même
# boucle CUMULÉE mais jeu à **mt30** (movetime, play_depth=8 cap) + labels eval_depth=8.
# Entraînement --prune (validé lossless, ~50× moins cher → la profondeur devient
# abordable). Question : le proxy DÉPASSE-t-il 0.46 quand on joue plus profond ?
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0214-depth-mt30/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

MT=30; EVAL_DEPTH=8; PLAY_CAP=8; NPER=300000   # per-gen self-play volume
proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1.pjtw" --testset "$REF" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
fit_wdl(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --out "$3.pjtw" >"$3-train.log" 2>&1; }
coverage(){ python3 tools/bucket_coverage.py "$1" 2>/dev/null | grep -E "distinct touched" | head -1; }
gen_and_append(){ local NN=$1; local OUTP=$2; local CUM=$3; shift 3; local PER=$(( (NN + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    $JASS --gen-data-wdl "$PER" "${OUTP}-$s.jnnw" "$EVAL_DEPTH" "$PLAY_CAP" 200 $((RANDOM)) "$@" --movetime "$MT" >"${OUTP}-$s.log" 2>&1 &
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
echo "=== gen0 : seed (200k self-play embarqué @mt${MT}, l2=3e-2) ==="
gen_and_append 200000 "$ART/sp0" "$CUM"
$JASS --dump-eval-features "$CUM" "$ART/feat0" 2>&1 | tail -1
fit_wdl "$CUM" "$ART/feat0" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo ABORT seed; exit 7; }
echo "  gen0 proxy = $(proxy "$ART/gen0")  [$(coverage "$CUM")]"

PREV="$ART/gen0"
for g in 1 2 3 4 5; do
  echo "=== gen$g : +${NPER} self-play @mt${MT} avec gen$((g-1)) → corpus cumulé → logistic(--prune) ==="
  gen_and_append "$NPER" "$ART/sp$g" "$CUM" --nnue "$PREV.pjtw"
  $JASS --dump-eval-features "$CUM" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$CUM" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g"; exit 7; }
  echo "  gen$g proxy = $(proxy "$ART/gen$g")  [$(coverage "$CUM")]"
  PREV="$ART/gen$g"
done

echo; echo "=========================================================="
echo "   cpx62-0214 — BOUCLE CUMULÉE @mt${MT} (--prune) — VERDICT"
echo "  COURBE proxy (Spearman vs Scan-d10, set fixe 50k) :"
for g in 0 1 2 3 4 5; do echo "    gen$g = $(proxy "$ART/gen$g")"; done
echo "  RAPPEL : depth4 (0210/0211) PLAFONNE ~0.45-0.46 ; eval compétent ~0.64-0.67."
echo "  → proxy DÉPASSE 0.46 = la PROFONDEUR DE JEU est le mur → scaler la profondeur."
echo "  → proxy plat ~0.46 = la profondeur n'est pas le mur → Nœud 2ter·B4 (proxy≠Elo, SPRT)."
echo "=========================================================="
