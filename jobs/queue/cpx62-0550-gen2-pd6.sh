#!/usr/bin/env bash
# id: cpx62-0550-gen2-pd6
# description: GEN2 — chaîne self-play (JFC promeut gen1 +14). Pilote + PRIOR = gen1 (le nouveau champion). PLAY_DEPTH
# BAISSÉ 10->6 (calibration : pd10 = 19h/3M sur box, intenable ; pd6 ~10x plus rapide, ~2h/3M). Recette conservée :
# asym punisher ext_forcing, quiet-only, combo-seed, enrichissement combos.jnnw, prior séquentiel (bit self-desc strippé).
# Fixes : (a) moniteur de volume SANS le bug 'wait' (on n'attend QUE les pids de gen) ; (b) CHECKPOINT incrémental
# (corpus partiel gzippé toutes ~8min -> récupérable si kill). Juge gen2 vs gen1 (la chaîne progresse-t-elle ?) ET vs
# egdbmix (Elo cumulé). Si gen2 > gen1 -> le pas gen1 était réel (ça compose). AUCUN NNUE. 100% linéaire. ~2-4 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0550-gen2-pd6/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-gen2; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-gen2
FRESH=3000000; PLAY_DEPTH=6; LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"; SEED_FRAC=25
CHUNK=1000000; MAXIT=25; L2=3e-5; PRIOR_VISIT=0.25; PRIOR_DECAY=1.0
JUDGE_PAIRS=4; JUDGE_DEPTH=9
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
EGDBMIX_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
COMBO_ENRICH_SRC=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"

say "=== build jass depuis main (qs_sacs baké, 32-pat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: $NP patterns != 32"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1 absent"; exit 4; }
PILOT="$W/gen1.pjtw"
python3 -c "import struct; r=bytearray(open('$PILOT','rb').read()); struct.pack_into('<I',r,4,3); open('$W/gen1_prior.pjtw','wb').write(r)" || { say "ABORT strip prior"; exit 4; }
PRIOR="$W/gen1_prior.pjtw"
git show "origin/main:$EGDBMIX_GZ" | gunzip > "$W/egdbmix.pjtw" 2>/dev/null || : > "$W/egdbmix.pjtw"
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  pilote+prior = gen1 (nouveau champion) ; play_depth=$PLAY_DEPTH (baissé de 10)"

# ---------- primitives ----------
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
concat(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,sys
out=sys.argv[1]; ins=sys.argv[2:]; REC=38; body=b""; tot=0; parts=[]
for f in ins:
    try: b=open(f,'rb').read()
    except Exception: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n; parts.append((f.split('/')[-1],n))
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
print("  concat -> "+str(tot)+" : "+", ".join(f"{k}={v}" for k,v in parts))
PY
}
# compte positions courant depuis la taille des shards (streaming)
count_pos(){ python3 -c "import glob,os
t=0
for f in glob.glob('$1.*'):
    try: t+=max(0,(os.path.getsize(f)-8)//38)
    except: pass
print(t)" 2>/dev/null || echo 0; }
# checkpoint : merge partiel des shards -> gzip dans ART (récupérable si kill)
checkpoint(){ python3 - "$1" "$ART/corpus-gen2-partial.jnnw" <<'PY' 2>/dev/null
import glob,struct,sys,re
pre,out=sys.argv[1],sys.argv[2]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(pre+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1)) if re.search(r"\.(\d+)$",p) else 0):
    try: b=open(f,'rb').read()
    except Exception: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
PY
gzip -f "$ART/corpus-gen2-partial.jnnw" 2>/dev/null || true; }
# gen + moniteur/checkpoint SANS bug wait (on n'attend QUE les pids de gen)
gen_strong(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn+NCPU-1)/NCPU )); local pids=()
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$pilot" --asym-punisher-params "$FORCE_SPEC" --quiet-only \
      --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
      >/dev/null 2>&1 & pids+=($!); done
  ( T0=$SECONDS; while kill -0 "${pids[0]}" 2>/dev/null; do
      P=$(count_pos "$out"); DT=$((SECONDS-T0)); R=$(( P/(DT>0?DT:1) ))
      echo "$(date -u +%H:%M:%SZ) positions~${P}/${nn} debit~${R}/s" >> "$ART/progress.txt"
      checkpoint "$out"
      sleep 480
    done ) & local MON=$!
  wait "${pids[@]}"; kill "$MON" 2>/dev/null || true; wait "$MON" 2>/dev/null || true
  merge "$out"; }
