#!/usr/bin/env bash
# id: cpx62-0405-prod-loop-32cf
# description: BOUCLE DE PRODUCTION a archi FIGEE 32cf (verdict GATE 0401). Seed = w32_full (champion 32cf fitte sur
# 29M). On ACCUMULE (plus de fenetre 2M) : a chaque tour, gen self-play d10 pilotee par le champion courant ->
# APPEND au cumul -> refit train_stream (color-fold, gradient exact, sur TOUT le cumul) -> juge cross-arch vs champion
# precedent (et vs champ-3). Chaque tour SAUVE ses nouvelles parties en shard gzippe (durable, manifeste, futur
# object-store) => rien perdu, reprise possible. Auto-stop au plateau (3x <=0.52 + cumule <=0.53). Tout hors-tree,
# transport gzip, aucun Scan. La 32cf est sous-nourrie a 29M (3.4 visites/poids) -> le volume doit continuer a payer.
# expected_duration: ~8 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-720}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0405-prod-loop-32cf/artefacts"; mkdir -p "$ART"
W=/root/cw-prod; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000
PLAY_DEPTH=10; EVAL_DEPTH=4; MAX=3; CHUNK=1000000; MAXIT=25
TARGET_GEN_MIN=45; CAP=2000000; FLOOR=800000; JUDGE_PAIRS=20
PLAT_THR=0.52; PLAT_CUM=0.53
GEOM32=/root/jass-geom32
SEED=jobs/results/cpx62-0401-gate-matrix-2x2/artefacts/w32_full.pjtw.gz
preflight_build 1; preflight_train 32000000 1; preflight_note "boucle prod 32cf : assemble + ${MAX}x (gen d10 + refit train_stream + juge)" 200; preflight_check

# ---------- build 32-pat (memes flags que la gen corpus) ----------
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
B="$W/build-32"; cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/build.log"; exit 6; }
J="$B/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

# ---------- seed champion + assemble le cumul (tout le corpus committe) ----------
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$SEED" 2>/dev/null && { ok=1; break; }; sleep 20; done
[ "$ok" = 1 ] || { echo "ABORT: seed w32_full absent"; exit 4; }
git show "origin/main:$SEED" | gunzip > "$W/champion.pjtw"
echo "=== assemble le cumul depuis tous les shards corpus committes ==="
tools/corpus_manifest.sh assemble "$W/cum.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }
NCUM=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/cum.jnnw','rb').read(8)[4:8])[0])")
echo "=== cumul de depart : ${NCUM} positions ==="
[ "$NCUM" -ge 25000000 ] || { echo "ABORT: cumul ${NCUM} < 25M"; exit 8; }

# ---------- helpers ----------
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
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
fit(){ local data="$1" feat="$2" out="$3"
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$feat" \
    --color-fold --tempo-stage --loss logistic --l2 1e-4 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$out" \
    >"${out%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL $out"; tail -10 "${out%.pjtw}.log"; exit 9; }; }
pjudge(){ for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$1" \
    --jass-b "$J" --pattern-b "$2" --depth 9 --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
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

# ---------- la boucle (accumulation, archi figee 32cf) ----------
declare -a CH; CH[0]="$W/champion.pjtw"; TRAJ="$ART/trajectory.txt"; : > "$TRAJ"
echo "tour 0  cumul=${NCUM}  (seed w32_full 0401)" >>"$TRAJ"
plat=0; STOP=""
for r in $(seq 1 "$MAX"); do
  echo "=== TOUR $r : gen d10 (champion courant) + APPEND + refit train_stream + juge ==="
  t0=$(date +%s); gen "${CH[$((r-1))]}" $((NCPU*200)) "$W/probe" >/dev/null 2>&1; dt=$(( $(date +%s)-t0 )); [ "$dt" -lt 1 ] && dt=1
  NPER=$(( NCPU*200*60/dt*TARGET_GEN_MIN )); [ "$NPER" -gt "$CAP" ] && NPER="$CAP"; [ "$NPER" -lt "$FLOOR" ] && NPER="$FLOOR"; rm -f "$W/probe"
  gen "${CH[$((r-1))]}" "$NPER" "$W/new.jnnw"
  gzip -c "$W/new.jnnw" > "$ART/prod-0405-r${r}-corpus.jnnw.gz"   # shard DURABLE (manifeste)
  NCUM=$(app "$W/new.jnnw" "$W/cum.jnnw")
  "$J" --dump-eval-features "$W/cum.jnnw" "$W/feat" >"$W/feat-r$r.log" 2>&1
  fit "$W/cum.jnnw" "$W/feat" "$W/champ$r.pjtw"; CH[$r]="$W/champ$r.pjtw"
  SP=$(pjudge "${CH[$r]}" "${CH[$((r-1))]}")
  CUM="NA"; [ "$r" -ge 3 ] && CUM=$(pjudge "${CH[$r]}" "${CH[$((r-3))]}")
  echo "  TOUR $r : champ vs champ-1 = ${SP}   |  vs champ-3 = ${CUM}   (cumul=${NCUM}, NPER=${NPER})"
  echo "tour $r  vs_prev=${SP}  vs_3=${CUM}  cumul=${NCUM}  NPER=${NPER}" >>"$TRAJ"
  case "$SP" in
    ''|NA) plat=0; echo "  [warn] juge NA au tour $r";;
    *) awk "BEGIN{exit !(${SP}+0 <= $PLAT_THR)}" && plat=$((plat+1)) || plat=0;;
  esac
  if [ "$plat" -ge 3 ] && [ "$r" -ge 3 ] && awk "BEGIN{exit !(\"$CUM\"!=\"NA\" && $CUM <= $PLAT_CUM)}"; then
    STOP="PLATEAU au tour $r"; break; fi
done

cp "${CH[${#CH[@]}-1]}" "$W/champion-32cf.pjtw" 2>/dev/null || true
gzip -c "$W/champion-32cf.pjtw" > "$ART/champion-32cf.pjtw.gz" 2>/dev/null || true
cp "$TRAJ" "$ART/trajectory.txt" 2>/dev/null || true
echo; echo "=========================================================="
echo "   cpx62-0405 — BOUCLE PROD 32cf (accumulation, ${MAX} tours max)"
cat "$TRAJ" | sed 's/^/   /'
echo "   ${STOP:-pas encore de plateau -> relancer pour continuer (le cumul a grossi, shards durables)}"
echo "   champion final -> artefacts/champion-32cf.pjtw.gz ; nouvelles parties -> prod-0405-r*-corpus.jnnw.gz"
echo "=========================================================="
