#!/usr/bin/env bash
# id: 0200-selfplay-deep-relabel-d12
# description: RECETTE SCAN — étape 6 : bootstrap teacher-free (eval<-search(eval)).
# 0198 a montré que le score self-play tel quel (recherche champion @movetime
# 30ms, bruité) est un MAUVAIS prof (0.08-0.17 d9, pire que le WDL 0.22). Le
# 0.39 du champion venait de labels PROFONDS (Scan-d10). On teste donc la même
# data self-play 1M relabellisée par RECHERCHE PROFONDE d12 avec le champion
# lui-même (--rewrite-scores-with-search, teacher-free, sans Scan), puis train
# score-target. La recherche d12 est plus forte que l'eval statique → si la
# pattern-eval franchit 0.39, le volant tourne sans prof externe.
#
#   Préambule : auto-calibrage (2000 positions @d12 avec le VRAI champion) →
#   imprime s/pos + ETA 1M/8-cœurs avant de lancer le gros run.
#   Relabel : 1M @ d12, shardé sur $(nproc) (ordre préservé → sp.feat de 0196
#   réutilisable tel quel, les features ne dépendent que des positions).
#   Train : score-target recette champion, l2 ∈ {1e-4, 3e-4}.
#   Bench : vs v15 (d9/mt/hc, comparable à 0198) + vs Scan d9 (ancre absolue).
#
#   score-d12 ≫ 0.17 (vers/au-delà de 0.39) = la profondeur du label est le
#   levier, bootstrap teacher-free marche → itérer les cycles.
#   score-d12 ≈ 0.17 = la profondeur n'aide pas → features/classe à reposer.
#
# expected_duration: ~5-8 h (relabel 1M @d12 le gros poste ; train+bench ~1h).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0200-selfplay-deep-relabel-d12/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SRC=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src
SP="$SRC/sp-all.jnnw"; FEAT="$SRC/sp.feat"; CHAMP="$SRC/champ.pjtw"
[ -f "$SP" ]   || { echo "ABORT: $SP introuvable (runner reclaimé ?)"; exit 3; }
[ -f "$FEAT" ] || { echo "ABORT: $FEAT introuvable"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
echo "=== host $(hostname)  nproc=$NCPU ; reuse $(ls -lh "$SP"|awk '{print $5}') data + $(ls -lh "$FEAT"|awk '{print $5}') feat ==="

# --- build ----------------------------------------------------------------
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- champion (re-distill si 0196 a disparu) ------------------------------
if [ ! -f "$CHAMP" ]; then
  echo "=== champ.pjtw absent → re-distill ==="
  CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
  [ -f "$CLEAN" ] || { echo "ABORT: master clean introuvable"; exit 3; }
  $JASS --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" >"$ART/champ-train.log" 2>&1
  CHAMP="$ART/champ.pjtw"; [ -f "$CHAMP" ] || { echo "ABORT re-distill"; exit 7; }
  rm -f "$ART/champ.feat"
fi
echo "champion : $CHAMP"

# --- auto-calibrage : s/pos @d12 avec le VRAI champion --------------------
D=12
echo "=== auto-calibrage : 2000 positions @ d$D ==="
t0=$(date +%s.%N)
$JASS --rewrite-scores-with-search "$SP" "$ART/cal.jnnw" --nnue "$CHAMP" --depth $D --start 0 --count 2000 >"$ART/cal.log" 2>&1
t1=$(date +%s.%N)
PER=$(python3 -c "print(f'{($t1-$t0)/2000:.4f}')")
ETA=$(python3 -c "print(f'{$PER*1000000/$NCPU/3600:.1f}')")
echo "  champion d$D : ${PER}s/pos  → 1M sur $NCPU cœurs ≈ ${ETA}h"
rm -f "$ART/cal.jnnw"

# --- relabel 1M @ d12, shardé (ORDRE PRÉSERVÉ pour aligner sp.feat) -------
NTOT=1000000; SH=$NCPU; CHUNK=$(( (NTOT + SH - 1) / SH ))
echo "=== relabel 1M @ d$D : $SH shards × $CHUNK ==="
for s in $(seq 1 "$SH"); do
  st=$(( (s-1) * CHUNK ))
  $JASS --rewrite-scores-with-search "$SP" "$ART/sp-d$D-$s.jnnw" --nnue "$CHAMP" --depth $D --start "$st" --count "$CHUNK" >"$ART/relabel-$s.log" 2>&1 &
done
wait
python3 - "$ART" "$D" <<'PY'
import struct,glob,os,sys,re
art=sys.argv[1]; D=sys.argv[2]; REC=38; outp=os.path.join(art,f"sp-d{D}.jnnw")
shards=sorted(glob.glob(os.path.join(art,f"sp-d{D}-*.jnnw")),
              key=lambda p:int(re.search(rf"sp-d{D}-(\d+)\.jnnw",p).group(1)))
tot=0; out=open(outp,'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',0))
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': print("SKIP bad",s); continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; out.write(b[8:8+n*REC])
out.seek(4); out.write(struct.pack('<I',tot)); out.close()
print("merged",tot,"->",outp,"from",len(shards),"shards (numeric order)")
PY
RELAB="$ART/sp-d$D.jnnw"
echo "=== stats score relabellisé ==="
python3 - "$RELAB" <<'PY'
import sys,struct,numpy as np
raw=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',raw[4:8])[0]
sc=np.frombuffer(raw[8:8+n*38],dtype=np.uint8).reshape(n,38)[:,33:37].copy().view('<i4').ravel()
print(f"n={n}  range=[{sc.min()},{sc.max()}]  std={sc.std():.1f}  nonzero={100*(sc!=0).mean():.1f}%  |s|>4900={100*(np.abs(sc)>4900).mean():.1f}%")
PY

