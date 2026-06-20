#!/usr/bin/env bash
# id: cpx62-0380-virtuous-loop-auto
# description: BOUCLE VERTUEUSE AUTONOME avec AUTO-STOP (toute l'archi des leçons). Self-contained sur cpx62 (pas de
# cross-box fragile), TOUT hors du tree (/root/cw-loop, immunisé au clean runner), transport gzip. Graine = champion +
# pool 2M de 0378. Chaque tour : gen d10 (cap relevé, piloté par le champion) → pool (fenêtre glissante 2M) → refit
# champion (full-fold) → JUGE PARALLÈLE (jass_vs_jass_arch shardé sur les cœurs, N≈1000) champion_k vs champion_{k-1}.
# AUTO-STOP : plateau = champ_k vs champ_{k-1} ≤ 0,52 (≈0,5+1σ@1000) 3 tours de suite ET champ_k vs champ_{k-3} ≤ 0,53.
# Tous les 2 tours : bake-off géométrie (32cf vs 8cf cross-arch) = la courbe archi vs volume. Au plateau → "ressortir
# Scan". Committe la trajectoire + champion gzippé à la fin. MAX 5 tours (garde-fou watchdog). Aucun Scan en boucle.
# expected_duration: ~3.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-260}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0380-virtuous-loop-auto/artefacts"; mkdir -p "$ART"
W=/root/cw-loop; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000; GEOM=/root/jass-geom-lean8
PLAY_DEPTH=10; EVAL_DEPTH=4; TARGET_GEN_MIN=20; CAP=600000; POOL_KEEP=2000000
MAX=5; JUDGE_PAIRS=28; PLAT_THR=0.52; PLAT_CUM=0.53     # N≈1008 parties ; 1σ@1000≈1.6%
SEED_CH=jobs/results/cpx62-0378-champion-geometry/artefacts/champion.pjtw.gz
SEED_POOL=jobs/results/cpx62-0378-champion-geometry/artefacts/pooled-2M.jnnw.gz
preflight_build 1; preflight_train 2000000 "$MAX"; preflight_note "boucle auto ${MAX} tours (gen d10 + refit + juge parallèle)" 180; preflight_check

echo "=== graine : champion + pool de 0378 ==="
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$SEED_CH" 2>/dev/null && { ok=1; break; }; echo "  attente 0378 ($i)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: champion 0378 absent (0378 a échoué ?)"; exit 4; }
git show "origin/main:$SEED_CH"  | gunzip > "$W/champion.pjtw"
git show "origin/main:$SEED_POOL" | gunzip > "$W/pool.jnnw"
echo "  pool graine = $(python3 -c "import struct;print(struct.unpack('<I',open('$W/pool.jnnw','rb').read(8)[4:8])[0])")"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake_jass(){ cmake -S . -B "$1" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cm-$(basename "$1").log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$W/cm-$(basename "$1").log" || { echo "ABORT egdb"; exit 6; }
  cmake --build "$1" -j"$(mem_safe_jobs)" --target jass >"$W/bd-$(basename "$1").log" 2>&1 || { echo "BUILD FAIL $1"; tail -8 "$W/bd-$(basename "$1").log"; exit 6; }; }
echo "=== build 32-pat ==="; cmake_jass "$W/build-32"; J="$W/build-32/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

# génère <n> positions piloté par <pilot> → <out>
gen(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >/dev/null 2>&1 & done; wait
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
# fit logistique sur le pool W/pool.jnnw + W/feat
fit(){ local extra="$1" out="$2" pdir="$3"
  ${pdir:+env JASS_PATTERNS_DIR=$pdir} python3 pattern_jass/tools/train.py --data "$W/pool.jnnw" --scan-eval \
    --eval-features-file "$W/feat" --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem $extra \
    --out "$out" >"${out%.pjtw}-tr.log" 2>&1; [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -6 "${out%.pjtw}-tr.log"; exit 9; }; }
# JUGE PARALLÈLE : <binA> <pA> <binB> <pB> → taux A (N≈18*JUDGE_PAIRS*2 ≈ 1008), shardé sur NCPU
pjudge(){ local ja="$1" pa="$2" jb="$3" pb="$4"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$ja" --pattern-a "$pa" \
    --jass-b "$jb" --pattern-b "$pb" --depth 9 --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f}" if g else "NA")
PY
  rm -f "$W"/j.* ; }

