#!/usr/bin/env bash
# id: cpx62-0696-b1-seed-ab
# description: B1 ETAPE-0 (mémo BOOST gen2-mmto, go JFC "A et A" 2026-07-13). SCREEN d'ENSEMENCEMENT : le trou 0688
# (conversion jass 0.136 vs Scan 0.904 sur 224 combos réelles) ne se comble PAS en IMPOSANT les coups humains à l'éval
# (0691 prefs = -135) ; la voie conforme = les faire VIVRE au pilote (self-play démarré SUR les graines -> labels = issue
# de jeu = le canal qui a toujours payé, 0464). A/B à VARIABLE UNIQUE : les 2 bras utilisent le MEME outil éprouvé
# (scan_selfplay_gen pilote=gen2-mmto self-asym d8/d3 -> WDL game-outcome) + MEME fit (wdl_finetune ancré gen2-mmto
# anchor=0.05) ; SEULE différence = le POOL de graines : bras A = base standard (corpus-mix2M >=32p) ; bras B = base +
# 25% de combos pcblues (16 160, réplique seed_frac=0.25). Juge : compose A/B généraliste mt0.2+0.3 (candB vs candA
# décisif + candB vs gen2-mmto ancre) + thermomètre-224 sur candB (baseline gen2-mmto 0.136, si Scan présent, sinon
# candB.pjtw émis pour thermo ccx33). GATE étape-0 : candB > candA hors-IC => l'ensemencement AJOUTE => scale (B1
# step-2, job séparé, gen 1-3M + finetune, sur go JFC). Dubois (789) omis (pcblues 16 160 suffit au screen). AUCUN NNUE
# (adaptateur linéaire, jamais refit-zéro). Progress + artefacts committés au fil de l'eau (règle 2).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0696-b1-seed-ab/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0696-b1-seed-ab/artefacts"
W=/root/cw-b1seedab; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-b1seedab
# RES dans $W (HORS arbre git) : le runner reset --hard /tick clobbe $ART mid-run (bug 8ter)
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SCAN_BIN=/root/jass-scan/scan_linux
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# gen : self-asym d8/d3 (ancre 0650). WDL cible ~1M/bras.
PERG=1050; MAXPLIES=160; MINPIECES=1; STRONG_D=8; WEAK_D=3; JITTER=1; SKIP=8; DRAWFRAC=0.2; SEED=50694
BASE_N=100000; SEED_FRAC_PCT=25      # base standard pré-échant. (assez grande pour diluer les 2×16160 combos à 25%)
ANCHOR=0.05; CHUNK=1000000; MAXIT=25 # fit wdl_finetune ancré gen2-mmto
NOPEN=96; PAIRS=8                     # A/B compose (ancre 0641)
THERMO_D=11; THERMO_PAIRS=1; GEN2_THERMO=0.136

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import struct,glob,sys,re
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
}
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== B1 étape-0 ensemencement — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
# CONSISTANCE SRC (fix 0696 BUILD FAIL) : pull TOUS les fichiers src qui DIVERGENT
# main<->develop, sinon develop main.cpp compile contre des headers base perimes
# (ex. compact_scan_weights declaree seulement dans develop scan_eval.hpp) => BUILD FAIL.
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
say "  src divergents pull develop : $(echo $DIVERGED | tr '\n' ' ')"
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
restore_src(){ git checkout -- src pattern_jass/src tools/scan_selfplay_gen.py tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py pattern_jass/tools/train_stream.py pattern_jass/tools/wdl_finetune.py 2>/dev/null||true; }
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS g_emasks"; restore_src; exit 5; }
  grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
  grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
  say "  garde-fou archi OK (g_emasks + has_any_capture)"; }
arch_assert
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/std.jnnw"  || { say "ABORT seeds std"; restore_src; exit 4; }
git show "origin/main:data/pcblues_combos.fen" > "$W/combos.fen" || { say "ABORT combos"; restore_src; exit 4; }
say "  ✓ build+geom(NP=$NP)+gen2 ; std seeds=$(jnnw_count "$W/std.jnnw") ; combos=$(grep -cvE '^\s*(#|$)' "$W/combos.fen")"

