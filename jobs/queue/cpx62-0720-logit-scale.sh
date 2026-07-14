#!/usr/bin/env bash
# id: cpx62-0720-logit-scale
# description: SWEEP LOGIT-SCALE (mémo T2b, suite 0719) — 0719 a trouvé le smoking-gun : z0/T max=+11.35 (T=1) => σ
# SATURÉE sur les positions matériellement tranchées. Or les ÉCHECS de conversion (matériel haut mais NON gagné = trou
# 0703) sont là : bootstrap prédit σ→1, vrai label nulle/perte => CE énorme mais gradient σ'(z)≈0 => le fit NE PEUT PAS
# apprendre la conversion. HYPOTHÈSE : dé-saturer (augmenter --logit-scale T) débloque l'apprentissage-conversion.
# TEST : refit full@0.05 (anchor de la recette) × T∈{1 contrôle, 4, 8}, corpus T1 committé (AUCUNE regen). Mesures :
# (a) z0/T dé-sature (|z/T| retombe ~1-3), (b) patterns nz GROSSIT (le fit bouge enfin des poids), (c) conv_self sur la
# JAUGE STRATIFIÉE FIGÉE v2 (0718, 1600 pos, disjointe) — la conversion monte-t-elle avec T ? (d) gate vs bootstrap.
# ⚠ CONFOND connu : un T plus grand peut gonfler l'échelle des poids de sortie => marges de search relatives ≠ ; conv_self
# + nz + z-stats sont les signaux PROPRES, le gate Elo est secondaire (à re-scaler proprement au tour suivant si conv monte).
# Pas d'egdb. AUCUN NNUE. AUCUN bake.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0720.lock
if ! flock -n 9; then echo "ABORT 0720 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0720-logit-scale/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0720-logit-scale/artefacts"
W=/root/cw-0720; GEOM=/root/jass-geom32-0720
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
EVALSTRAT=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
MAXIT=60; CHUNK=1000000; CONV_DEPTH=10; ANCHOR=0.05
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
      --pool-file "$W/conv_pool.fen" --depth "$CONV_DEPTH" --lead 1 --max-plies 260 \
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
fit_a(){ # $1=lab $2=logit_scale -> $W/cand_$1.pjtw ; z-stats + POV-gate capturés
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$W/full.jnnw" --feat "$W/feat" --out "$W/cand_$1.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --logit-scale "$2" --color-fold --tempo-stage \
    --max-iter "$MAXIT" --chunk "$CHUNK" --verify-jass "$J" --verify-n 80 >"$W/ft_$1.log" 2>&1 \
    || { say "  [$1] FIT ABORT : $(tail -1 "$W/ft_$1.log")"; return 1; }
  return 0
}
delta_w(){ python3 - "$W/bootstrap.pjtw" "$1" "$2" <<'PY'
import struct,sys,numpy as np
b0=open(sys.argv[1],'rb').read(); b1=open(sys.argv[2],'rb').read()
_,_,sc,npat,next_=struct.unpack_from('<IIIII',b0,0)
a0=np.frombuffer(b0,dtype='<i4',offset=20).astype(np.float64)/sc; a1=np.frombuffer(b1,dtype='<i4',offset=20).astype(np.float64)/sc
de=np.abs(a1[2*npat:2*npat+next_]-a0[2*npat:2*npat+next_]); dp=np.abs(a1[:npat]-a0[:npat])
print(f"  [{sys.argv[3]}] |Δw| EXTRA max={de.max():.4f} | patterns nz={int((dp>1e-9).sum())}")
PY
}

say "=== SWEEP LOGIT-SCALE (dé-saturation, corpus T1 committé SANS regen) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
for f in tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; do git show "origin/$SRC_BRANCH:$f" > "$f" 2>/dev/null || true; done
restore_src(){ git checkout -- src pattern_jass/src pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }

