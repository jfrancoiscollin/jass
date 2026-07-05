#!/usr/bin/env bash
# id: cpx62-0581-labelhyg-validate
# description: MINI-VALIDATION §7.5 (JFC) — l'hygiene de label WDL paie-t-elle ? Gen ANCIEN pipeline (explore-eps 5, sans
# fixes) vs NOUVEAU (FIX#1 decay+drop, FIX#2 adjud, FIX#3 pair) a volume egal, fit chacun (prior gen1), MATCH head-to-head
# eval-nouveau vs eval-ancien (d9 dilf) + holdout log-loss. Gate : eval-nouveau >= eval-ancien => les labels propres
# produisent un meilleur eval => on integre les fixes au gen et on va vers E2. Code depuis DEVELOP (overlay main.cpp +
# train_stream sur l'arbre main). AUCUN NNUE, AUCUNE distillation. FIX#4 (tb) hors-scope (pas d'egdb ici).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0581-labelhyg-validate/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0581-labelhyg-validate/artefacts"
W=/root/cw-lhval; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-lhval
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
VOL=300000; LABEL_DEPTH=4; PD=6; MAXPLIES=200; FORCE="ext_forcing=1,forcing_ext_cap=6"
L2=3e-5; MAXIT=25; CHUNK=1000000; PRIOR_VISIT=0.25; JUDGE_DEPTH=9; JUDGE_PAIRS=3
VERD="$ART/VERDICT.txt"; : > "$VERD"; say(){ echo "$@" | tee -a "$VERD"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_into(){ python3 - "$@" <<'PY'
import struct,glob,sys
out=sys.argv[1]; body=b""; tot=0
for p in sys.argv[2:]:
    for f in sorted(glob.glob(p)):
        try: b=open(f,'rb').read()
        except: continue
        if len(b)<8 or b[:4]!=b'JNNW': continue
        n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}

say "=== MINI-VALIDATION label-hygiene — overlay code develop ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
grep -q 'explore-decay-plies\|adjud-material' src/main.cpp || { say "ABORT: fixes absents (develop pas overlay)"; exit 5; }
say "  develop : $(git show origin/develop --oneline -1|cat)"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT NP=$NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
python3 -c "import struct;r=bytearray(open('$W/gen1.pjtw','rb').read());struct.pack_into('<I',r,4,3);open('$W/gen1_prior.pjtw','wb').write(r)"
git checkout -- src/main.cpp pattern_jass/tools/train_stream.py 2>/dev/null || true   # restaure l'arbre (overlay non committe)

gen_pipeline(){ local tag="$1"; shift; local extra="$*"; local per=$(( (VOL+NCPU-1)/NCPU ))
  say ""; say "=== GEN $tag : ${VOL} pos @ pd${PD} ($extra) ==="
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/${tag}.$s.jnnw" "$LABEL_DEPTH" "$PD" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE" --quiet-only --explore-eps 5 --random-open-plies 8 $extra \
      >"$W/gen_${tag}_$s.log" 2>&1 & done; wait
  local N; N=$(merge_into "$W/${tag}.jnnw" "$W/${tag}.*.jnnw"); rm -f "$W/${tag}."[0-9]*.jnnw
  say "  $tag : $N pos ; $(grep -h LABELHYG "$W/gen_${tag}_1.log" | head -1)"
}
gen_pipeline old ""
gen_pipeline new "--explore-decay-plies 20 --drop-post-eps --adjud-material 3 --adjud-hold-plies 10 --pair-openings"

fit(){ local data="$1" out="$2"
  "$J" --dump-eval-features "$data" "$W/feat" >"$W/feat.log" 2>&1 || { say "dump FAIL $data"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prior-mean "$W/gen1_prior.pjtw" --prior-visit-scale "$PRIOR_VISIT" --prior-decay 1.0 --prune-min-visits 1 \
    --out "$out" >"${out%.pjtw}.log" 2>&1 || { say "TRAIN FAIL : $(tail -2 "${out%.pjtw}.log"|tr '\n' ' ')"; return 1; }
  rm -f "$W/feat"; }
say ""; say "=== FITS (prior gen1 lambda=$PRIOR_VISIT) ==="
fit "$W/old.jnnw" "$W/eval_old.pjtw" && say "  eval_old fitte" || exit 9
fit "$W/new.jnnw" "$W/eval_new.pjtw" && say "  eval_new fitte" || exit 9

say ""; say "=== MATCH head-to-head : eval_NEW vs eval_OLD (d${JUDGE_DEPTH} dilf) ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/eval_new.pjtw" \
  --jass-b "$J" --pattern-b "$W/eval_old.pjtw" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 \
  --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" >"$W/j.$s" 2>&1 & done; wait
python3 - "$W"/j.* <<'PY' 2>&1 | tee -a "$VERD"
import sys,math; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
verd="NOUVEAU > ANCIEN hors-IC : l'hygiene de label PAIE => integrer les fixes au gen, GO E2" if lo>0.5 else ("NOUVEAU < ANCIEN : l'hygiene degrade (a investiguer)" if hi<0.5 else "PARITE : l'hygiene n'a pas d'effet net mesurable a ce volume")
print(f"  [new-vs-old] games={g} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  IC=[{lo:.4f},{hi:.4f}]")
print(f"  => {verd}")
PY
say "=== fin mini-validation ==="
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0581 mini-validation label-hygiene : VERDICT job-side (eval-nouveau vs eval-ancien)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
