#!/usr/bin/env bash
# id: cpx62-0373-virtuous-loop-deep
# description: TUNING de la boucle virtuelle (directive JFC : on ne se compare PLUS à Scan, seulement à NOUS-MÊMES ;
# on ressortira Scan au plateau). Qualité + volume d'un coup : self-play joué PROFOND (play_depth=10 → issues
# véridiques, pas blunder-driven comme d4 dans 0363/0365) + le max de volume que le compute permet (sonde de débit
# qui dimensionne NPER pour viser ~18 min de génération/gen). Seed matériel-seul (la recherche d10 compense l'eval
# faible → jeu correct dès gen0). Boucle : self-play(gen_{k-1}) d10 → WDL (résultat, egdb-adjugé) → pool cumulé →
# logistique full-batch (--lowmem ; NB --minibatch est L2-only donc incompatible logistique, et à d10 le goulot est la
# GÉNÉRATION pas la RAM → full-batch suffit). JUGE = SELF : gen_k vs gen_{k-1} (on monte encore ?) + gen_k vs gen1
# (montée cumulée). AUCUN vs Scan. gen_k vs gen_{k-1} > 0.5 soutenu → la boucle grimpe → on continue/scale. → ~0.5 = plateau.
# expected_duration: ~3-4 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-280}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0373-virtuous-loop-deep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
PLAY_DEPTH=10; EVAL_DEPTH=4; SCALE=1000; NGEN=6; TARGET_GEN_MIN=20
preflight_build 1; preflight_train 1500000 $((NGEN+1)); preflight_note "boucle profonde d${PLAY_DEPTH} ${NGEN} gens (sonde débit) + DIRECT self" 150; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
echo "=== build (EGDB ON = adjudication finale exacte) ==="
B=build-prod; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted && echo "  egdb data: ON" || echo "  egdb data: absente"

echo "=== seed matériel-seul (recherche d${PLAY_DEPTH} compense) ==="
"$JASS" --gen-data-wdl 256 "$ART/mini.jnnw" 2 2 60 1 >/dev/null 2>&1
"$JASS" --dump-eval-features "$ART/mini.jnnw" "$ART/seed.feat" >/dev/null 2>&1
python3 - "$ART/seed.feat" "$ART/gen0.pjtw" "$SCALE" <<'PY'
import sys,struct,numpy as np; sys.path.insert(0,'pattern_jass/tools')
import patterns as P, train; from pathlib import Path
feat,out,scale=sys.argv[1],sys.argv[2],int(sys.argv[3])
raw=open(feat,'rb').read(); cnt,k=struct.unpack_from('<II',raw,4)
NB=P.NUM_PATTERNS*P.BUCKETS_PER_PATTERN
pat=np.zeros(NB,np.int32); ext=np.zeros(k,np.int32)
ext[100]=scale; ext[101]=-scale; ext[0:50]=3*scale; ext[50:100]=-3*scale
train.write_weights_v3(Path(out),pat,pat.copy(),ext,ext.copy(),scale,king=False); print('seed ok n_ext=%d'%k)
PY

CUM="$ART/cumulative.jnnw"
gen_append(){ local pilot="$1" nn="$2" tag="$3"; local per=$(( (nn + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    "$JASS" --gen-data-wdl "$per" "$ART/$tag.$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >"$ART/$tag.$s.log" 2>&1 &
  done; wait
  python3 - "$ART/$tag" "$CUM" <<'PY'
import struct,glob,sys,re,os
tag,cum=sys.argv[1],sys.argv[2]; REC=38
shards=sorted(glob.glob(tag+".*.jnnw"),key=lambda p:int(re.search(r"\.(\d+)\.jnnw$",p).group(1)))
body=b""; add=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
if os.path.exists(cum) and os.path.getsize(cum)>=8:
    raw=open(cum,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(cum,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+add)); o.close(); print('cumulative',old+add)
else:
    open(cum,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print('cumulative',add)
PY
  rm -f "$ART/$tag".*.jnnw
}
fit(){ # logistique WDL full-batch (--lowmem) ; full-fold (32-pat ~1M)
  "$JASS" --dump-eval-features "$1" "$2.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2.feat" \
    --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem --full-fold \
    --out "$2.pjtw" >"$2-train.log" 2>&1
  [ -f "$2.pjtw" ] || { echo "TRAIN FAIL $2"; tail -8 "$2-train.log"; exit 9; }
}
direct(){ "$JASS" --benchmark-nnue-vs-nnue "$1.pjtw" "$2.pjtw" 9 6 1 0 >"$3" 2>&1 || true
  grep -E 'score rate' "$3" | grep -oE '[0-9.]+' | head -1; }

echo "=== sonde de débit @ d${PLAY_DEPTH} (dimensionne NPER pour ~${TARGET_GEN_MIN} min/gen) ==="
t0=$(date +%s); gen_append "$ART/gen0.pjtw" $((NCPU*200)) "probe" >/dev/null 2>&1; dt=$(( $(date +%s) - t0 )); [ "$dt" -lt 1 ] && dt=1
PROBE_N=$((NCPU*200)); RATE=$(( PROBE_N*60/dt ))   # positions/min
NPER=$(( RATE*TARGET_GEN_MIN )); [ "$NPER" -lt 20000 ] && NPER=20000; [ "$NPER" -gt 600000 ] && NPER=600000
echo "  débit ≈ ${RATE} pos/min @ d${PLAY_DEPTH} → NPER=${NPER}/gen"
rm -f "$CUM"   # FIX 0366: rm, PAS truncate (sinon gen_append crashe sur fichier 0 octet)

declare -A DPREV DGEN1
PREV="$ART/gen0"
for g in $(seq 1 "$NGEN"); do
  echo "=== gen$g : self-play(gen$((g-1))) d${PLAY_DEPTH} +${NPER} → cumulé → logistique ==="
  gen_append "$PREV.pjtw" "$NPER" "sp$g"
  fit "$CUM" "$ART/gen$g"
  if [ "$g" -ge 2 ]; then
    DPREV[$g]=$(direct "$ART/gen$g" "$PREV" "$ART/gen$g-vsprev.log")
    DGEN1[$g]=$(direct "$ART/gen$g" "$ART/gen1" "$ART/gen$g-vsgen1.log")
    echo "  gen$g : vs gen$((g-1))=${DPREV[$g]}   vs gen1=${DGEN1[$g]}"
  else
    echo "  gen1 : (baseline self)"
  fi
  PREV="$ART/gen$g"
done

echo; echo "=========================================================="
echo "   cpx62-0373 — BOUCLE VIRTUELLE PROFONDE (FIX bug CUM + cap relevé 600k) (d${PLAY_DEPTH}), jugée SELF (aucun Scan)"
echo "   NPER=${NPER}/gen  cumul final=$(python3 -c "import struct;print(struct.unpack('<I',open('$CUM','rb').read(8)[4:8])[0])" 2>/dev/null)"
echo "   gen :  vs gen(k-1)   vs gen1"
for g in $(seq 2 "$NGEN"); do echo "    $g :   ${DPREV[$g]:-NA}        ${DGEN1[$g]:-NA}"; done
echo "----------------------------------------------------------"
echo "   vs gen(k-1) > 0.5 SOUTENU → la boucle GRIMPE encore (jeu profond = issues véridiques) → continuer/scaler."
echo "   vs gen(k-1) ~0.5 → PLATEAU → c'est LÀ qu'on ressort Scan (et pas avant)."
echo "=========================================================="
