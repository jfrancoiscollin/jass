#!/usr/bin/env bash
# id: cpx62-0582-labelhyg-decisive
# description: MINI-VALIDATION DECISIVE label-hygiene (JFC : 300k trop peu + verifier que les labels sont INTRINSEQUEMENT
# plus propres). Ameliore 0581 : (1) volume 600k, (2) fit FROM-SCRATCH (pas de prior gen1 qui masque l'effet — gen1 a ete
# fit sur labels contamines), (3) VERIF LABEL-CORRECTNESS = deep-search oracle d16 sur un echantillon des 2 corpus, accord
# sign(wdl-partie) vs sign(deep-score). ANCIEN pipeline (eps=5, sans fixes) vs NOUVEAU (FIX#1 decay+drop, #2 adjud, #3 pair).
# Sorties : (A) accord-oracle ancien vs nouveau (les labels neufs doivent etre + justes) + (B) match eval-new vs eval-old
# from-scratch (les labels propres doivent produire un meilleur eval). Le deep-search sert de JUGE, pas de source de label
# (pas de distillation, §6 vise le label d'entrainement). Code depuis DEVELOP. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0582-labelhyg-decisive/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0582-labelhyg-decisive/artefacts"
W=/root/cw-lhdec; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-lhdec
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
VOL=600000; LABEL_DEPTH=4; PD=6; MAXPLIES=200; FORCE="ext_forcing=1,forcing_ext_cap=6"
L2=3e-5; MAXIT=25; CHUNK=1000000; JUDGE_DEPTH=9; JUDGE_PAIRS=4
ORACLE_DEPTH=16; ORACLE_SPARAMS="probcut_min_depth=0,multicut_min_depth=0,razor_max_depth=0"; ORACLE_N=1500
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

