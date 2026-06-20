#!/usr/bin/env bash
# id: cpx62-0383-fit-scaling-test
# description: TEST DÉCISIF "scaler le fit" (priorité JFC). Hypothèse : la fenêtre 2M plafonne ARTIFICIELLEMENT (elle
# expulse les buckets rares → jamais leurs 30-50 visites) ; le vrai plafond est à des dizaines-centaines de M.
# DÉCOUVERTE : --minibatch supporte DÉJÀ la logistique (train_lbfgs_chunked a la branche sigmoïde ; le "L2-only"
# visait les ancres). Donc on peut fitter ~10-15M sans OOM, SANS changement de code. Ici : on assemble ~5M (gen d10
# frais piloté champion + d12 de 0374/0382), on fit champion_BIG via --minibatch --loss logistic, et on le compare EN
# DIRECT au champion 2M (0378). champion_BIG > 0.55 → la fenêtre 2M ÉTAIT le mur → on bascule la boucle en accumulation
# + minibatch (et plus tard streaming-disque pour 100M). ≈0,5 → 2M suffisait (surprenant). Tout hors-tree, gzip.
# expected_duration: ~3 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-240}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0383-fit-scaling-test/artefacts"; mkdir -p "$ART"
W=/root/cw-scale; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000
PLAY_DEPTH=10; EVAL_DEPTH=4; D10_TARGET=3500000; MB=600000
CH=jobs/results/cpx62-0378-champion-geometry/artefacts/champion.pjtw.gz
D12A=jobs/results/ccx33-0375-salvage-d12/artefacts/d12-data.jnnw
D12B=jobs/results/ccx33-0382-d12-diversity/artefacts/d12-diversity.jnnw.gz
preflight_build 1; preflight_train 5000000 2; preflight_note "gen ~3.5M d10 + minibatch fit BIG vs 2M" 150; preflight_check

echo "=== champion 0378 (pilote + baseline 2M) ==="
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$CH" 2>/dev/null && { ok=1; break; }; echo "  attente 0378 ($i)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: champion 0378 absent"; exit 4; }
git show "origin/main:$CH" | gunzip > "$W/champ2M.pjtw"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
B="$W/build"; cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/build.log"; exit 6; }
JASS="$B/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

gen(){ local nn="$1" out="$2"; local per=$(( (nn+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do "$JASS" --gen-data-wdl "$per" "$out.$s" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$W/champ2M.pjtw" >/dev/null 2>&1 & done; wait
  python3 - "$out" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
  rm -f "$out".[0-9]* ; }
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc):
    raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
echo "=== assemble le pool BIG : ${D10_TARGET} d10 frais + d12 (0374,0382) ==="
N=0; while [ "$N" -lt "$D10_TARGET" ]; do gen 500000 "$W/b" >/dev/null 2>&1; N=$(app "$W/b" "$W/big.jnnw"); echo "  d10 accumulé $N"; done
git show "origin/main:$D12A" > "$W/d12a.jnnw" 2>/dev/null && app "$W/d12a.jnnw" "$W/big.jnnw" >/dev/null || echo "  (d12 0375 indispo)"
git show "origin/main:$D12B" 2>/dev/null | gunzip > "$W/d12b.jnnw" && app "$W/d12b.jnnw" "$W/big.jnnw" >/dev/null || echo "  (d12 0382 pas encore prêt)"
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/big.jnnw','rb').read(8)[4:8])[0])")
echo "  POOL BIG = ${NBIG} positions"

fitmb(){ local data="$1" out="$2"
  "$JASS" --dump-eval-features "$data" "$W/feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$data" --scan-eval --eval-features-file "$W/feat" \
    --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --minibatch "$MB" --full-fold \
    --out "$out" >"${out%.pjtw}-tr.log" 2>&1; [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -10 "${out%.pjtw}-tr.log"; exit 9; }; }
echo "=== fit champion_BIG sur ${NBIG} (--minibatch ${MB} --loss logistic) ==="
fitmb "$W/big.jnnw" "$W/champBIG.pjtw"
grep -iE "minibatch|train_loss|LOGISTIC" "$W/champBIG-tr.log" | head -3 | sed 's/^/  [fit] /'

echo "=== DIRECT : champion_BIG (${NBIG}) vs champion_2M (0378) — juge parallèle N≈1000 ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$JASS" --pattern-a "$W/champBIG.pjtw" \
  --jass-b "$JASS" --pattern-b "$W/champ2M.pjtw" --depth 9 --pairs 28 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
R=$(python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f}  (N={g})" if g else "NA")
PY
)
gzip -c "$W/champBIG.pjtw" > "$ART/champBIG.pjtw.gz" 2>/dev/null || true
echo; echo "=========================================================="
echo "   cpx62-0383 — TEST SCALE DU FIT : BIG(${NBIG}) vs 2M(0378)"
echo "   champion_BIG vs champion_2M = ${R}"
echo "----------------------------------------------------------"
echo "   > 0.55 → la fenêtre 2M ÉTAIT le mur → basculer la boucle en ACCUMULATION + minibatch (puis streaming pour 100M)."
echo "   ≈ 0.5  → 2M suffisait à ce stade (le rare-bucket ne paie pas encore) → re-tester à plus gros volume."
echo "=========================================================="