# ---- pools de graines : base standard (>=32p, sous-échant.) ; poolA=base ; poolB=base+25% combos ----
python3 - "$W/std.jnnw" "$W/combos.fen" "$W/poolA.jnnw" "$W/poolB.jnnw" "$BASE_N" "$SEED_FRAC_PCT" <<'PY' | tee -a "$RES"
import struct,sys,random,re
REC=38
std,cfen,pA,pB,base_n,fracpct=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]),int(sys.argv[6])
def pc(x):
    c=0
    while x: x&=x-1; c+=1
    return c
def mirror(bb):
    o=0
    for s in range(1,51):
        if (bb>>(s-1))&1: o|=1<<(50-s)
    return o
# base : sous-échantillon des seeds standard filtrés >=32 pièces (recette gen2 lineage)
b=open(std,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
rng=random.Random(694); base=[]
idx=list(range(n)); rng.shuffle(idx)
for i in idx:
    r=body[i*REC:(i+1)*REC]
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    if pc(wm)+pc(wk)+pc(bm)+pc(bk)>=32: base.append(r)
    if len(base)>=base_n: break
# combos pcblues .fen -> records (score=0,wdl=0) + paires couleurs-échangées
def parse(fen):
    fen=fen.split('#',1)[0].strip()
    if not fen: return None
    turn,rest=fen.split(':',1); stm=1 if turn.strip().upper().startswith('B') else 0
    wm=wk=bm=bk=0
    for part in rest.split(':'):
        part=part.strip()
        if not part: continue
        side=part[0].upper(); items=part[1:]
        for tok in items.split(','):
            tok=tok.strip()
            if not tok: continue
            king=tok[0].upper()=='K'; s=int(tok[1:] if king else tok)
            bit=1<<(s-1)
            if side=='W': (wk:=wk|bit) if king else (wm:=wm|bit)  # noqa
            else: (bk:=bk|bit) if king else (bm:=bm|bit)          # noqa
    return wm,wk,bm,bk,stm
def rec(wm,wk,bm,bk,stm):
    return struct.pack('<QQQQ',wm,wk,bm,bk)+struct.pack('<B',stm)+struct.pack('<i',0)+struct.pack('<b',0)
combos=[]
for ln in open(cfen,encoding='utf-8',errors='replace'):
    p=parse(ln)
    if not p: continue
    wm,wk,bm,bk,stm=p
    if pc(wm)+pc(wk)+pc(bm)+pc(bk)<4: continue
    combos.append(rec(wm,wk,bm,bk,stm))
    combos.append(rec(mirror(bm),mirror(bk),mirror(wm),mirror(wk),1-stm))  # couleur-échangée
def write(path,recs):
    open(path,'wb').write(b'JNNW'+struct.pack('<I',len(recs))+b''.join(recs))
# poolA = base ; poolB = base + combos (dimensionné pour ~fracpct% de combos)
write(pA,base)
# nb de base à garder dans B pour que combos = fracpct% : combos/(base_keep+combos)=frac -> base_keep=combos*(100-frac)/frac
keepB=min(len(base), int(len(combos)*(100-fracpct)/max(fracpct,1)))
poolB=base[:keepB]+combos; rng.shuffle(poolB)
write(pB,poolB)
print(f"  poolA base={len(base)}  poolB base_keep={keepB}+combos={len(combos)} (combos={100*len(combos)/max(len(poolB),1):.1f}% du pool B)")
PY
[ -s "$W/poolA.jnnw" ] && [ -s "$W/poolB.jnnw" ] || { say "ABORT pools vides"; restore_src; exit 7; }

# ---- gen self-asym par bras (WDL game-outcome) ----
gen_arm(){ local arm="$1" pool="$2" outmerged="$3"; local GT0=$SECONDS; local pids=()
  say ""; say "=== [$arm] gen self-asym : ${PERG}×${NCPU} parties (pool=$(jnnw_count "$pool")) ==="
  for s in $(seq 0 $((NCPU-1))); do
    python3 tools/scan_selfplay_gen.py --jass "$J" --player-jass-bin "$J" --player-pattern "$W/gen2.pjtw" \
      --seeds "$pool" --out "$W/sp_${arm}.$s" --games "$PERG" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" \
      --sample-every 1 --depth "$STRONG_D" --weak-depth "$WEAK_D" --depth-jitter "$JITTER" \
      --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
      --seed "$SEED" --nshards "$NCPU" --shard "$s" >"$W/sp_${arm}-$s.log" 2>&1 &
    pids+=($!)
  done
  wait "${pids[@]}"
  local nw; nw=$(merge_jnnw "$outmerged" "$W/sp_${arm}"); say "  [$arm] WDL positions = $nw ($((SECONDS-GT0))s)"
  echo "$nw"
}
NW_A=$(gen_arm A "$W/poolA.jnnw" "$W/wdlA.jnnw" | tail -1)
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 gen bras A fini" >/dev/null 2>&1 || true
NW_B=$(gen_arm B "$W/poolB.jnnw" "$W/wdlB.jnnw" | tail -1)
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 gen bras B fini" >/dev/null 2>&1 || true

# ---- fit wdl_finetune ancré gen2-mmto par bras ----
fit_arm(){ local arm="$1" wdl="$2" out="$3"
  say ""; say "=== [$arm] fit wdl_finetune ancré gen2-mmto anchor=$ANCHOR ==="
  "$J" --dump-eval-features "$wdl" "$W/feat_$arm" >"$W/feat_$arm.log" 2>&1 || { say "  [$arm] DUMP FAIL"; tail -4 "$W/feat_$arm.log"|sed 's/^/    /'; return 1; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
      --champion "$W/gen2.pjtw" --data "$wdl" --feat "$W/feat_$arm" --out "$out" \
      --tools pattern_jass/tools --anchor "$ANCHOR" --logit-scale 1.0 --chunk "$CHUNK" --max-iter "$MAXIT" \
      --full-fold --tempo-stage --verify-jass "$J" --verify-n 60 >"$W/fit_$arm.log" 2>&1
  if [ $? = 0 ] && [ -s "$out" ]; then
    say "  [$arm] $(grep -iE 'fit : logloss|mean|verify' "$W/fit_$arm.log" | tr '\n' ' ')"
    gzip -c "$out" > "$ART/cand_$arm.pjtw.gz"; commit_to_main "$ART/cand_$arm.pjtw.gz" "$ARTREL/cand_$arm.pjtw.gz" "0696 candidat $arm" >/dev/null 2>&1 || true
  else say "  [$arm] FIT FAIL : $(tail -4 "$W/fit_$arm.log"|tr '\n' ' ')"; return 1; fi
}
fit_arm A "$W/wdlA.jnnw" "$W/candA.pjtw" || { say "ABORT fit A"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 ABORT fit A"; exit 8; }
fit_arm B "$W/wdlB.jnnw" "$W/candB.pjtw" || { say "ABORT fit B"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 ABORT fit B"; exit 8; }
restore_src

# ---- openings généralistes (≥38p) depuis corpus-mix2M (ancre 0641) ----
python3 - "$W/std.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def fen(wm,wk,bm,bk,stm):
    Wl=[str(s) for s in range(1,51) if (wm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (wk>>(s-1))&1]
    Bl=[str(s) for s in range(1,51) if (bm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (bk>>(s-1))&1]
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
out=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    if bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  généraliste : {len(out)} openings")
PY
NG=$(grep -c . "$W/gen.fen"); [ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings vides"; exit 7; }

# ---- A/B compose (cellule ancre 0641) ----
abcell(){ local pa="$1" pb="$2" tag="$3" mt="$4"; local pref="$W/x_${tag}_${mt}"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$pa" --jass-b "$J" --pattern-b "$pb" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$tag" "$mt" "$W/.cellout" "${pref}".* <<'PY'
import sys,math
tag,mt,outp=sys.argv[1],sys.argv[2],sys.argv[3]; a=d=b=0
for f in sys.argv[4:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="A GAGNE hors-IC" if lo>0.5 else ("A PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [{tag} | mt{mt}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"; rm -f "${pref}".* ; }
say ""; say "=== A/B compose (généraliste) : candB vs candA [décisif] + candB vs gen2-mmto [ancre] ==="
abcell "$W/candB.pjtw" "$W/candA.pjtw" "candB_vs_candA" 0.2
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 A/B candB-vs-candA mt0.2" >/dev/null 2>&1 || true
abcell "$W/candB.pjtw" "$W/candA.pjtw" "candB_vs_candA" 0.3
abcell "$W/candB.pjtw" "$W/gen2.pjtw"  "candB_vs_gen2"  0.2
say ""; say "  GATE étape-0 : candB>candA hors-IC => l'ensemencement (25% combos pcblues) AJOUTE => scale B1 step-2 (go JFC)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 A/B compose ensemencement" >/dev/null 2>&1 || true

# ---- thermomètre-224 sur candB (recette 0688 exacte ; guardé Scan) ----
say ""; say "=== thermomètre-224 candB (baseline gen2-mmto au trait=$GEN2_THERMO) ==="
if [ -x "$SCAN_BIN" ]; then
  git show "origin/$SRC_BRANCH:data/pcblues_thermometre.fen" > "$W/thermo.fen" 2>/dev/null || git show "origin/main:data/pcblues_thermometre.fen" > "$W/thermo.fen" 2>/dev/null
  NPOS=$(grep -cvE '^\s*(#|$)' "$W/thermo.fen" 2>/dev/null || echo 0)
  if [ "${NPOS:-0}" -ge 100 ]; then
    unset JASS_EGDB_PATH; mkdir -p "$ART/games"
    timeout 14400 python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/candB.pjtw" \
      --scan-bb-size 0 --depth "$THERMO_D" --pairs "$THERMO_PAIRS" --openings-file "$W/thermo.fen" \
      --dump-games-dir "$ART/games" >"$W/thermo.log" 2>&1 || say "  (thermo interrompu/timeout — on analyse ce qui est dumpé)"
    python3 - "$ART/games" "$W/thermo.fen" "$GEN2_THERMO" <<'PY' | tee -a "$RES" || true
import json,glob,sys,os
gdir,fens,base=sys.argv[1],sys.argv[2],float(sys.argv[3])
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm[b]=b.split(':',1)[0].strip()
ja_w=ja_n=0; sc_w=sc_n=0; tot=0; nolegal=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except Exception: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    tot+=1
    jw=g.get("jass_is_white"); out=g.get("outcome")
    if g.get("reason","")=="no-legal-move" and g.get("plies",1)<=1: nolegal+=1
    jass_is_attacker=(jw and s=="W") or ((not jw) and s=="B")
    if out=="D": att=0.5
    elif (out=="W" and s=="W") or (out=="L" and s=="B"): att=1.0
    else: att=0.0
    if jass_is_attacker: ja_w+=att; ja_n+=1
    else: sc_w+=att; sc_n+=1
def pct(w,n): return f"{w/n:.3f} ({w:.1f}/{n})" if n else "n/a"
print(f"  parties analysées : {tot} (sans coup légal au départ : {nolegal})")
print(f"  candB au trait (convertit) : {pct(ja_w,ja_n)}  | baseline gen2-mmto={base:.3f}")
print(f"  SCAN au trait (convertit)  : {pct(sc_w,sc_n)}")
if ja_n:
    d=ja_w/ja_n-base
    print(f"  DELTA candB - gen2-mmto (au trait) : {d:+.3f}  => {'candB CONVERTIT MIEUX (le trou 0688 bouge)' if d>0.02 else ('parité' if abs(d)<=0.02 else 'candB convertit MOINS')}")
PY
  else say "  (thermomètre absent/insuffisant — candB.pjtw émis, thermo à passer sur ccx33)"; fi
else
  say "  (Scan absent sur cette box — candA/candB.pjtw émis en artefacts ; thermo-224 à queuer sur ccx33, pattern 0688)"
fi

commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0696 B1 étape-0 ensemencement : gen+fit+A/B (+thermo candB) — verdict compose" \
  && say "  ✓ RESULTS committé" || say "  ⚠ commit RESULTS échoué"
say "=== 0696 B1 étape-0 FINI ==="
