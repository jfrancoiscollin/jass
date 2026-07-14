#!/usr/bin/env bash
# id: cpx62-0719-anchor-diag
# description: DIAG ANCHOR (mémo JFC 2026-07-14) — 0716 viole la monotonie de l'ancrage (serrer 0.05→0.15→0.30 fait
# −27→−292→−220 = s'éloigne de la référence). Le code+T3 réfutent déjà H-A (w0=bootstrap COMPLET, ‖dw‖∝1/anchor
# monotone, |Δw|EXTRA 0.405→0.223→0.139 = converge vers bootstrap). Ce job TRANCHE au runtime, AUCUNE regen (corpus T1
# committé). T1 λ-ÉNORME : fit full@{1,10,100} + POV-gate (--verify-jass : Spearman X·w0 vs eval réelle >0.95 = référence
# alignée) + z-stats z0/T (saturation = H-B mismatch d'échelle) + ‖Δw‖ directionnel + gate Elo vs bootstrap. + CELLULE
# SANITÉ bootstrap-vs-bootstrap (DOIT ~0.5 sinon harness cassé = vrai bug). Lectures : Elo→~0 quand λ↑ ⟹ référence saine,
# la vallée 0.15/0.30 = H-B (non-convexité réelle, pas bug) ; Elo≪0 même @100 ⟹ référence/harness cassé. Garde-fou
# gravé : tout DOE d'anchor porte une cellule λ-énorme (gate attendu ≈ référence). Pas d'egdb. AUCUN NNUE. AUCUN bake.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0719.lock
if ! flock -n 9; then echo "ABORT 0719 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0719-anchor-diag/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0719-anchor-diag/artefacts"
W=/root/cw-0719; GEOM=/root/jass-geom32-0719
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
MAXIT=60; CHUNK=1000000
NOPEN=300; PAIRS=1; DEPTH=9; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
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
fit_a(){ # $1=lab $2=data $3=anchor -> $W/cand_$1.pjtw ; POV-gate + z-stats capturés
  "$J" --dump-eval-features "$2" "$W/feat_$1" >"$W/dump_$1.log" 2>&1 || { say "  [$1] DUMP FAIL"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$2" --feat "$W/feat_$1" --out "$W/cand_$1.pjtw" \
    --tools pattern_jass/tools --anchor "$3" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
    --verify-jass "$J" --verify-n 80 >"$W/ft_$1.log" 2>&1 \
    || { say "  [$1] FIT ABORT : $(tail -1 "$W/ft_$1.log")"; return 1; }
  return 0
}
delta_w(){ python3 - "$W/bootstrap.pjtw" "$1" "$2" <<'PY'
import struct,sys,numpy as np
b0=open(sys.argv[1],'rb').read(); b1=open(sys.argv[2],'rb').read()
_,_,sc,npat,next_=struct.unpack_from('<IIIII',b0,0)
a0=np.frombuffer(b0,dtype='<i4',offset=20).astype(np.float64)/sc; a1=np.frombuffer(b1,dtype='<i4',offset=20).astype(np.float64)/sc
de=np.abs(a1[2*npat:2*npat+next_]-a0[2*npat:2*npat+next_]); dp=np.abs(a1[:npat]-a0[:npat])
tot=np.sqrt(float(np.dot(a1-a0,a1-a0)))
print(f"  [{sys.argv[3]}] |Δw| EXTRA max={de.max():.4f} mean={de.mean():.4f} | patterns nz={int((dp>1e-9).sum())} | ‖Δw‖tot={tot:.4f}")
PY
}

say "=== DIAG ANCHOR (T1 λ-énorme, corpus T1 committé SANS regen) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
git show "origin/$SRC_BRANCH:pattern_jass/tools/make_bootstrap_eval.py" > pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py 2>/dev/null||true; rm -f pattern_jass/tools/make_bootstrap_eval.py; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }

say "=== build jass (v4, sans egdb) ==="
cmake -S . -B "$W/build" $FLAGS >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0719 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/full.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }
say "  ✓ build + bootstrap + corpus T1 committé (sans regen)"