say "=== build jass (v4, sans egdb) ==="
cmake -S . -B "$W/build" $FLAGS >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0720 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/full.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }
git show "origin/main:$EVALSTRAT" > "$W/eval_strat_full.fen" || { say "ABORT eval strat v2"; restore_src; exit 4; }
# sous-échantillon ÉQUILIBRÉ par palier (1 non-# sur 4 ≈ 400 pos, l'ordre est par palier) — diagnostic, pas jauge pleine
grep -vE '^\s*#' "$W/eval_strat_full.fen" | awk 'NR%4==1' > "$W/conv_pool.fen"
"$J" --dump-eval-features "$W/full.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "ABORT dump-features"; restore_src; exit 6; }
NCP=$(grep -cvE '^\s*#' "$W/conv_pool.fen"); say "  ✓ build + bootstrap + corpus T1 + jauge conv_self v2 sous-éch. ($NCP pos, FIGÉE disjointe)"
# baseline conversion du bootstrap lui-même (repère)
read BCS BCN < <(conv_self "boot" "$W/bootstrap.pjtw")
say "  [bootstrap] conv_self baseline = $BCS (n=$BCN)"

# --- sweep T ---
for T in 1 4 8; do
  lab="T$T"
  say ""; say "--- refit full@$ANCHOR × logit-scale=$T ---"
  if fit_a "$lab" "$T"; then
    grep -iE 'z-stats|POV gate|Spearman' "$W/ft_$lab.log"|sed 's/^/    /'|tee -a "$RES"
    delta_w "$W/cand_$lab.pjtw" "$lab" | tee -a "$RES"
    read CS NP1 < <(conv_self "$lab" "$W/cand_$lab.pjtw")
    read GR GN GE < <(gate_vs_boot "$lab" "$W/cand_$lab.pjtw")
    say "  [$lab] conv_self=$CS (n=$NP1) | gate vs bootstrap : rate=$GR n=$GN elo=$GE"
  fi
done

say ""; say "=== VERDICT SWEEP LOGIT-SCALE ==="
python3 - "$RES" <<'PY' | tee -a "$RES"
import re,sys
txt=open(sys.argv[1]).read()
mb=re.search(r"\[bootstrap\] conv_self baseline = ([\d.]+)",txt); boot=float(mb.group(1)) if mb else None
g={}
for T in (1,4,8):
    m=re.search(rf"\[T{T}\] conv_self=([\d.]+) \(n=(\d+)\) \| gate vs bootstrap : rate=[\d.]+ n=\d+ elo=([+-]?\d+)",txt)
    mz=re.search(rf"--- refit full@[\d.]+ × logit-scale={T} ---.*?z0/T : min=([+-][\d.]+) max=([+-][\d.]+).*?nz=(\d+)",txt,re.S)
    if m: g[T]=(float(m.group(1)),int(m.group(3)),float(mz.group(2)) if mz else None,int(mz.group(3)) if mz else None)
print(f"  bootstrap conv_self baseline = {boot}")
for T in (1,4,8):
    if T in g: cs,elo,zmax,nz=g[T]; print(f"  T={T} : conv_self={cs:.4f}  z0/T_max={zmax}  patterns_nz={nz}  gate_elo={elo:+d}")
cs=[g[T][0] for T in (1,4,8) if T in g]
if boot is not None and len(cs)==3:
    best=max(cs); bestT=[T for T in (1,4,8) if T in g and g[T][0]==best][0]
    if best >= cs[0]+0.03 and g[bestT][3] > g[1][3]:
        print(f"  => ✓ DÉ-SATURER DÉBLOQUE : conv_self monte {cs[0]:.3f}→{best:.3f} à T={bestT} ET le fit apprend (nz {g[1][3]}→{g[bestT][3]}). ⟹ la SATURATION bloquait l'apprentissage-conversion. Suite : re-scaler proprement le bootstrap (échelle logit saine) puis rejouer le smoke L3.")
    elif best >= cs[0]+0.03:
        print(f"  => ~ conv_self monte à T={bestT} mais nz peu (confond échelle/search possible) — inspecter le gate + re-scaler bootstrap au tour suivant.")
    else:
        print(f"  => ✗ dé-saturer NE monte PAS conv_self (best {best:.3f} ≤ T1 {cs[0]:.3f}+0.03) ⟹ la saturation n'était pas le bloqueur de conversion. Piste = (ii) adjud / labels, pas l'échelle du fit.")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0720 FIN sweep logit-scale T{1,4,8} : conv_self + nz + z-stats + gate" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0720 FINI ==="
rm -rf "$W" "$GEOM"
