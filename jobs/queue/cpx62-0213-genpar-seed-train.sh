#!/usr/bin/env bash
# id: cpx62-0213-genpar-seed-train
# description: 2-BOX HARNESS, réducteur CPX62. Génère SA part (2M, 16 shards) du corpus
# seed commun, puis BARRIÈRE : attend que ccx33-0212 ait fini (en LISANT origin/main —
# que le runner rafraîchit tout seul toutes les 5 min, donc AUCUNE op git côté job →
# zéro contention), récupère ses 8 shards committés, FUSIONNE les 24 shards (3M au
# total) et entraîne en --prune (≈50× moins cher). Prouve qu'on cumule CCX33+CPX62
# (24 cœurs) pour UN même jeu de données. Mesure proxy + couverture + le temps gen vs
# attente vs train. NB : git transporte les SHARDS (≤95MB chacun) ; pour la boucle
# ITÉRÉE 2-box il faudra aussi transporter l'eval (136MB>cap → format dense C++ ou
# object store) — noté comme suite.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0213-genpar-seed-train/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
PEER=ccx33-0212-genpar-seed
PEERART="jobs/results/$PEER/artefacts"
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- CPX62's share : 2M over 16 shards (embedded net, depth4), same generator as CCX33 ---
SHARE=2000000; PER=$(( (SHARE + NCPU - 1) / NCPU ))
t_gen0=$(date +%s)
echo "CPX62 generating $((PER*NCPU)) positions over $NCPU shards (embedded net, depth4)"
for s in $(seq 1 "$NCPU"); do
  $JASS --gen-data-wdl "$PER" "$ART/cpx-$s.jnnw" 6 4 200 $((s*200003 + 29)) >"$ART/cpx-$s.log" 2>&1 &
done
wait
t_gen1=$(date +%s); echo "CPX62 gen done in $((t_gen1-t_gen0))s"

# --- BARRIER : wait for CCX33's peer to finish (read origin/main, refreshed by the runner) ---
echo "barrier: waiting for $PEER to complete on main ..."
t_b0=$(date +%s); DEADLINE=$(( t_b0 + 5400 ))   # 90 min cap
while :; do
  st=$(git show "origin/main:jobs/results/$PEER/status.json" 2>/dev/null | grep -oE '"state": "[^"]*"' | cut -d'"' -f4)
  [ "$st" = "completed" ] && { echo "  peer completed"; break; }
  [ "$st" = "failed" ] && { echo "  peer FAILED — proceeding with CPX62 shards only"; break; }
  [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "  barrier TIMEOUT — proceeding with CPX62 shards only"; break; }
  sleep 60
done
t_b1=$(date +%s); echo "barrier waited $((t_b1-t_b0))s"

# --- pull the peer's committed shards via read-only git show (no index/worktree touch) ---
peer_n=0
for k in $(seq 1 64); do
  if git show "origin/main:$PEERART/sh-$k.jnnw" >"$ART/peer-$k.jnnw" 2>/dev/null && [ -s "$ART/peer-$k.jnnw" ]; then
    peer_n=$k
  else rm -f "$ART/peer-$k.jnnw"; break; fi
done
echo "pulled $peer_n peer shards from $PEER"

# --- merge ALL shards (CPX62 local + CCX33 peer) into one corpus ---
python3 - "$ART" <<'PY'
import struct,glob,sys,re,os
art=sys.argv[1]; REC=38
shards=sorted(glob.glob(art+"/cpx-*.jnnw")) + sorted(glob.glob(art+"/peer-*.jnnw"))
out=open(art+"/corpus.jnnw",'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',0)); tot=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; out.write(b[8:8+n*REC])
out.seek(4); out.write(struct.pack('<I',tot)); out.close()
print("merged",len(shards),"shards ->",tot,"positions")
PY
rm -f "$ART"/cpx-*.jnnw "$ART"/peer-*.jnnw
CORP="$ART/corpus.jnnw"
TOT=$(python3 -c "import struct;print(struct.unpack('<I',open('$CORP','rb').read(8)[4:8])[0])")

# --- train the pooled seed with --prune (cheap) + proxy + coverage ---
$JASS --dump-eval-features "$CORP" "$ART/feat" 2>&1 | tail -1
t_tr0=$(date +%s)
python3 pattern_jass/tools/train.py --data "$CORP" --scan-eval --eval-features-file "$ART/feat" \
  --loss logistic --l2 3e-2 --max-iter 200 --scale 1000 --prune --out "$ART/seed.pjtw" >"$ART/train.log" 2>&1
t_tr1=$(date +%s)
grep -E "prune|design|train_loss|wrote" "$ART/train.log" | tail -4
PRX=$(python3 tools/eval_proxy.py --jass "$JASS" --eval "$ART/seed.pjtw" --testset "$REF" \
        --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2)
COV=$(python3 tools/bucket_coverage.py "$CORP" 2>/dev/null | grep -E "Chao1|observe 95" | tr '\n' ' ')

echo; echo "=========================================================="
echo "   cpx62-0213 — HARNESS 2-BOX (CCX33+CPX62) — UN corpus, 24 cœurs"
echo "  positions totales = $TOT  (CPX62 2M @16c  +  CCX33 ~1M @8c, fusionnés via git)"
echo "  temps : gen CPX62=$((t_gen1-t_gen0))s · attente barrière=$((t_b1-t_b0))s · train(--prune)=$((t_tr1-t_tr0))s"
echo "  seed proxy (Spearman vs Scan-d10) = $PRX"
echo "  $COV"
echo "  → prouve le pooling 2-box pour un même jeu de données ; le train --prune"
echo "    rend la fusion exploitable en minutes. Suite : boucle ITÉRÉE 2-box"
echo "    (transporter l'eval entre gens : format dense C++ ~6MB < cap, ou object store)."
echo "=========================================================="
