#!/usr/bin/env bash
# id: cpx62-0558-fit-matin-mix2M
# description: FIT MATIN (JFC) — fit prior gen1 sur le corpus NUIT mix2M (2M : 60/20/20 pd8/9/10, archi COMPLETE) +
# supplement pd10 0557 (~300k) + combos (~1.24M) = ~3.5M. JUGE en config ERE-GEN1 : qs_threat_ext=0 FORCE des DEUX
# cotes (F2 baké ON changerait la recherche du juge => incomparable avec gen1 +14 / gen2 -5 ; F1 no-op au defaut,
# F5 node-identical => comparabilite EXACTE). Juge vs gen1 (gate COMPOSE) + vs egdbmix (cumule). Champion job-side.
# C'est le test decisif : la donnee complete-archi + mix-profondeur compose-t-elle enfin sur gen1 ? AUCUN NNUE. ~1h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0558-fit-matin-mix2M/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-fitmatin; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-fitmatin
CHUNK=1000000; MAXIT=25; L2=3e-5; PRIOR_VISIT=0.25; PRIOR_DECAY=1.0; JUDGE_PAIRS=4; JUDGE_DEPTH=9
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
EGDBMIX_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MIX_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SUPP_GZ=jobs/results/ccx33-0557-gen-pd10-supp/artefacts/phase-pd10supp.jnnw.gz
COMBO_SRC=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw
DILF=data/dilf_combinations.fen
ARTREL="jobs/results/cpx62-0558-fit-matin-mix2M/artefacts"

say "=== build jass depuis main (archi complete : qs_sacs + threat_ext + F1 + F5) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT $NP!=32"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
python3 -c "import struct; r=bytearray(open('$W/gen1.pjtw','rb').read()); struct.pack_into('<I',r,4,3); open('$W/gen1_prior.pjtw','wb').write(r)"
git show "origin/main:$EGDBMIX_GZ" | gunzip > "$W/egdbmix.pjtw" 2>/dev/null || : > "$W/egdbmix.pjtw"
git show "origin/main:$MIX_GZ" | gunzip > "$W/mix.jnnw" || { say "ABORT mix2M absent"; exit 4; }
git show "origin/main:$SUPP_GZ" | gunzip > "$W/supp.jnnw" 2>/dev/null && SUPP_OK=1 || { : > "$W/supp.jnnw"; SUPP_OK=0; }
git show "origin/main:$COMBO_SRC" > "$W/combos.jnnw" 2>/dev/null || : > "$W/combos.jnnw"
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  mix2M=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/mix.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) supp=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/supp.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) combos=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0)"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
concat(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,sys
out=sys.argv[1]; body=b""; tot=0; parts=[]
for f in sys.argv[2:]:
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n; parts.append((f.split('/')[-1],n))
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print("  concat -> "+str(tot)+" : "+", ".join(f"{k}={v}" for k,v in parts))
PY
}
fit(){ env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$1" --feat "$2" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prior-mean "$W/gen1_prior.pjtw" --prior-visit-scale "$PRIOR_VISIT" --prior-decay "$PRIOR_DECAY" --out "$3" \
    >"${3%.pjtw}.log" 2>&1 || { say "TRAIN FAIL"; tail -14 "${3%.pjtw}.log"|sed 's/^/  /'; exit 9; }; }
# JUGE en config ERE-GEN1 : qs_threat_ext=0 force des DEUX cotes (comparabilite exacte avec gen1/gen2)
pjudge(){ local np="$1" rp="$2" tag="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$np" \
    --jass-b "$J" --pattern-b "$rp" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" \
    --quiet --openings-file "$DILF" --search-params-a "qs_threat_ext=0" --search-params-b "qs_threat_ext=0" \
    >"$W/j.$s" 2>&1 & done; wait
  python3 - "$tag" "$W"/j.* <<'PY'
import sys,math; tag=sys.argv[1]; a=d=b=0
for f in sys.argv[2:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"  [{tag}] games={g} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  (juge ere-gen1: threat_ext=0)")
PY
  rm -f "$W"/j.* ; }

say ""; say "=== corpus = mix2M + supp-pd10 + combos -> fit prior gen1 (lambda=$PRIOR_VISIT) ==="
concat "$W/corpus.jnnw" "$W/mix.jnnw" "$W/supp.jnnw" "$W/combos.jnnw" | tee -a "$RES"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
fit "$W/corpus.jnnw" "$W/feat" "$W/candmix.pjtw"; rm -f "$W/feat"
grep -iE 'prior|train_loss' "$W/candmix.log" | tail -3 | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/candmix.pjtw" > "$ART/champion-mix2M.pjtw.gz"
commit_to_main "$ART/champion-mix2M.pjtw.gz" "$ARTREL/champion-mix2M.pjtw.gz" "fit-matin: commit champion-mix2M JOB-SIDE" \
  && say "  champion-mix2M committe JOB-SIDE" || say "  ⚠ commit job-side echoue"

say ""; say "=== JUGE (config ERE-GEN1, threat_ext=0 des 2 cotes) ==="
pjudge "$W/candmix.pjtw" "$W/gen1.pjtw" "mix2M-vs-gen1" | tee -a "$RES"
[ -s "$W/egdbmix.pjtw" ] && pjudge "$W/candmix.pjtw" "$W/egdbmix.pjtw" "mix2M-vs-egdbmix" | tee -a "$RES"
say ""
say "  => mix2M-vs-gen1 borne basse IC >0.50 (COMPOSE) => la donnee complete-archi+mix-profondeur DEBLOQUE la chaine"
say "     => promouvoir cand-mix, gen3. Sinon (<=gen1) => plateau CONFIRME sur archi complete => phase EBF."
say "=== fin fit-matin mix2M ==="
