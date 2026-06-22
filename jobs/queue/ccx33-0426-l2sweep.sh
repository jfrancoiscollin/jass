#!/usr/bin/env bash
# id: ccx33-0426-l2sweep
# description: GATE PROGRESSION — mesure le gain de volume au DOUBLEMENT (la vraie progression, pas les +0,8M/round
# qui sont sous le bruit). Baseline FIGE = w32_full (32cf@29M, archive par 0401). Challenger = 32cf REFIT sur le corpus
# accumule courant. AUTO-GARDE : si le corpus < THRESH (doublement pas atteint), no-op propre (exit 0) -> a re-deployer
# quand le volume est la. Sinon : build 32-pat, assemble, dump FEAT, fit 32cf challenger (meme config que 0401), juge
# challenger vs baseline. >0.55 => la 32cf PROGRESSE encore avec le volume (prediction 0401 : avantage croit vers 100M).
# Meme build/fold/extras des 2 cotes => isole l'effet VOLUME. EN PLUS : sweep L2 au scale (3e-5/1e-4/3e-4) car le
# l2=1e-4 fut cale a <=2M et l'optimum peut differer a gros volume -> on adopte le meilleur dans la boucle 0420.
# Hors-tree (/root/cw-prog), gzip. Aucun Scan.
# expected_duration: ~6 h (3 fits L2 + 3 juges, au-dela du seuil ; quasi-instantane si no-op)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-720}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0426-l2sweep/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
W=/root/cw-prog; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM=/root/jass-geom32-prog; MAXIT=25; CHUNK=1000000
BASE_VOL=29010792                       # volume du baseline w32_full (0401)
THRESH=40000000                         # corpus deja assez gros (44M+) -> on tourne maintenant
BASE_GZ=jobs/results/cpx62-0401-gate-matrix-2x2/artefacts/w32_full.pjtw.gz
say(){ echo "$@" | tee -a "$RES"; }

# ---------- AUTO-GARDE : assemble d'abord, no-op si sous le seuil ----------
echo "=== assemble le corpus accumule (tous les shards committes) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
tools/corpus_manifest.sh assemble "$W/big.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
RATIO=$(python3 -c "print(f'{$NBIG/$BASE_VOL:.2f}')")
say "# corpus courant : ${NBIG} positions  (x${RATIO} le baseline ${BASE_VOL})"
if [ "$NBIG" -lt "$THRESH" ]; then
  say "# NO-OP : ${NBIG} < seuil ${THRESH} (doublement pas atteint). Re-deployer ce gate quand le corpus aura double."
  say "# (rien gaspille : aucun build ni fit lance.)"
  exit 0
fi

# ---------- sous-echantillon 35M (ccx33 16Go/disque : FEAT + petit, fits + rapides ; L2 tout aussi representatif) ----------
SUB=35000000
if [ "$NBIG" -gt "$SUB" ]; then
  python3 - "$W/big.jnnw" "$W/sub.jnnw" "$SUB" <<'PY'
import struct,sys,numpy as np
src,dst,sub=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
with open(src,'rb') as f: n=struct.unpack('<I',f.read(8)[4:8])[0]
mm=np.memmap(src,dtype=np.uint8,mode='r',offset=8,shape=(n,REC))
sub=min(sub,n); idx=np.sort(np.random.default_rng(42).choice(n,sub,replace=False))
sel=np.ascontiguousarray(mm[idx])
with open(dst,'wb') as o: o.write(b'JNNW'+struct.pack('<I',sub)); o.write(sel.tobytes())
print(f"sous-ech {sub}/{n}")
PY
  DATA="$W/sub.jnnw"
else
  DATA="$W/big.jnnw"
fi
NFIT=$(python3 -c "import struct;print(struct.unpack('<I',open('$DATA','rb').read(8)[4:8])[0])")
say "# L2 sweep sur ${NFIT} positions (sous-ech de ${NBIG} pour ccx33)"

# ---------- au-dela du seuil : on mesure la progression ----------
preflight_build 1; preflight_train "$NFIT" 1; preflight_note "L2 sweep ccx33 : 3 fits + 3 juges vs baseline 29M" 120; preflight_check

echo "=== build 32-pat (memes flags que 0401) ==="
cmake -S . -B "$W/build-32" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
cmake --build "$W/build-32" -j"$(mem_safe_jobs)" --target jass >"$W/bd.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/bd.log"; exit 6; }
J32="$W/build-32/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
say "# build OK : 32-pat ($J32)"

echo "=== recupere + decompresse le baseline w32_full (0401) ==="
git cat-file -e "origin/main:$BASE_GZ" 2>/dev/null || { echo "ABORT: baseline $BASE_GZ absent"; exit 4; }
git show "origin/main:$BASE_GZ" | gunzip > "$W/baseline.pjtw" || { echo "ABORT gunzip baseline"; exit 4; }

echo "=== dump FEAT + fit 32cf challenger sur ${NBIG} ==="
"$J32" --dump-eval-features "$DATA" "$W/feat.full" >"$W/feat.log" 2>&1 || { echo "ABORT dump feat"; tail "$W/feat.log"; exit 8; }

# ---------- L2 SWEEP au scale : l2=1e-4 fut cale a <=2M (0176) ; a ${NBIG} l'optimum peut etre + BAS ----------
# (a gros volume + ~47% de buckets bien determines, trop de L2 bride la queue qu'on vient de nourrir).
L2S="3e-5 1e-4 3e-4"
fit_l2(){ env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$DATA" --feat "$W/feat.full" \
      --color-fold --tempo-stage --loss logistic --l2 "$1" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$2" \
      >"${2%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL l2=$1"; tail -12 "${2%.pjtw}.log"; exit 9; }
  grep -iE "train_loss|wrote" "${2%.pjtw}.log" | tail -1 | sed 's/^/    /'; }
judge(){ for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J32" --pattern-a "$1" \
     --jass-b "$J32" --pattern-b "$2" --depth 9 --pairs 28 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>"$W/je.$s" & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (N={g})" if g else "NA")
PY
  rm -f "$W"/j.* "$W"/je.* ; }

say "# --- FITS (sweep L2 au scale ${NBIG}) + PROGRESSION vs baseline@${BASE_VOL} ---"
for L2 in $L2S; do
  tag=$(echo "$L2" | tr -cd '0-9a-z')
  echo "  [fit l2=$L2] sur ${NBIG}"; fit_l2 "$L2" "$W/chal_${tag}.pjtw"
  gzip -c "$W/chal_${tag}.pjtw" > "$ART/w32-chal-l2-${tag}-${NBIG}.pjtw.gz" 2>/dev/null || true
  s=$(judge "$W/chal_${tag}.pjtw" "$W/baseline.pjtw")
  say "P(l2=$L2)  32cf@${NBIG} (x${RATIO}) vs baseline@${BASE_VOL} = ${s}"
done
say ""
say "================= LECTURE ================="
say "  Meilleur L2 = score le + haut vs baseline (= meilleur fit au scale). Si argmax(P) != 1e-4 =>"
say "  ADOPTER ce L2 dans la boucle d'iteration (0420) + tous les futurs fits (le 1e-4 etait cale a <=2M)."
say "  P > 0.55 => la 32cf PROGRESSE encore avec le volume (viser 100M). ~0.50 => debut de plateau. <0.45 => data bruitee."
say "==========================================="
