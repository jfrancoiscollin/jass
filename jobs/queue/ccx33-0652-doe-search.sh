#!/usr/bin/env bash
# id: ccx33-0652-doe-search
# description: DOE SEARCH sur gen2-mmto (mémo JFC, piste // de la chaîne cpx62). Hypothèse : une MEILLEURE éval (gen2-mmto,
# d9 +34/+46 vs Scan) TOLÈRE une recherche plus AGRESSIVE (élaguer/réduire davantage en faisant confiance à l'éval →
# chercher plus PROFOND à temps fixe → convertir le gain éval-par-nœud en force MOVETIME). OAT : chaque cellule = gen2-mmto
# + UN knob search modifié (side A) vs gen2-mmto search DÉFAUT (side B), MÊME éval, mt0.2 généraliste ≥38p. UN SEUL build
# (les knobs sont runtime via --search-params-a). GATE : rate_A>0.5 hors-IC => ce knob convertit éval→movetime => confirm
# (mt0.3 + dilf) + baker le search. Sanity : cellule défaut-vs-défaut ≈ 0.5. ⚠️ bug go-movetime overshoot endgame (harnais
# catch timeout→nulle). Elo-first. AUCUN NNUE. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0652-doe-search/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0652-doe-search/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-doe-search; rm -rf "$W"; mkdir -p "$W"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
NOPEN=96; PAIRS=8; ABMT=0.2
# DOE OAT (nom:params) — direction AGRESSIVE (l'éval meilleure absorbe plus d'élagage) + sanity
CELLS=(
  "baseline:"                    # défaut vs défaut (sanity ~0.5)
  "lmr_ddiv4:lmr_depth_div=4"    # plus de LMR avec la profondeur (défaut 6)
  "lmr_log:lmr_formula=1"        # LMR logarithmique (Stockfish-like) vs linéaire
  "nmp_r3:nmp_r_base=3"          # NMP plus agressif (R base 2->3)
  "probcut5:probcut_min_depth=5" # ProbCut ON (défaut off)
  "lmp6:lmp_max_depth=6"         # LMP plus profond (défaut 3)
  "asp30:aspiration_initial=30"  # fenêtre aspiration plus serrée (défaut 50)
  "rfp7:rfp_max_depth=7"         # RFP jusqu'à d7 (défaut 5)
)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== DOE SEARCH gen2-mmto (OAT knobs, mt$ABMT généraliste) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
restore_src(){ git checkout -- src/main.cpp tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
# build avec RETRY (0649 a échoué -j4 alors que 0645 -j8 a marché => transient) + commit de la VRAIE erreur au 2e échec
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
build_ok=0
for attempt in 1 2; do
  if cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.$attempt.log" 2>&1; then build_ok=1; break; fi
  say "  build tentative $attempt échouée, retry..."
done
if [ "$build_ok" != 1 ]; then
  say "BUILD FAIL (2 tentatives). Vraie erreur :"; grep -iE "error:|Error [0-9]|fatal" "$W/build.2.log" | head -15 | sed 's/^/  /' | tee -a "$RES"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0652 BUILD FAIL (erreur committée)"; restore_src; exit 6
fi
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
say "  ✓ build+gen2 (NCPU=$NCPU)"

# openings généralistes ≥38p
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
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG"; [ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 7; }

# ---- OAT : chaque knob (side A) vs défaut (side B), même éval gen2-mmto ----
say ""; say "=== OAT DOE search (side A = gen2-mmto+knob vs side B = gen2-mmto défaut, mt$ABMT) ==="
docell(){ local name="$1" params="$2"; local pref="$W/ab_$name"; rm -f "${pref}".*
  local spa=(); [ -n "$params" ] && spa=(--search-params-a "$params")
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen2.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" "${spa[@]}" \
    --movetime "$ABMT" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$name" "$params" "$W/.doe" "${pref}".* <<'PY'
import sys,math
name,params,outp=sys.argv[1],sys.argv[2],sys.argv[3]; a=d=b=0
for f in sys.argv[4:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [{name:10s} {params:24s}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.doe" | tee -a "$RES"; rm -f "${pref}".* ; }
for cell in "${CELLS[@]}"; do
  name="${cell%%:*}"; params="${cell#*:}"
  docell "$name" "$params"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0652 DOE cellule $name" >/dev/null 2>&1 || true
done
restore_src
say ""; say "  GATE : un knob rate_A>0.5 hors-IC => il convertit le gain éval-par-nœud en force MOVETIME => confirm mt0.3+dilf + baker search."
say "  (baseline doit être ~0.5 : sanity harnais symétrique.) Neutre partout => la marge movetime n'est pas dans ces knobs (OAT étendre / combos)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0652 FIN DOE search : quel knob convertit éval->movetime sur gen2-mmto" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin DOE search ==="
