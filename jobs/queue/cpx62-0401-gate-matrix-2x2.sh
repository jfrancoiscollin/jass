#!/usr/bin/env bash
# id: cpx62-0401-gate-matrix-2x2
# description: GATE 0+1 EN UNE MATRICE 2x2 (volume x archi) sur le corpus 29M (17 shards, manifeste). On fit 32cf ET
# 8cf, chacun a 2M (sous-ech. seede du MEME corpus) ET a 29M (full), via train_stream (gradient EXACT, streaming disque
# -> pas d'OOM, la version qui MARCHE de 0319-qui-a-plante). Puis juge cross-arch (jass_vs_jass_arch) sur 4 matchups :
#   V32 = 32cf@29M vs 32cf@2M   (effet VOLUME, archi riche)
#   V8  =  8cf@29M vs  8cf@2M   (effet VOLUME, archi Scan-exacte)
#   A29 = 32cf@29M vs  8cf@29M  (GATE 1 PROPRE : archi au scale)
#   A2  = 32cf@2M  vs  8cf@2M   (l'ancien regime affame, pour montrer l'inversion)
# Lecture : V*>0.55 => le volume paie (fit-volume confirme) ; A29 vs A2 => l'archi riche s'INVERSE-t-elle au scale ?
# Tout hors-tree (/root/cw-gate, immunise au clean runner), transport gzip. Aucun Scan. Resultats emis au fil de l'eau.
# expected_duration: ~9 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-720}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0401-gate-matrix-2x2/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
W=/root/cw-gate; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32; GEOM8=/root/jass-geom8
SUB=2000000; MAXIT_FULL=25; MAXIT_2M=25; CHUNK=1000000
DROP=diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3
say(){ echo "$@" | tee -a "$RES"; }

preflight_build 2; preflight_train 29000000 2; preflight_note "assemble 29M + dump feat + 4 fits train_stream + 4 juges" 200; preflight_check

# ---------- build commun (memes flags que la gen du corpus) ----------
cmake_jass(){ cmake -S . -B "$1" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake-$(basename "$1").log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$W/cmake-$(basename "$1").log" || { echo "ABORT egdb $1"; exit 6; }
  cmake --build "$1" -j"$(mem_safe_jobs)" --target jass >"$W/bd-$(basename "$1").log" 2>&1 || { echo "BUILD FAIL $1"; tail -8 "$W/bd-$(basename "$1").log"; exit 6; }; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1

echo "=== build 32-pat (defaut) ==="
cmake_jass "$W/build-32"; J32="$W/build-32/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP32=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP32" = 32 ] || { echo "ABORT: build-32 attendait 32 patterns, a $NP32"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

echo "=== emit 8-pat (drop 24) -> build 8-pat IMMEDIAT -> snapshot hors-tree ==="
python3 pattern_jass/tools/gen_patterns.py --emit --drop "$DROP" >"$W/g8.log" 2>&1
NP8=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP8" = 8 ] || { echo "ABORT: emit 8-pat a donne $NP8 patterns (attendu 8)"; cat "$W/g8.log"; exit 7; }
cmake_jass "$W/build-8"; J8="$W/build-8/jass"
rm -rf "$GEOM8"; mkdir -p "$GEOM8"; cp pattern_jass/tools/patterns.py "$GEOM8/patterns.py"
git checkout -- pattern_jass/src/pattern.hpp pattern_jass/tools/patterns.py pattern_jass/tests/run_tests.cpp 2>/dev/null || true
say "# build OK : 32-pat ($J32) + 8-pat ($J8)"

# ---------- assemble 29M + sous-ech 2M + dump FEAT ----------
echo "=== assemble le corpus 29M depuis les 17 shards committes ==="
tools/corpus_manifest.sh assemble "$W/big.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
say "# corpus assemble : ${NBIG} positions"
[ "$NBIG" -ge 25000000 ] || { echo "ABORT: corpus ${NBIG} < 25M (shards manquants ?)"; exit 8; }

echo "=== sous-echantillon seede ${SUB} (MEME corpus) ==="
python3 - "$W/big.jnnw" "$W/big2M.jnnw" "$SUB" <<'PY'
import struct,sys,numpy as np
src,dst,sub=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
sub=min(sub,n); idx=np.sort(np.random.default_rng(42).choice(n,sub,replace=False))
out=bytearray(b'JNNW'+struct.pack('<I',sub))
for i in idx: out+=body[i*REC:(i+1)*REC]
open(dst,'wb').write(out); print(f"sous-ech {sub} / {n}")
PY

echo "=== dump FEAT (extras, arch-independant) pour 29M et 2M ==="
"$J32" --dump-eval-features "$W/big.jnnw"   "$W/feat.full" >"$W/feat-full.log" 2>&1 || { echo "ABORT dump feat full"; tail "$W/feat-full.log"; exit 8; }
"$J32" --dump-eval-features "$W/big2M.jnnw" "$W/feat.2m"   >"$W/feat-2m.log"   2>&1 || { echo "ABORT dump feat 2m"; tail "$W/feat-2m.log"; exit 8; }

# ---------- les 4 fits (train_stream, color-fold, logistic, tempo-stage) ----------
fit(){ # $1=geomdir $2=data $3=feat $4=maxit $5=out $6=tag
  echo "  [fit $6] train_stream color-fold logistic maxit=$4 ($2)"
  env JASS_PATTERNS_DIR="$1" python3 pattern_jass/tools/train_stream.py --data "$2" --feat "$3" \
      --color-fold --tempo-stage --loss logistic --l2 1e-4 --max-iter "$4" --chunk "$CHUNK" --out "$5" \
      >"${5%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL $6"; tail -12 "${5%.pjtw}.log"; exit 9; }
  grep -iE "train_loss|wrote|columns" "${5%.pjtw}.log" | tail -2 | sed 's/^/    /'; }