# --- CELLULE SANITÉ : bootstrap vs bootstrap DOIT ~0.5 (sinon harness cassé) ---
say ""; say "--- SANITÉ : gate bootstrap vs bootstrap (attendu ~0.500) ---"
read SR SN SE < <(gate_vs_boot "sanity" "$W/bootstrap.pjtw")
say "  [SANITÉ] boot-vs-boot rate=$SR n=$SN elo=$SE  $([ "$SN" -gt 0 ] && python3 -c "print('✓ harness SAIN' if abs($SR-0.5)<0.06 else '✗✗ HARNESS CASSÉ (explique tout 0716)')" || echo '✗ n=0')"

# --- T1 : fits λ croissant (0.05 contrôle connu −27, puis 1/10/100) ---
declare -a JOBS=("full1:$W/full.jnnw:1.0" "full10:$W/full.jnnw:10" "full100:$W/full.jnnw:100")
for spec in "${JOBS[@]}"; do
  lab="${spec%%:*}"; rest="${spec#*:}"; data="${rest%%:*}"; anc="${rest##*:}"
  say ""; say "--- refit $lab (data=full.jnnw anchor=$anc) ---"
  if fit_a "$lab" "$data" "$anc"; then
    grep -iE 'z-stats|POV gate|Spearman' "$W/ft_$lab.log"|sed 's/^/    /'|tee -a "$RES"
    delta_w "$W/cand_$lab.pjtw" "$lab" | tee -a "$RES"
    read GR GN GE < <(gate_vs_boot "$lab" "$W/cand_$lab.pjtw")
    say "  [$lab] gate vs bootstrap : rate=$GR n=$GN elo=$GE"
  fi
done

say ""; say "=== VERDICT DIAG ANCHOR ==="
python3 - "$RES" <<'PY' | tee -a "$RES"
import re,sys
txt=open(sys.argv[1]).read()
m=re.search(r"\[SANITÉ\] boot-vs-boot rate=([\d.]+) n=(\d+)",txt); san=float(m.group(1)) if m else None
g={}
for V in ("full1","full10","full100"):
    m=re.search(rf"\[{V}\] gate vs bootstrap : rate=([\d.]+) n=(\d+) elo=([+-]?\d+)",txt)
    if m: g[V]=(float(m.group(1)),int(m.group(2)),int(m.group(3)))
print(f"  SANITÉ boot-vs-boot = {san}")
print("  contrôle connu : full@0.05=−27 · full@0.15=−292 · full@0.30=−220")
for V in ("full1","full10","full100"):
    if V in g: print(f"  {V:8s} (λ={ {'full1':1,'full10':10,'full100':100}[V] }) : elo {g[V][2]:+d}  (n={g[V][1]})")
e100=g.get("full100",(0,0,-999))[2]
if san is not None and abs(san-0.5)>=0.06:
    print("  => ✗✗ HARNESS CASSÉ (boot-vs-boot ≠ 0.5) : TOUT 0716 est un artefact de gate. Le vrai bug est dans jass_vs_jass_arch / le chargement pattern. Corriger AVANT toute lecture stratégique.")
elif e100 >= -15:
    print("  => ✓ RÉFÉRENCE SAINE : Elo→~0 quand λ↑ (monotone en poids ET Elo aux extrêmes). La vallée 0.15/0.30 = H-B (non-convexité RÉELLE : matériel distordu SANS compensation-patterns), PAS un bug. ⟹ D1-(i) réhabilité en partie (l'anchor lâche laisse la data bouger le matériel) mais l'anchor n'est pas un levier de GAIN. Piste réelle = (ii) adjud + (iii) gymnase. Documenter T4 (anchor global vs data/N).")
else:
    print(f"  => ⚠ Elo encore {e100:+d} à λ=100 malgré ‖dw‖→0 : incohérence référence↔espace-fit (POV-gate à lire). Inspecter l'alignement w0/X folded (color-fold/tempo-stage) — H-A résiduelle au runtime.")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0719 FIN diag anchor : sanité + full@{1,10,100} POV-gate + z-stats + Elo(λ)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0719 FINI ==="
rm -rf "$W" "$GEOM"