fit(){ env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$1" --feat "$2" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prior-mean "$PRIOR" --prior-visit-scale "$PRIOR_VISIT" --prior-decay "$PRIOR_DECAY" --out "$3" \
    >"${3%.pjtw}.log" 2>&1 || { say "TRAIN FAIL $3"; tail -14 "${3%.pjtw}.log"|sed 's/^/  /'; exit 9; }; }
pjudge(){ local newp="$1" refp="$2" tag="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$newp" \
    --jass-b "$J" --pattern-b "$refp" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" \
    --quiet --openings-file "$DILF" >"$W/j.$s" 2>&1 & done; wait
  python3 - "$tag" "$W"/j.* <<'PY'
import sys,math; tag=sys.argv[1]; a=d=b=0
for f in sys.argv[2:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0
# SE ajustée aux nulles
import math
ex2=(a+0.25*d)/g if g else 0; var=ex2-r*r; se=math.sqrt(var/g) if g and var>0 else 0.5/(g**0.5 if g else 1)
elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"  [{tag}] games={g} A(new)={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}")
PY
  rm -f "$W"/j.* ; }

# ---------- seed-file + combo enrich ----------
say ""; say "=== seed-file (dilf + lidraughts) ==="
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
python3 - "$W" "$DILF" 14 40 300000 $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
REC=38; W=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xBEEF); drecs=bytearray(); nd=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b); drecs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); nd+=1
mids=[]
for sh in shards:
    try: raw=gzip.open(sh,'rb').read()
    except Exception: continue
    if raw[:4]!=b'JNNW': continue
    m=struct.unpack('<I',raw[4:8])[0]; body=memoryview(raw)[8:8+m*REC]
    for i in range(m):
        r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
        pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        if lo<=pc<=hi: mids.append(bytes(r))
random.shuffle(mids); mids=mids[:cap]
open(f"{W}/seeds.jnnw",'wb').write(b'JNNW'+struct.pack('<I',nd+len(mids))+bytes(drecs)+b"".join(mids))
print(f"  seed-file : dilf={nd} lidraughts={len(mids)}")
PY
SEEDFILE="$W/seeds.jnnw"; [ -s "$SEEDFILE" ] || { say "ABORT seed vide"; exit 7; }
git show "origin/main:$COMBO_ENRICH_SRC" > "$W/combos.jnnw" 2>/dev/null && [ -s "$W/combos.jnnw" ] \
  && say "  combo-enrich : $(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) pos" || { : > "$W/combos.jnnw"; say "  (combos absent)"; }

# ---------- GEN2 (pilote gen1, pd6) ----------
say ""; say "================= GEN2 (pilote=gen1, play_depth $PLAY_DEPTH, asym) ================="
gen_strong "$PILOT" "$FRESH" "$W/selfplay.jnnw"
NSP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/selfplay.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  self-play : ${NSP} pos"
[ "${NSP:-0}" -ge 500000 ] || { say "ABORT corpus trop petit ($NSP)"; exit 7; }
rm -f "$ART/corpus-gen2-partial.jnnw.gz"   # partiel plus utile (gen fini)

concat "$W/corpus.jnnw" "$W/selfplay.jnnw" "$W/combos.jnnw" | tee -a "$RES"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
say ""; say "=== fit train_stream (PRIOR = gen1, visit=$PRIOR_VISIT) ==="
fit "$W/corpus.jnnw" "$W/feat" "$W/gen2.pjtw"; rm -f "$W/feat"
grep -iE 'prior|iter|loss' "$W/gen2.log" | tail -5 | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/gen2.pjtw" > "$ART/champion-gen2.pjtw.gz"; say "  champion-gen2 committé"

# ---------- JUGE : chaîne (vs gen1) + cumulé (vs egdbmix) ----------
say ""; say "=== JUGE gen2 @ d$JUDGE_DEPTH, dilf x${JUDGE_PAIRS}pair ==="
pjudge "$W/gen2.pjtw" "$PILOT" "gen2-vs-gen1" | tee -a "$RES"
[ -s "$W/egdbmix.pjtw" ] && pjudge "$W/gen2.pjtw" "$W/egdbmix.pjtw" "gen2-vs-egdbmix" | tee -a "$RES"
say ""
say "  => gen2-vs-gen1 >0.5 hors-IC = la chaîne PROGRESSE (gen1 était réel, ça compose) => promouvoir gen2, gen3."
say "=== fin gen2 ==="
