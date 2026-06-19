#!/usr/bin/env bash
# id: cpx62-0371-round-refit
# description: TOUR 1 boucle distribuée poolée — cpx62 (CAP RELEVÉ). Génère sa part d10 GROS piloté par le champion
# (NPER=débit×30min, plafond 800k ≈ 720k), tire le shard d12 de ccx33-0370, ÉTEND le pool durable (pooled.jnnw de
# 0369) avec les deux nouveaux shards, RE-FIT → champion2, juge champion2 vs champion en DIRECT (le tour a-t-il
# amélioré ?), committe champion2.pjtw + le pool (fenêtre glissante ≤2M pour rester sous le cap git 95Mo). C'est UN
# tour de la boucle ; on l'enchaîne (champion2 → tour 2 → …). DÉPLOYER après 0369 + 0370. Aucun Scan.
# expected_duration: ~70 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0371-round-refit/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
PLAY_DEPTH=10; EVAL_DEPTH=4; SCALE=1000; TARGET_GEN_MIN=30; CAP=800000; POOL_KEEP=2000000
CHAMP_PATH=jobs/results/cpx62-0369-merge-champion/artefacts/champion.pjtw
POOL_PATH=jobs/results/cpx62-0369-merge-champion/artefacts/pooled.jnnw
D12_PATH=jobs/results/ccx33-0370-round-gen-d12/artefacts/round1-d12.jnnw
preflight_build 1; preflight_train 2500000 1; preflight_note "gen d10 cap relevé + pool + refit champion2" 110; preflight_check

echo "=== récupère champion + pool (0369) et attend le shard d12 (0370) ==="
fetch_one(){ local p="$1" out="$2"; local ok=0
  for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
    git cat-file -e "origin/main:$p" 2>/dev/null && { ok=1; break; }; echo "  attente $p ($i/24)"; sleep 30; done
  [ "$ok" = 1 ] || { echo "ABORT: $p absent"; exit 4; }; git show "origin/main:$p" > "$out"; }
fetch_one "$CHAMP_PATH" "$ART/champion.pjtw"
fetch_one "$POOL_PATH"  "$ART/pool.jnnw"
fetch_one "$D12_PATH"   "$ART/round1-d12.jnnw"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
B=build-prod; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

gen(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    "$JASS" --gen-data-wdl "$per" "$out.$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >"$out.$s.log" 2>&1 &
  done; wait
  python3 - "$out" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*.jnnw"),key=lambda p:int(re.search(r"\.(\d+)\.jnnw$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print('shard',tot)
PY
  rm -f "$out".*.jnnw
}
echo "=== sonde débit @ d${PLAY_DEPTH} → NPER (cap relevé ${CAP}) ==="
t0=$(date +%s); gen "$ART/champion.pjtw" $((NCPU*200)) "$ART/probe" >/dev/null 2>&1; dt=$(( $(date +%s) - t0 )); [ "$dt" -lt 1 ] && dt=1
RATE=$(( NCPU*200*60/dt )); NPER=$(( RATE*TARGET_GEN_MIN )); [ "$NPER" -lt 100000 ] && NPER=100000; [ "$NPER" -gt "$CAP" ] && NPER="$CAP"
echo "  débit ≈ ${RATE} pos/min @ d10 → NPER=${NPER}"; rm -f "$ART/probe"

echo "=== génération d10 du tour (NPER=${NPER}) ==="
gen "$ART/champion.pjtw" "$NPER" "$ART/round1-d10.jnnw"

echo "=== étend le pool (pool ∪ d10 ∪ d12), fenêtre glissante ≤${POOL_KEEP} (cap git) ==="
python3 - "$ART/pool.jnnw" "$ART/round1-d10.jnnw" "$ART/round1-d12.jnnw" "$ART/pooled2.jnnw" "$POOL_KEEP" <<'PY'
import struct,sys
REC=38; keep=int(sys.argv[5]); parts=sys.argv[1:4]; out=sys.argv[4]
chunks=[]; tot=0
for p in parts:
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; chunks.append((n,b[8:8+n*REC])); tot+=n
body=b"".join(c[1] for c in chunks)
n_all=tot
if n_all>keep: body=body[(n_all-keep)*REC:]; n_all=keep   # garde les plus RÉCENTS (évals + fortes)
open(out,'wb').write(b'JNNW'+struct.pack('<I',n_all)+body)
print(f"  pool {parts}: tot={tot} -> gardé {n_all} ({n_all*REC/1e6:.1f} Mo)")
PY

echo "=== RE-FIT champion2 sur le pool étendu (logistique full-fold) ==="
"$JASS" --dump-eval-features "$ART/pooled2.jnnw" "$ART/pooled2.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$ART/pooled2.jnnw" --scan-eval --eval-features-file "$ART/pooled2.feat" \
  --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem --full-fold \
  --out "$ART/champion2.pjtw" >"$ART/champion2-train.log" 2>&1
[ -f "$ART/champion2.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/champion2-train.log"; exit 9; }

echo "=== champion2 vs champion (DIRECT) — le tour a-t-il amélioré ? ==="
"$JASS" --benchmark-nnue-vs-nnue "$ART/champion2.pjtw" "$ART/champion.pjtw" 9 6 1 0 >"$ART/c2_vs_c1.log" 2>&1 || true
C2=$(grep -E 'score rate' "$ART/c2_vs_c1.log" | grep -oE '[0-9.]+' | head -1)
cp "$ART/pooled2.jnnw" "$ART/pooled.jnnw"   # nom stable pour le prochain tour

echo; echo "=========================================================="
echo "   cpx62-0371 — TOUR 1 boucle distribuée poolée (cap relevé)"
echo "   champion2 vs champion = ${C2}   (>0.5 → le tour a amélioré → enchaîner tour 2)"
echo "   pool durable committé (champion2.pjtw + pooled.jnnw) pour le prochain tour."
echo "=========================================================="