# --- train score-target (recette champion) + bench -----------------------
SCAN_DIR=/root/jass/.scan; SCAN="$SCAN_DIR/scan_linux"
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+'|head -1; }
bench(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9  6 1 0   "" 64 >"$1-v15d9.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 64 4 1 300 "" 64 >"$1-v15mt.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$1.pjtw" hc    8  6 1 0   "" 64 >"$1-hc.log"    2>&1; }
train_score(){ # <tag> <l2>
  python3 pattern_jass/tools/train.py --data "$RELAB" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 "$2" --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" >"$ART/$1-train.log" 2>&1
  [ -f "$ART/$1.pjtw" ] && bench "$ART/$1" || echo "  ABORT train $1"; }

for pair in "d12-1e-4 1e-4" "d12-3e-4 3e-4"; do
  set -- $pair
  echo "=== score-target d12 relabel, l2=$2 ==="; train_score "$1" "$2"
  echo "  l2=$2 : v15 d9=$(rate "$ART/$1-v15d9.log")  mt=$(rate "$ART/$1-v15mt.log")  hc=$(rate "$ART/$1-hc.log")"
done

# vs Scan (profondeur égale d9) — ancre absolue, si Scan dispo
if [ -x "$SCAN" ]; then
  for m in d12-1e-4 d12-3e-4; do
    python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" --jass-pattern "$ART/$m.pjtw" \
      --depth 9 --pairs 8 --jass-threads 1 >"$ART/$m-scand9.log" 2>&1
    echo "  $m vs Scan d9 = $(jrate "$ART/$m-scand9.log")"
  done
fi

echo; echo "=========================================================="
echo "   0200 DEEP RELABEL d12 (recette Scan étape 6) — VERDICT"
echo "  calibrage : champion d12 = ${PER}s/pos  (1M/$NCPU ≈ ${ETA}h)"
echo "  score-d12 l2=1e-4 : v15 d9=$(rate "$ART/d12-1e-4-v15d9.log")  mt=$(rate "$ART/d12-1e-4-v15mt.log")  hc=$(rate "$ART/d12-1e-4-hc.log")  | Scan d9=$(jrate "$ART/d12-1e-4-scand9.log" 2>/dev/null)"
echo "  score-d12 l2=3e-4 : v15 d9=$(rate "$ART/d12-3e-4-v15d9.log")  mt=$(rate "$ART/d12-3e-4-v15mt.log")  hc=$(rate "$ART/d12-3e-4-hc.log")  | Scan d9=$(jrate "$ART/d12-3e-4-scand9.log" 2>/dev/null)"
echo "  ANCRES vs v15 : self-play+score@30ms (0198)=0.08-0.17 ; champion(Scan-d10 distill)=0.39 ; self-play+WDL=0.22"
echo "  → d12 ≫ 0.17 (→ 0.39+) = la profondeur du label est le levier, bootstrap teacher-free marche → itérer."
echo "  → d12 ≈ 0.17 = la profondeur n'aide pas → features/classe à reposer."
echo "=========================================================="
