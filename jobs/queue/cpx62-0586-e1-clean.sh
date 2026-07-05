#!/usr/bin/env bash
# id: cpx62-0586-e1-clean
# description: P3 (JFC) — RE-LECTURE E1 (8cf vs 32cf, learning-curve) sur un HOLDOUT PROPRE (split PAR PARTIE, pas par
# position). 0579 shufflait les positions => les positions d'une meme partie fuyaient train<->val => log-loss optimiste =>
# verdict "courbe plate" suspect. Fix anti-fuite : VAL = un SHARD de gen SEPARE (parties disjointes du train, zero same-game
# leakage), TRAIN = sous-ensembles croissants des autres shards. Ouvertures aleatoires par partie (pas de seed-file) =>
# pas de duplication inter-parties. Question : "le volume aide-t-il / 8cf~32cf" tient-il sur split propre ? Gen ANCIEN
# config (pas de fixes — E1 teste la geometrie/volume, pas l'hygiene). Code 8cf/holdout depuis DEVELOP. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0586-e1-clean/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0586-e1-clean/artefacts"
W=/root/cw-e1clean; rm -rf "$W"; mkdir -p "$W"; G8="$W/g8"; G32="$W/g32"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
FORCE="ext_forcing=1,forcing_ext_cap=6"; PD=6; LABEL_DEPTH=4; MAXPLIES=200
PERSHARD=350000; L2=3e-5; MAXIT=25; CHUNK=1000000
RANK="$W/rank.tsv"; : > "$RANK"; say(){ echo "$@" | tee -a "$W/run.log"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
cat_jnnw(){ python3 - "$@" <<'PY'
import struct,sys
out=sys.argv[1]; body=b""; tot=0
for f in sys.argv[2:]:
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}

say "=== P3 E1-clean : overlay develop (holdout-frac + 8cf) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/gen_patterns.py > pattern_jass/tools/gen_patterns.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; TOOLS="$(pwd)/pattern_jass/tools"
mkdir -p "$G8" "$G32"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v3 >/dev/null 2>&1 || true; cp pattern_jass/tools/patterns.py "$G8/patterns.py"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true; cp pattern_jass/tools/patterns.py "$G32/patterns.py"
N8=$(PYTHONPATH="$G8:$TOOLS" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>/dev/null)
N32=$(PYTHONPATH="$G32:$TOOLS" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>/dev/null)
[ "$N8" = 8 ] && [ "$N32" = 32 ] || { say "ABORT geom $N8/$N32"; exit 7; }
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
# NE PAS restaurer train_stream.py ici : les fits en ont besoin (version develop = --holdout-frac). main.cpp/gen_patterns OK.
git checkout -- src/main.cpp pattern_jass/tools/gen_patterns.py 2>/dev/null || true

# GEN NCPU shards (game-ordered, PAS de shuffle) ; shard 0 = VAL, shards 1..NCPU-1 = TRAIN pool
say "=== gen $NCPU shards @ pd$PD (~$PERSHARD/shard) — shard0=VAL, reste=TRAIN ==="
for s in $(seq 0 $((NCPU-1))); do "$J" --gen-data-wdl "$PERSHARD" "$W/shard.$s.jnnw" "$LABEL_DEPTH" "$PD" "$MAXPLIES" "$((RANDOM*RANDOM+s+1))" \
    --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE" --quiet-only --explore-eps 5 --random-open-plies 8 \
    >"$W/g_$s.log" 2>&1 & done; wait
mv "$W/shard.0.jnnw" "$W/VAL.jnnw"
VALN=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/VAL.jnnw','rb').read(8)[4:8])[0])")
cat_jnnw "$W/trainpool.jnnw" "$W"/shard.[1-9]*.jnnw >/dev/null
POOLN=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/trainpool.jnnw','rb').read(8)[4:8])[0])")
say "  VAL=$VALN (shard separe, parties disjointes) ; train pool=$POOLN"

# data_V = TRAIN(premiers V du pool) ++ VAL ; frac = VAL/(V+VAL) => holdout = VAL (parties disjointes = PROPRE)
mkdata(){ python3 - "$W/trainpool.jnnw" "$W/VAL.jnnw" "$1" "$2" <<'PY'
import struct,sys
tp=open(sys.argv[1],'rb').read(); vn=open(sys.argv[2],'rb').read(); REC=38
ntp=struct.unpack('<I',tp[4:8])[0]; V=min(int(sys.argv[3]),ntp)
train=tp[8:8+V*REC]; val=vn[8:]
recs=train+val; tot=len(recs)//REC
open(sys.argv[4],'wb').write(b'JNNW'+struct.pack('<I',tot)+recs); print(tot)
PY
}
fit_ll(){ local geom="$1" data="$2" feat="$3" frac="$4"
  JASS_PATTERNS_DIR="$geom" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prune-min-visits 1 --holdout-frac "$frac" --out "$W/c.pjtw" 2>&1 | grep -oE 'HOLDOUT_LOGLOSS [0-9.]+' | awk '{print $2}'; }

say "=== fits (val PROPRE = shard separe) ==="
for V in 500000 1000000 2000000; do
  [ "$V" -gt "$POOLN" ] && { say "  V=$V > pool, skip"; continue; }
  mkdata "$V" "$W/data.jnnw" >/dev/null
  FRAC=$(python3 -c "print($VALN/($V+$VALN))")
  "$J" --dump-eval-features "$W/data.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "dump $V FAIL"; continue; }
  for A in 8cf 32cf; do G="$G8"; [ "$A" = 32cf ] && G="$G32"
    LL=$(fit_ll "$G" "$W/data.jnnw" "$W/feat" "$FRAC"); [ -z "$LL" ] && LL=NA
    say "  V=$V $A : holdout=$LL"; echo -e "$V\t$A\t$LL" >>"$RANK"
  done
  rm -f "$W/feat" "$W/data.jnnw"
done

VERD="$ART/VERDICT.txt"
python3 - "$RANK" > "$VERD" <<'PY'
import sys
d={}
for l in open(sys.argv[1]):
    r=l.strip().split('\t')
    if len(r)<3: continue
    try: d[(int(r[0]),r[1])]=float(r[2])
    except: pass
print("=== VERDICT P3 E1-clean : holdout log-loss (val PROPRE = shard separe, pas de fuite) ===")
print(f"  {'train':>9} {'8cf':>10} {'32cf':>10}  {'ecart':>10}")
vols=sorted(set(k[0] for k in d))
for v in vols:
    a8=d.get((v,'8cf')); a32=d.get((v,'32cf'))
    if a8 is None or a32 is None: print(f"  {v:>9} {a8} {a32} (incomplet)"); continue
    print(f"  {v:>9} {a8:>10.5f} {a32:>10.5f}  {a32-a8:>+10.5f}")
print("")
for a in ('8cf','32cf'):
    xs=[(v,d[(v,a)]) for v in vols if d.get((v,a)) is not None]
    if len(xs)>=2: print(f"  {a} : "+"  ".join(f"{v//1000}k={ll:.5f}" for v,ll in xs)+f"  (delta {xs[-1][1]-xs[0][1]:+.5f})")
print("")
print("Comparer a 0579 (shufflé/fuite) : si la courbe DESCEND ici alors qu'elle etait plate en 0579 =>")
print("  la fuite masquait l'effet du volume => le verdict famine etait un ARTEFACT. Si toujours plate => tient.")
PY
cat "$VERD" | tee -a "$W/run.log"; cp "$RANK" "$ART/RANKING.tsv"
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0584 P3 E1-clean : holdout PROPRE (val=shard separe) 8cf vs 32cf ; la courbe plate de 0579 tient-elle sans fuite ?" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
