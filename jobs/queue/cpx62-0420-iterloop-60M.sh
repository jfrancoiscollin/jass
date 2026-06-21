#!/usr/bin/env bash
# id: cpx62-0420-iterloop-60M
# description: BOUCLE D'ITERATION 60M (systeme cible Scan-style) — la VRAIE iteration, pas l'accumulation de 0405.
# Chaque iteration REGENERE une LARGE fenetre fraiche PILOTEE PAR LE CHAMPION COURANT (qui s'ameliore), en MIX
# d10/d12 5:1 par COMPTE (5/6 d10 decisivite+volume, 1/6 d12 labels + precis ; ~2:1 en TEMPS car d12 ~2.5x plus lent),
# l'integre dans une fenetre glissante FIFO 40M (couverture saturee ~10-30M), refit 32cf, JUGE champion_k vs champion_{k-1}. Le pilote
# change vraiment a chaque tour => la progression devient MESURABLE (contrairement aux +0,8M figes de 0405). Levier =
# QUALITE/distribution des donnees (le moteur de Scan), pas le volume. Auto-stop au plateau. La data fraiche reste
# box-local (REGENERABLE ; on ne bloate pas git — la corpus durable reutilisable vient des maillons 0411-0418) ; SEULS
# les champions + la trajectoire sont committes. Self-contained UNE box (lecon cross-box). Hors-tree, gzip. Aucun Scan.
# >>> PARAMS AJUSTABLES (cout vs signal) en tete. expected_duration: ~MAX x ~10 h (gen-bound).
set -uo pipefail
cd /root/jass
# ----- params (cout <-> signal) -----
WINDOW=40000000          # fenetre glissante pour le FIT : 40M suffit (couverture saturee ~10-30M, cf BOUCLE §10.1)
FRESH=8000000            # data FRAICHE / iteration, pilotee par le champion COURANT (la vraie iteration ; ~20% turnover)
DEEP_DEPTH=12; DEEP_NUM=1; DEEP_DEN=6  # MIX d10/d12 : 1/6 FRESH en d12 (labels+precis), 5/6 en d10 (decisivite+volume) = 5:1 par COMPTE (~2:1 en TEMPS, d12 ~2.5x plus lent)
MAX=4                    # nb d'iterations (job re-lancable : re-seed avec le dernier champion pour continuer)
PLAY_DEPTH=10; EVAL_DEPTH=4   # d>=10 = issues veridiques (non negociable) ; d10 = profondeur DOMINANTE du mix
CHUNK=1000000; MAXIT=25; JUDGE_PAIRS=28
PLAT_THR=0.52; PLAT_CUM=0.53  # auto-stop : champ_k vs champ_{k-1} <= 0.52 x3 consecutifs ET vs champ_{k-3} <= 0.53
SEED_CH=jobs/results/cpx62-0401-gate-matrix-2x2/artefacts/w32_full.pjtw.gz  # graine = meilleur 32cf connu au lancement
# -------------------------------------
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-600}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0420-iterloop-60M/artefacts"; mkdir -p "$ART"
W=/root/cw-iterloop; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-iter; TRAJ="$ART/trajectory.txt"; : > "$TRAJ"

preflight_build 1; preflight_train "$WINDOW" 1; preflight_note "iterloop 60M : ${MAX}x (gen ${FRESH} + FIFO + refit + juge)" 200; preflight_check

