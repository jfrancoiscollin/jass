#!/usr/bin/env bash
# id: cpx62-0716-refit-anchor
# description: F-ANCHOR (suite D1) — le D3 a montré que l'anchor 0.05 ÉRODE l'EXTRA/matériel du bootstrap (|Δw| EXTRA
# max 0.405) → régression transversale (oracle −26, onp −47). Test : re-fitter le corpus T1 DÉJÀ COMMITTÉ (0715, AUCUNE
# regen) avec un anchor SERRÉ qui protège le matériel : full@0.15, full@0.30, oracle@0.15. Contrôle = 0715 full@0.05
# (elo −27, conv 0.5469). Chaque : conv_self + généraliste vs bootstrap (~600 games). Si un anchor serré cesse de
# régresser => l'érosion (i) était le lever ; sinon l'anchor n'était pas tout. Pas d'egdb (fit+gate seuls). AUCUN NNUE.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0716.lock
if ! flock -n 9; then echo "ABORT 0716 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0716-refit-anchor/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0716-refit-anchor/artefacts"
W=/root/cw-0716; GEOM=/root/jass-geom32-0716
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
LABELS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.labels.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
MAXIT=60; CHUNK=1000000; CONV_DEPTH=10
NOPEN=300; PAIRS=1; DEPTH=9; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
conv_self(){ local pids=()  # $1=lab $2=pattern -> "conv n"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/conv_self.py --jass "$J" --pattern "$2" --defender-pattern "$W/gen2.pjtw" \
      --pool-file "$W/conversion_pool.fen" --depth "$CONV_DEPTH" --lead 1 --max-plies 260 \
      --shard "$s" --nshards "$NSH" --out "$W/cs_$1.$s.json" >"$W/cs_$1.$s.log" 2>&1 & pids+=($!); done
  wait "${pids[@]}"
  python3 - "$W"/cs_$1.*.json <<'PY'
import json,sys
P=Wn=0
for f in sys.argv[1:]:
    try: j=json.load(open(f)); P+=j["n_pos"]; Wn+=j["n_win"]
    except Exception: pass
print(f"{(Wn/P if P else 0):.4f} {P}")
PY
}
gate_vs_boot(){ local pids=()  # $1=lab $2=pattern -> "rate n elo"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$2" --jass-b "$J" --pattern-b "$W/bootstrap.pjtw" \
      --search-params-a "$QS" --search-params-b "$QS" --depth "$DEPTH" --pairs "$PAIRS" --max-plies 160 \
      --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" >"$W/g_$1.$s" 2>&1 & pids+=($!); done
  wait "${pids[@]}"
  python3 - "$W"/g_$1.* <<'PY'
import sys,math
a=d=b=0
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"{r:.4f} {g} {elo:+.0f}")
PY
}
fit_a(){ # $1=lab $2=data $3=anchor -> $W/cand_$1.pjtw
  "$J" --dump-eval-features "$2" "$W/feat_$1" >"$W/dump_$1.log" 2>&1 || { say "  [$1] DUMP FAIL"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$2" --feat "$W/feat_$1" --out "$W/cand_$1.pjtw" \
    --tools pattern_jass/tools --anchor "$3" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" >"$W/ft_$1.log" 2>&1 \
    || { say "  [$1] FIT ABORT : $(tail -1 "$W/ft_$1.log")"; return 1; }
  return 0
}
delta_w(){ python3 - "$W/bootstrap.pjtw" "$1" "$2" <<'PY'
import struct,sys,numpy as np
b0=open(sys.argv[1],'rb').read(); b1=open(sys.argv[2],'rb').read()
_,_,sc,npat,next_=struct.unpack_from('<IIIII',b0,0)
a0=np.frombuffer(b0,dtype='<i4',offset=20).astype(np.float64)/sc; a1=np.frombuffer(b1,dtype='<i4',offset=20).astype(np.float64)/sc
de=np.abs(a1[2*npat:2*npat+next_]-a0[2*npat:2*npat+next_]); dp=np.abs(a1[:npat]-a0[:npat])
print(f"  [{sys.argv[3]}] |Δw| EXTRA max={de.max():.4f} mean={de.mean():.4f} | patterns nz={int((dp>1e-9).sum())}")
PY
}

say "=== F-ANCHOR (refit corpus T1 committé, SANS regen) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
for f in tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; do git show "origin/$SRC_BRANCH:$f" > "$f" 2>/dev/null || true; done
git show "origin/$SRC_BRANCH:data/conversion_pool.fen" > "$W/conversion_pool.fen" 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }

