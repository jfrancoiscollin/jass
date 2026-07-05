#!/usr/bin/env bash
# id: cpx62-0587-fix4-egdb-iso
# description: A3 (mémo JFC) — ISOLATION des fixes "innocents" motivée par P2 (labels PIRE en finale, 31% desaccord).
# EGDB dispo sur box => on teste enfin les leviers ENDGAME. Build UNIQUE avec -DJASS_EGDB=ON ; egdb toggle par env
# (JASS_EGDB_PATH set/unset) => meme binaire, isolation propre. 3 bras iso-volume (from-scratch, match vs baseline) :
#   A baseline : egdb OFF (= tous les gens de la campagne, pas de TB)
#   B +TB      : egdb ON (TB-terminate s'active) + --tb-relabel (labels TB EXACTS par-sample, biais 0 en finale)
#   C +adjud   : --adjud-material 3 (adjudication materielle des fausses nulles, sans egdb)
# Gate : B ou C >= A hors-IC => garder ce fix comme hygiene GRATUITE (cible le vrai biais finale que P2 a chiffre).
# VERIF que FIX#4 agit : LABELHYG doit montrer tb_relabel>0 (sinon egdb pas trouve). Code depuis DEVELOP. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0587-fix4-egdb-iso/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0587-fix4-egdb-iso/artefacts"
W=/root/cw-fix4; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-fix4
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
VOL=500000; LABEL_DEPTH=4; PD=6; MAXPLIES=200; FORCE="ext_forcing=1,forcing_ext_cap=6"
L2=3e-5; MAXIT=25; CHUNK=1000000; JUDGE_DEPTH=9; JUDGE_PAIRS=4
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

say "=== A3 isolation FIX#4(TB)/FIX#2(adjud) — build EGDB, code develop ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build non actif"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git checkout -- src/main.cpp 2>/dev/null || true
EGDBP=""; [ -d /root/egdb_extracted ] && EGDBP=/root/egdb_extracted
say "  egdb data : ${EGDBP:-INTROUVABLE (/root/egdb_extracted)} ; NUM_PATTERNS=$NP"

gen_arm(){ local tag="$1" use_egdb="$2"; shift 2; local extra="$*"; local per=$(( (VOL+NCPU-1)/NCPU ))
  say ""; say "=== GEN $tag : ${VOL} (egdb=$use_egdb $extra) ==="
  local ENV=""; [ "$use_egdb" = 1 ] && [ -n "$EGDBP" ] && ENV="JASS_EGDB_PATH=$EGDBP"
  for s in $(seq 1 "$NCPU"); do env $ENV "$J" --gen-data-wdl "$per" "$W/${tag}.$s.jnnw" "$LABEL_DEPTH" "$PD" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE" --quiet-only --explore-eps 5 --random-open-plies 8 $extra \
      >"$W/g_${tag}_$s.log" 2>&1 & done; wait
  local N; N=$(merge_into "$W/${tag}.jnnw" "$W/${tag}.*.jnnw"); rm -f "$W/${tag}."[0-9]*.jnnw
  say "  $tag : $N pos ; $(grep -h LABELHYG "$W/g_${tag}_1.log"|head -1)"
}
gen_arm A 0 ""
gen_arm B 1 "--tb-relabel"
gen_arm C 0 "--adjud-material 3 --adjud-hold-plies 10"

fit_fs(){ local data="$1" out="$2"
  "$J" --dump-eval-features "$data" "$W/feat" >"$W/f.log" 2>&1 || return 1
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --prune-min-visits 1 \
    --out "$out" >"${out%.pjtw}.log" 2>&1 || { say "TRAIN FAIL $(tail -2 "${out%.pjtw}.log"|tr '\n' ' ')"; return 1; }
  rm -f "$W/feat"; }
say ""; say "=== FITS from-scratch ==="
fit_fs "$W/A.jnnw" "$W/evA.pjtw" && say "  A OK" || exit 9
fit_fs "$W/B.jnnw" "$W/evB.pjtw" && say "  B OK" || exit 9
fit_fs "$W/C.jnnw" "$W/evC.pjtw" && say "  C OK" || exit 9

match(){ local na="$1" nb="$2" tag="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$na" \
    --jass-b "$J" --pattern-b "$nb" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" \
    --quiet --openings-file "$DILF" >"$W/j_${tag}.$s" 2>&1 & done; wait
  python3 - "$tag" "$W"/j_${tag}.* <<'PY' 2>&1 | tee -a "$VERD"
import sys,math; tag=sys.argv[1]; a=d=b=0
for f in sys.argv[2:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="AIDE hors-IC (garder)" if lo>0.5 else ("NUIT hors-IC" if hi<0.5 else "parite (pas d'effet net)")
print(f"  [{tag}] games={g} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  => {vd}")
PY
}
say ""; say "=== MATCHS vs baseline A (d${JUDGE_DEPTH} dilf) ==="
match "$W/evB.pjtw" "$W/evA.pjtw" "B(+TB)-vs-A"
match "$W/evC.pjtw" "$W/evA.pjtw" "C(+adjud)-vs-A"
say ""; say "  => B ou C > 0.5 hors-IC => fix cible le VRAI biais finale (P2 31%) => hygiene gratuite a garder."
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0587 isolation FIX#4(TB)/FIX#2(adjud) vs baseline (levier finale motive par P2)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
say "=== fin isolation fix4/fix2 ==="