# ---------- build 32-pat (memes flags) + seed champion + pool initial ----------
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb"; exit 6; }
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { echo "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git cat-file -e "origin/main:$SEED_CH" 2>/dev/null || { echo "ABORT: graine $SEED_CH absente"; exit 4; }
git show "origin/main:$SEED_CH" | gunzip > "$W/champ0.pjtw"

echo "=== pool initial : assemble le corpus committe -> fenetre glissante (<=${WINDOW}) ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { echo "ABORT assemble"; tail "$W/assemble.log"; exit 8; }

# ---------- helpers (gen/app preuves de 0405 ; trim FIFO nouveau, memory-light) ----------
gen(){ local pilot="$1" nn="$2" out="$3" depth="${4:-$PLAY_DEPTH}"; local per=$(( (nn+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$EVAL_DEPTH" "$depth" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >/dev/null 2>&1 & done; wait
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
trim(){ python3 - "$1" "$2" <<'PY'   # garde les W DERNIERES lignes (FIFO : jette les plus VIEILLES) ; memory-light
import struct,sys,os,shutil; REC=38
acc=sys.argv[1]; Wn=int(sys.argv[2])
with open(acc,'rb') as f:
    hdr=f.read(8); n=struct.unpack('<I',hdr[4:8])[0]
    if n<=Wn: print(n); sys.exit(0)
    f.seek(8+(n-Wn)*REC); tmp=acc+'.trim'
    with open(tmp,'wb') as o:
        o.write(b'JNNW'+struct.pack('<I',Wn)); shutil.copyfileobj(f,o,1<<24)
os.replace(tmp,acc); print(Wn)
PY
}
fit(){ env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$1" --feat "$2" \
    --color-fold --tempo-stage --loss logistic --l2 1e-4 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$3" \
    >"${3%.pjtw}.log" 2>&1 || { echo "TRAIN FAIL $3"; tail -10 "${3%.pjtw}.log"; exit 9; }; }
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

# ---------- la boucle d'iteration (archi 32cf figee ; pilote ameliorant ; fenetre glissante) ----------
NP0=$(trim "$W/pool.jnnw" "$WINDOW")
declare -a CH; CH[0]="$W/champ0.pjtw"
echo "iter 0  pool=${NP0}  (graine = w32_full 0401)  WINDOW=${WINDOW} FRESH=${FRESH}" | tee -a "$TRAJ"
plat=0; STOP=""
for k in $(seq 1 "$MAX"); do
  echo "=== ITER $k : gen ${FRESH} mix d${PLAY_DEPTH}/d${DEEP_DEPTH} 5:1 (champion_$((k-1))) -> FIFO ${WINDOW} -> refit -> juge ==="
  # MIX d10/d12 (5:1 par compte) : 1/6 de FRESH en d12 (labels + precis), 5/6 en d10 (decisivite + volume)
  ND12=$(( FRESH*DEEP_NUM/DEEP_DEN )); ND10=$(( FRESH - ND12 ))
  gen "${CH[$((k-1))]}" "$ND10" "$W/new10.jnnw" "$PLAY_DEPTH"
  gen "${CH[$((k-1))]}" "$ND12" "$W/new12.jnnw" "$DEEP_DEPTH"
  rm -f "$W/new.jnnw"; app "$W/new10.jnnw" "$W/new.jnnw" >/dev/null; app "$W/new12.jnnw" "$W/new.jnnw" >/dev/null
  echo "    mix gen : ${ND10} @d${PLAY_DEPTH} + ${ND12} @d${DEEP_DEPTH}"
  NTOT=$(app "$W/new.jnnw" "$W/pool.jnnw")
  NPOOL=$(trim "$W/pool.jnnw" "$WINDOW")           # jette les plus vieilles (data du pilote le plus faible)
  "$J" --dump-eval-features "$W/pool.jnnw" "$W/feat" >"$W/feat-k$k.log" 2>&1 || { echo "ABORT dump feat k$k"; exit 8; }
  fit "$W/pool.jnnw" "$W/feat" "$W/champ$k.pjtw"; CH[$k]="$W/champ$k.pjtw"
  gzip -c "$W/champ$k.pjtw" > "$ART/champion-iter${k}.pjtw.gz"   # champion DURABLE (petit)
  SP=$(pjudge "${CH[$k]}" "${CH[$((k-1))]}")
  CUM="NA"; [ "$k" -ge 3 ] && CUM=$(pjudge "${CH[$k]}" "${CH[$((k-3))]}")
  echo "  ITER $k : champ vs champ-1 = ${SP}   |  vs champ-3 = ${CUM}   (pool=${NPOOL}, turnover ${FRESH}/${WINDOW})"
  echo "iter $k  vs_prev=${SP}  vs_3=${CUM}  pool=${NPOOL}" | tee -a "$TRAJ" >/dev/null
  cp "$TRAJ" "$ART/trajectory.txt"
  case "$SP" in
    ''|NA) plat=0; echo "  [warn] juge NA a l'iter $k";;
    *) awk "BEGIN{exit !(${SP}+0 <= $PLAT_THR)}" && plat=$((plat+1)) || plat=0;;
  esac
  if [ "$plat" -ge 3 ] && [ "$k" -ge 3 ] && awk "BEGIN{exit !(\"$CUM\"!=\"NA\" && $CUM <= $PLAT_CUM)}"; then
    STOP="PLATEAU a l'iter $k (3x <=${PLAT_THR} + cumule <=${PLAT_CUM})"; break; fi
done

LAST=${#CH[@]}; LAST=$((LAST-1))
cp "${CH[$LAST]}" "$W/champion-iterloop.pjtw" 2>/dev/null || true
gzip -c "$W/champion-iterloop.pjtw" > "$ART/champion-iterloop-final.pjtw.gz" 2>/dev/null || true
echo; echo "=========================================================="
echo "   cpx62-0420 — BOUCLE ITERATION 60M (Scan-style, ${MAX} iters max)"
cat "$TRAJ" | sed 's/^/   /'
echo "   LECTURE : vs_prev > 0.55 a chaque iter = ca PROGRESSE (le pilote ameliorant paie). vs_3 cumule la progression."
echo "   ${STOP:-pas de plateau -> RE-LANCER (re-seed SEED_CH=champion-iterloop-final) pour continuer la boucle}"
echo "   champion final -> artefacts/champion-iterloop-final.pjtw.gz"
echo "=========================================================="