say "=== MINI-VALIDATION DECISIVE (from-scratch + verif oracle) — overlay develop ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
grep -q 'explore-decay-plies' src/main.cpp || { say "ABORT fixes absents"; exit 5; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git checkout -- src/main.cpp pattern_jass/tools/train_stream.py 2>/dev/null || true

gen_pipeline(){ local tag="$1"; shift; local extra="$*"; local per=$(( (VOL+NCPU-1)/NCPU ))
  say ""; say "=== GEN $tag : ${VOL} @ pd${PD} ($extra) ==="
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/${tag}.$s.jnnw" "$LABEL_DEPTH" "$PD" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE" --quiet-only --explore-eps 5 --random-open-plies 8 $extra \
      >"$W/gen_${tag}_$s.log" 2>&1 & done; wait
  local N; N=$(merge_into "$W/${tag}.jnnw" "$W/${tag}.*.jnnw"); rm -f "$W/${tag}."[0-9]*.jnnw
  say "  $tag : $N pos ; $(grep -h LABELHYG "$W/gen_${tag}_1.log"|head -1)"
}
gen_pipeline old ""
gen_pipeline new "--explore-decay-plies 20 --drop-post-eps --adjud-material 3 --adjud-hold-plies 10 --pair-openings"

# ---------- (A) VERIF LABEL-CORRECTNESS : accord sign(wdl) vs sign(deep-score d16) ----------
oracle_agree(){ local tag="$1"; local sub="$W/sub_$tag.jnnw"
  python3 - "$W/${tag}.jnnw" "$sub" "$ORACLE_N" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; K=min(int(sys.argv[3]),n); step=max(1,n//K)
idx=list(range(0,n,step))[:K]
with open(sys.argv[2],'wb') as f:
    f.write(b'JNNW'); f.write(struct.pack('<I',len(idx)))
    for i in idx: f.write(b[8+i*REC:8+(i+1)*REC])
PY
  # split + deep-relabel (reecrit score avec la valeur d16) ; wdl inchange
  python3 - "$sub" "$W/osh_$tag" "$NCPU" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    lo=s*per; hi=min((s+1)*per,n); m=max(0,hi-lo)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',m)+(body[lo*REC:hi*REC] if m else b''))
PY
  for s in $(seq 0 $((NCPU-1))); do "$J" --deep-relabel "$W/osh_${tag}.$s.jnnw" "$W/odeep_${tag}.$s.jnnw" "$ORACLE_DEPTH" \
      --nnue "$W/gen1.pjtw" --search-params "$ORACLE_SPARAMS" --draw-band 50 >"$W/orl_${tag}_$s.log" 2>&1 & done; wait
  merge_into "$W/odeep_$tag.jnnw" "$W/odeep_${tag}.*.jnnw" >/dev/null; rm -f "$W/odeep_${tag}."[0-9]*.jnnw "$W/osh_${tag}."*
  python3 - "$W/odeep_$tag.jnnw" "$tag" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]
agree=tot=0
for i in range(n):
    r=body[i*REC:(i+1)*REC]; score=struct.unpack('<i',r[33:37])[0]; wdl=struct.unpack('<b',r[37:38])[0]
    if wdl==0: continue          # nulles : on ne juge que les decisifs
    tot+=1
    ds = 1 if score>50 else (-1 if score<-50 else 0)  # sign du deep-score (draw-band 50)
    if ds==wdl: agree+=1
print(f"AGREE {sys.argv[2]} {agree}/{tot} = {agree/tot:.3f}" if tot else f"AGREE {sys.argv[2]} n/a")
PY
}
say ""; say "=== (A) VERIF LABEL-CORRECTNESS : accord label-partie vs oracle deep d${ORACLE_DEPTH} (decisifs seulement) ==="
AG_OLD=$(oracle_agree old | tee -a "$VERD" | grep -oE '= [0-9.]+' | tr -d '= ')
AG_NEW=$(oracle_agree new | tee -a "$VERD" | grep -oE '= [0-9.]+' | tr -d '= ')
say "  => accord ancien=$AG_OLD  nouveau=$AG_NEW  ($([ -n "$AG_NEW" ] && [ -n "$AG_OLD" ] && python3 -c "print('NOUVEAU + JUSTE' if $AG_NEW>$AG_OLD else 'pas + juste')" || echo '?'))"

# ---------- (B) FIT FROM-SCRATCH + MATCH ----------
fit_fs(){ local data="$1" out="$2"
  "$J" --dump-eval-features "$data" "$W/feat" >"$W/f.log" 2>&1 || return 1
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --prune-min-visits 1 \
    --out "$out" >"${out%.pjtw}.log" 2>&1 || { say "TRAIN FAIL $(tail -2 "${out%.pjtw}.log"|tr '\n' ' ')"; return 1; }
  rm -f "$W/feat"; }
say ""; say "=== (B) FITS FROM-SCRATCH (pas de prior => isole l'effet label) ==="
fit_fs "$W/old.jnnw" "$W/eval_old.pjtw" && say "  eval_old (from-scratch) OK" || exit 9
fit_fs "$W/new.jnnw" "$W/eval_new.pjtw" && say "  eval_new (from-scratch) OK" || exit 9
say ""; say "=== MATCH eval_NEW vs eval_OLD (from-scratch, d${JUDGE_DEPTH} dilf) ==="
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
vd="NOUVEAU>ANCIEN hors-IC : labels propres => meilleur eval => LEVIER CONFIRME, integrer + GO gros gen propre" if lo>0.5 else ("NOUVEAU<ANCIEN hors-IC : l'hygiene degrade (investiguer)" if hi<0.5 else "PARITE : effet non significatif a ce volume")
print(f"  [new-vs-old from-scratch] games={g} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  IC=[{lo:.4f},{hi:.4f}]")
print(f"  => {vd}")
PY
say "=== fin mini-validation decisive ==="
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0582 mini-validation decisive : accord-oracle + match from-scratch (labels propres vs contamines)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