say "=== build jass (v4, sans egdb) ==="
cmake -S . -B "$W/build" $FLAGS >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0716 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
# corpus T1 committé (AUCUNE regen) + split oracle
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/full.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }
git show "origin/main:$LABELS_GZ" | gunzip > "$W/labels" || { say "ABORT labels"; restore_src; exit 4; }
python3 - "$W/full.jnnw" "$W/labels" "$W/oracle.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; L=open(sys.argv[2],'rb').read(); REC=38; body=b[8:]
orc=bytearray(); no=0
for i in range(n):
    if L[i] in (1,2): orc+=body[i*REC:(i+1)*REC]; no+=1
open(sys.argv[3],'wb').write(b'JNNW'+struct.pack('<I',no)+bytes(orc))
print(f"  corpus T1={n} ; oracle(GYM+CAP)={no}")
PY
say "  ✓ build + bootstrap + corpus T1 committé (sans regen) ; contrôle 0715 full@0.05 = elo −27 conv 0.5469"

# --- 3 refits ancrés serrés ---
declare -a JOBS=("full15:$W/full.jnnw:0.15" "full30:$W/full.jnnw:0.30" "oracle15:$W/oracle.jnnw:0.15")
for spec in "${JOBS[@]}"; do
  lab="${spec%%:*}"; rest="${spec#*:}"; data="${rest%%:*}"; anc="${rest##*:}"
  say ""; say "--- refit $lab (data=$(basename "$data") anchor=$anc) ---"
  if fit_a "$lab" "$data" "$anc"; then
    grep -iE 'logloss|delta' "$W/ft_$lab.log"|tail -1|sed 's/^/    /'|tee -a "$RES"
    delta_w "$W/cand_$lab.pjtw" "$lab" | tee -a "$RES"
    read CS NP1 < <(conv_self "$lab" "$W/cand_$lab.pjtw")
    read GR GN GE < <(gate_vs_boot "$lab" "$W/cand_$lab.pjtw")
    say "  [$lab] conv_self=$CS (n=$NP1) | généraliste vs bootstrap : rate=$GR n=$GN elo=$GE"
  fi
done

say ""; say "=== VERDICT F-ANCHOR ==="
python3 - "$RES" <<'PY' | tee -a "$RES"
import re,sys
txt=open(sys.argv[1]).read(); g={}
for V in ("full15","full30","oracle15"):
    m=re.search(rf"\[{V}\] conv_self=([\d.]+).*?rate=([\d.]+).*?elo=([+-]?\d+)",txt,re.S)
    if m: g[V]=(float(m.group(1)),float(m.group(2)),int(m.group(3)))
print("  contrôle 0715 full@0.05 : conv 0.5469 elo −27")
for V in ("full15","full30","oracle15"):
    if V in g: print(f"  {V:9s} : conv {g[V][0]:.4f}  elo {g[V][2]:+d}")
fe=[g[V][2] for V in ("full15","full30") if V in g]
if fe and max(fe) >= -12:
    print("  => ANCHOR = LE LEVER : un anchor serré cesse (~) de régresser => l'érosion EXTRA était (i). Enchaîner : + adjud (ii) + pondération-gymnase (iii).")
elif fe and max(fe) > -27:
    print("  => anchor AIDE partiellement (moins que −27) mais régresse encore => érosion réelle MAIS pas tout => enchaîner F1 adjud (ii).")
else:
    print("  => anchor N'AIDE PAS (≤ −27) => l'érosion n'était pas le lever principal => F1 adjud (ii) / D2 ventilation.")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0716 FIN F-anchor : full@0.15/0.30 + oracle@0.15 vs contrôle full@0.05 (−27)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0716 FINI ==="
rm -rf "$W" "$GEOM"
