#!/usr/bin/env bash
# id: cpx62-0479-selfplay-pruningoff-ab
# description: TEST de l'insight Scan (recherche 2026-06-27) : Scan = pur self-play depuis zero, SANS prof. Notre mur probable :
# notre elagage bake (multicut/razor) CACHE ~40%% des shots a profondeur fixe (0446) => pendant notre GEN self-play, ces shots
# ne sont jamais joues/punis dans le playout => nos labels WDL restent AVEUGLES => eval shot-blind. Fix teste ici : generer le
# self-play avec --search-params ELAGAGE OFF (full-width) => le playout JOUE et PUNIT les shots dans l'horizon => les labels
# enseignent enfin la securite tactique (recette Scan). A/B propre : meme pilote (egdbmix), meme self-play normal (open-plies
# alea, PAS de seeds dilf = set de test), meme play_depth 8, meme volume ; SEULE difference = elagage ON vs OFF au gen. Fit
# (gen + egdb-finale baked) -> juge 0440 + IC95 vs egdbmix (0.302). Si OFF >> ON et > 0.35 => l'elagage aveuglait nos labels =>
# on tient la recette Scan => scaler + bootstrap. 100%% lineaire, self-play, sans prof, sans NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0479-selfplay-pruningoff-ab/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-pruneoff79; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
GEOM32=/root/jass-geom32-pruneoff79
NGEN=5000000; NEGDB=4000000; EVALDEPTH=4; PLAYDEPTH=8; OPEN=8
OFF="rfp_max_depth=0,nmp_min_depth=99,lmr_min_depth=99,lmp_max_depth=0,razor_max_depth=0,multicut_min_depth=0,probcut_min_depth=0"
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — gate 0440 a faire ailleurs)"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON (avec --search-params au gen) ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]; o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
merge(){ python3 - "$1" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
rm -f "$1".[0-9]* ; }

# gen self-play sharde ; $1=tag $2=search-spec(""|OFF)
gen_arm(){ local tag="$1" spec="$2"; local per=$(( (NGEN+NCPU-1)/NCPU )); local sa=""
  [ -n "$spec" ] && sa="--search-params $spec"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/$tag.jnnw.$s" "$EVALDEPTH" "$PLAYDEPTH" 200 "$((RANDOM*RANDOM+s))" \
      --nnue "$W/pilot.pjtw" --random-open-plies "$OPEN" $sa >"$W/gen-$tag.$s.log" 2>&1 & done; wait
  merge "$W/$tag.jnnw"; }

"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8014 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }

conv_ci(){ python3 - "$1" "$DILF" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=[]
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    aw.append(0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0))
n=len(aw)
if not n: print("NA NA NA 0"); sys.exit(0)
m=sum(aw)/n; seed=12345; boots=[]
for _ in range(2000):
    acc=0
    for _ in range(n):
        seed=(1103515245*seed+12345)&0x7fffffff; acc+=aw[seed%n]
    boots.append(acc/n)
boots.sort(); print(f"{m:.3f} {boots[50]:.3f} {boots[1949]:.3f} {n}")
PY
}
fitjudge(){ local tag="$1"   # corpus = gen($tag) + egdb ; fit ; juge 0440
  cp "$W/$tag.jnnw" "$W/corpus-$tag.jnnw"; app "$W/egdb.jnnw" "$W/corpus-$tag.jnnw" >/dev/null
  local NT=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus-$tag.jnnw','rb').read(8)[4:8])[0])")
  say "  [$tag] corpus = ${NT}"
  "$J" --dump-eval-features "$W/corpus-$tag.jnnw" "$W/feat-$tag" >"$W/feat-$tag.log" 2>&1 || { say "ABORT dump feat $tag"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus-$tag.jnnw" --feat "$W/feat-$tag" \
      --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ-$tag.pjtw" >"$W/fit-$tag.log" 2>&1 || { say "TRAIN FAIL $tag"; tail -6 "$W/fit-$tag.log"|sed 's/^/  /'; return 1; }
  rm -f "$W/feat-$tag" "$W/corpus-$tag.jnnw"; gzip -c "$W/champ-$tag.pjtw" > "$ART/champion-$tag.pjtw.gz"
  if [ "$HAVE_SCAN" = 1 ]; then
    ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ-$tag.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-$tag" >"$W/cv-$tag.log" 2>&1 ) || say "  (juge $tag echoue)"
    read M LO HI N < <(conv_ci "$ART/conv-$tag")
    say "  [$tag] 0440 = $M  IC95=[$LO,$HI]  (n=$N)"
    echo "$tag $M $LO $HI $N" >> "$ART/SUMMARY.txt"
  fi
}

say ""; say "=== ARM A : self-play ELAGAGE ON (baseline) — pilote egdbmix, play d${PLAYDEPTH}, ${NGEN} pos ==="
gen_arm on ""; fitjudge on
say ""; say "=== ARM B : self-play ELAGAGE OFF (full-width) — meme tout, SEULE difference = elagage OFF ==="
gen_arm off "$OFF"; fitjudge off

say ""; say "================= VERDICT (A/B elagage au gen) ================="
cat "$ART/SUMMARY.txt" 2>/dev/null | sed 's/^/  /' | tee -a "$RES"
say "  rappel egdbmix=0.302 [0.25,0.35] ; seuil compte >0.35"
say "  OFF >> ON (et > 0.35) => l'elagage AVEUGLAIT nos labels (shots non joues au gen) => recette Scan tenue => scaler+bootstrap."
say "  OFF ~ ON            => l'elagage n'etait pas le coupable des labels => creuser (profondeur de gen, volume, from-scratch)."
