#!/usr/bin/env bash
# id: cpx62-0697-doe-search-b3b
# description: B3b — RE-DOE COIN DES CUTS sur gen2-mmto (mémo BOOST, go JFC "Go b3"). Hypothèse (inchangée) : une MEILLEURE
# éval (gen2-mmto, d9 +34/+46 vs Scan) TOLÈRE une recherche plus AGRESSIVE → chercher plus PROFOND à temps fixe → convertir
# le gain éval-par-nœud (+34 d9 encore stocké aux 3/4 ; movetime +5-6 seulement) en Elo MOVETIME. 0657 a déjà tué asp30/
# asp20/combo(asp30+lmr+nmp) à haut-N ; ici on teste des leviers NON encore couverts, direction agressive : probcut_margin
# resserré (probcut DÉJÀ bakée min_depth=5, on durcit la marge 150→100), single-reply extension (ext_single_reply, OFF par
# défaut), et le TRIPLE du mémo asp30×lmr_log×probcut. OAT : chaque cellule = gen2-mmto + UN knob (side A) vs gen2-mmto
# search DÉFAUT (side B), MÊME éval, mt0.2 généraliste ≥38p, UN build (knobs runtime via --search-params-a). GATE :
# rate_A>0.5 hors-IC => ce knob convertit éval→movetime => confirm haut-N (mt0.3+dilf) + baker search. Sanity : baseline
# défaut-vs-défaut ≈ 0.5 ; n<plancher => INCONCLUANT (pas "neutre"). ROBUSTESSE (checklist 12pts, 0657 avait HUNG) :
# df-guard + clean cw-* stale + timeout PAR SHARD + RES dans $W (hors arbre) + monitor progress. ⚠️ bug go-movetime
# overshoot endgame (harnais catch timeout→nulle). Elo-first. AUCUN NNUE. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0697-doe-search-b3b/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0697-doe-search-b3b/artefacts"
W=/root/cw-doe-b3b
# --- checklist 8bis : hygiène disque (clean stale cw-* >3h sauf le sien, garde df) ---
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
# --- checklist 8ter : RES/PROG dans $W (HORS arbre git), jamais dans $ART ---
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go ($DFA Mo)"; exit 3; }
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
NOPEN=96; PAIRS=8; ABMT=0.2; SHARD_TIMEOUT=2400; MIN_N=600
# DOE OAT (nom:params) — leviers NON couverts par 0657, direction agressive + sanity
CELLS=(
  "baseline:"                                                            # sanity ~0.5
  "pcm100:probcut_margin=100"                                            # probcut plus agressif (marge 150->100)
  "single:ext_single_reply=1"                                           # single-reply extension (Scan, OFF défaut)
  "triple:aspiration_initial=30,lmr_formula=1,probcut_margin=100"        # le triple du mémo asp30×lmr_log×probcut
)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== B3b DOE SEARCH gen2-mmto (OAT knobs agressifs, mt$ABMT généraliste) — HEAD $(git log --oneline -1|cat) ==="
say "  box: NCPU=$NCPU df=${DFA}Mo ; cellules=${#CELLS[@]} PAIRS=$PAIRS NOPEN=$NOPEN timeout/shard=${SHARD_TIMEOUT}s"
# --- garde-fou archi (checklist 11) : pull explicite + assert AVANT cmake ---
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
# CONSISTANCE SRC (fix 0694/0697 BUILD FAIL) : pull TOUS les fichiers src qui
# DIVERGENT main<->develop, sinon develop main.cpp compile contre des headers
# base périmés (ex. compact_scan_weights déclarée seulement dans develop
# scan_eval.hpp) => BUILD FAIL. Dynamique => robuste aux divergences futures.
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
say "  src divergents pull develop : $(echo $DIVERGED | tr '\n' ' ')"
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
restore_src(){ git checkout -- src pattern_jass/src tools/jass_vs_jass_arch.py 2>/dev/null||true; }
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS g_emasks"; restore_src; exit 5; }
  grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
  grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
  say "  garde-fou archi ✓ (g_emasks + has_any_capture)"; }
arch_assert
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
build_ok=0
for attempt in 1 2; do
  if cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.$attempt.log" 2>&1; then build_ok=1; break; fi
  say "  build tentative $attempt échouée, retry..."
done
[ "$build_ok" = 1 ] || { say "BUILD FAIL :"; grep -iE "error:|Error [0-9]|fatal" "$W/build.2.log"|head -12|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0697 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
say "  ✓ build+gen2 (NCPU=$NCPU)"

# openings généralistes ≥38p (ancre 0657)
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw"
python3 - "$W/corpus.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
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
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG"; [ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 7; }

# ---- OAT : chaque knob (side A) vs défaut (side B), timeout PAR SHARD ----
say ""; say "=== OAT DOE (side A = gen2-mmto+knob vs side B = défaut, mt$ABMT) ==="
docell(){ local name="$1" params="$2"; local pref="$W/ab_$name"; rm -f "${pref}".*
  local spa=(); [ -n "$params" ] && spa=(--search-params-a "$params")
  local pids=()
  for s in $(seq 0 $((NCPU-1))); do
    timeout "$SHARD_TIMEOUT" python3 tools/jass_vs_jass_arch.py \
      --jass-a "$J" --pattern-a "$W/gen2.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" "${spa[@]}" \
      --movetime "$ABMT" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 &
    pids+=($!)
  done
  wait "${pids[@]}"
  python3 - "$name" "$params" "$W/.doe" "$MIN_N" "${pref}".* <<'PY'
import sys,math
name,params,outp,min_n=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); a=d=b=0
for f in sys.argv[5:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b
if g < min_n:
    open(outp,'w').write(f"  [{name:8s} {params:44s}] n={g} < {min_n} => INCONCLUANT (shards culés/timeout — NE PAS lire comme neutre)\n"); sys.exit(0)
r=(a+0.5*d)/g; ex2=(a+0.25*d)/g; v=ex2-r*r
se=math.sqrt(v/g) if v>0 else 0.5/(g**0.5); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="A GAGNE hors-IC (convertit)" if lo>0.5 else ("A PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [{name:8s} {params:44s}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.doe" | tee -a "$RES"; rm -f "${pref}".* ; }
for cell in "${CELLS[@]}"; do
  name="${cell%%:*}"; params="${cell#*:}"
  docell "$name" "$params"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0697 DOE cellule $name : $(tail -1 "$RES")" >/dev/null 2>&1 || true
done
restore_src
say ""; say "  GATE : un knob rate_A>0.5 hors-IC => convertit éval→movetime => confirm haut-N (mt0.3+dilf) + baker search."
say "  baseline ~0.5 = sanity harnais ; INCONCLUANT (n<$MIN_N) ≠ neutre."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0697 FIN B3b DOE search : quel cut agressif convertit éval->movetime sur gen2-mmto" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin B3b DOE search ==="