say "# --- FITS ---"
fit "$GEOM32" "$W/big2M.jnnw" "$W/feat.2m"   "$MAXIT_2M"   "$W/w32_2m.pjtw"   "32cf@2M"
fit "$GEOM8"  "$W/big2M.jnnw" "$W/feat.2m"   "$MAXIT_2M"   "$W/w8_2m.pjtw"    "8cf@2M"
fit "$GEOM32" "$W/big.jnnw"   "$W/feat.full" "$MAXIT_FULL" "$W/w32_full.pjtw" "32cf@29M"
fit "$GEOM8"  "$W/big.jnnw"   "$W/feat.full" "$MAXIT_FULL" "$W/w8_full.pjtw"  "8cf@29M"
gzip -c "$W/w32_full.pjtw" > "$ART/w32_full.pjtw.gz" 2>/dev/null || true
gzip -c "$W/w8_full.pjtw"  > "$ART/w8_full.pjtw.gz"  2>/dev/null || true
say "# fits OK (poids 29M gzippes en artefacts)"

# ---------- juge cross-arch parallele ----------
judge(){ # $1=JA $2=PA $3=JB $4=PB ; echo score
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
     --jass-a "$1" --pattern-a "$2" --jass-b "$3" --pattern-b "$4" \
     --depth 9 --pairs 14 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>"$W/je.$s" & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (N={g})" if g else "NA")
PY
}
say "# --- JUGES (score = A vs B, >0.5 => A gagne) ---"
say "V32  32cf@29M vs 32cf@2M = $(judge "$J32" "$W/w32_full.pjtw" "$J32" "$W/w32_2m.pjtw")   [effet VOLUME, archi riche]"
say "V8    8cf@29M vs  8cf@2M = $(judge "$J8"  "$W/w8_full.pjtw"  "$J8"  "$W/w8_2m.pjtw")    [effet VOLUME, archi Scan-exacte]"
say "A29  32cf@29M vs  8cf@29M = $(judge "$J32" "$W/w32_full.pjtw" "$J8" "$W/w8_full.pjtw")  [GATE 1 : archi au SCALE]"
say "A2   32cf@2M  vs  8cf@2M  = $(judge "$J32" "$W/w32_2m.pjtw"  "$J8" "$W/w8_2m.pjtw")     [ancien regime affame]"

say ""
say "================= LECTURE ================="
say "  V32/V8 > 0.55  => le VOLUME paie (fit-volume CONFIRME ; la fenetre 2M etait le mur)."
say "  A29 > A2       => l'archi riche s'INVERSE au scale (riche perdait par famine, gagne nourrie)."
say "  archi gagnante de A29 = candidate pour la boucle de production a archi figee."
say "==========================================="