declare -a CH RA; CH[0]="$W/champion.pjtw"; TRAJ="$W/trajectory.txt"; : > "$TRAJ"
plat=0; STOP=""
for r in $(seq 1 "$MAX"); do
  echo "=== TOUR $r : gen d10 + refit + juge parallèle ==="
  "$J" --dump-eval-features "$W/pool.jnnw" "$W/feat" >/dev/null 2>&1
  # débit -> NPER (cap relevé)
  t0=$(date +%s); gen "${CH[$((r-1))]}" $((NCPU*200)) "$W/probe" >/dev/null 2>&1; dt=$(( $(date +%s)-t0 )); [ "$dt" -lt 1 ] && dt=1
  NPER=$(( NCPU*200*60/dt*TARGET_GEN_MIN )); [ "$NPER" -gt "$CAP" ] && NPER="$CAP"; [ "$NPER" -lt 100000 ] && NPER=100000; rm -f "$W/probe"
  gen "${CH[$((r-1))]}" "$NPER" "$W/new.jnnw"
  # étend le pool, fenêtre glissante POOL_KEEP (garde les + récents)
  python3 - "$W/pool.jnnw" "$W/new.jnnw" "$POOL_KEEP" <<'PY'
import struct,sys; REC=38; keep=int(sys.argv[3])
def rd(p): b=open(p,'rb').read(); return struct.unpack('<I',b[4:8])[0], b[8:]
n0,b0=rd(sys.argv[1]); n1,b1=rd(sys.argv[2]); body=b0+b1; n=n0+n1
if n>keep: body=body[(n-keep)*REC:]; n=keep
open(sys.argv[1],'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(f"pool={n}")
PY
  "$J" --dump-eval-features "$W/pool.jnnw" "$W/feat" >/dev/null 2>&1
  fit "--full-fold" "$W/champ$r.pjtw" ""; CH[$r]="$W/champ$r.pjtw"
  RA[$r]=$(pjudge "$J" "${CH[$r]}" "$J" "${CH[$((r-1))]}")
  CUM="NA"; [ "$r" -ge 3 ] && CUM=$(pjudge "$J" "${CH[$r]}" "$J" "${CH[$((r-3))]}")
  echo "  TOUR $r : champ vs champ-1 = ${RA[$r]}   |  vs champ-3 = ${CUM}   (pool ↑, NPER=$NPER)"
  echo "tour $r  vs_prev=${RA[$r]}  vs_3=${CUM}  NPER=$NPER" >>"$TRAJ"
  # bake-off géométrie tous les 2 tours
  if [ $((r%2)) -eq 0 ]; then
    fit "--color-fold" "$W/e32.pjtw" ""
    python3 pattern_jass/tools/gen_patterns.py --emit --drop diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3 >"$W/g8.log" 2>&1
    cmake_jass "$W/build-8"; rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
    fit "--color-fold" "$W/e8.pjtw" "$GEOM"
    GEO=$(pjudge "$W/build-32/jass" "$W/e32.pjtw" "$W/build-8/jass" "$W/e8.pjtw")
    echo "  [bake-off] 32cf vs 8cf = ${GEO}   (⚠️ pool encore petit → 32cf sous-fitté, on suit la PENTE)"
    echo "  bakeoff tour $r  32cf_vs_8cf=${GEO}" >>"$TRAJ"
    # le build-8 a émis la géométrie 8 dans le tree ; on restaure 32 pour le tour suivant
    git checkout -- pattern_jass/src/pattern.hpp pattern_jass/tools/patterns.py pattern_jass/tests/run_tests.cpp 2>/dev/null || true
  fi
  # auto-stop : plateau (garde contre un juge NA = échec, qui ne doit PAS compter comme plateau)
  case "${RA[$r]}" in
    ''|NA) plat=0; echo "  [warn] juge NA au tour $r";;
    *) awk "BEGIN{exit !(${RA[$r]}+0 <= $PLAT_THR)}" && plat=$((plat+1)) || plat=0;;
  esac
  if [ "$plat" -ge 3 ] && [ "$r" -ge 3 ] && awk "BEGIN{exit !(\"$CUM\"!=\"NA\" && $CUM <= $PLAT_CUM)}"; then
    STOP="PLATEAU au tour $r (3× ≤${PLAT_THR} + cumulé ≤${PLAT_CUM})"; break; fi
done

cp "${CH[${#CH[@]}-1]}" "$W/champion-final.pjtw" 2>/dev/null || cp "${CH[$MAX]}" "$W/champion-final.pjtw" 2>/dev/null || true
gzip -c "$W/champion-final.pjtw" > "$ART/champion-final.pjtw.gz" 2>/dev/null || true
gzip -c "$W/pool.jnnw" > "$ART/pool-final.jnnw.gz" 2>/dev/null || true
cp "$TRAJ" "$ART/trajectory.txt"
echo; echo "=========================================================="
echo "   cpx62-0380 — BOUCLE VERTUEUSE AUTO (trajectoire)"; cat "$TRAJ"
echo "----------------------------------------------------------"
echo "   ${STOP:-MAX $MAX tours atteint (pas encore de plateau → relancer pour continuer)}"
echo "   → si PLATEAU : c'est ICI qu'on ressort Scan (depth-égale) pour situer le niveau."
echo "=========================================================="