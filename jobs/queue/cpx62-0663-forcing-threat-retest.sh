#!/usr/bin/env bash
# id: cpx62-0663-forcing-threat-retest
# description: RE-TEST forcing/threat extensions (demande JFC) AVEC les dernières optimisations. Ces extensions étaient
# neutres/non-retenues quand (a) elles coûtaient une GÉNÉRATION COMPLÈTE par test forcing, (b) le search était plus lent.
# Maintenant : develop a `has_any_capture` (prédicat cheap au lieu de gen-complète) + eval +13-15% NPS byte-identique. Leur
# coût/bénéfice a changé → re-test au MOVETIME (là où le budget de nœuds décide). Build DEVELOP (has_any_capture + opts).
# A/B : gen2-mmto + config-extension (A) vs gen2-mmto défaut (B), MÊME éval, mt0.2 généraliste ≥38p. GATE : une config
# >0.5 hors-IC => l'extension paie enfin (confirm mt0.3 + dilf + bake search). Harnais durci + timeout x5. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0663-forcing-threat-retest/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0663-forcing-threat-retest/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-forcing-retest; rm -rf "$W"; mkdir -p "$W"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
NOPEN=96; PAIRS=8; ABMT=0.2
# cellules (nom:params) — OAT + combos des extensions forcing/threat (le baseline = sanity ~0.5)
CELLS=(
  "baseline:"
  "ext_forcing:ext_forcing=1"
  "no_reduce:no_reduce_forcing=1"
  "extf_nored:ext_forcing=1,no_reduce_forcing=1"
  "qs_forcing:qs_forcing_depth=4"
  "qs_threat:qs_threat_ext=1"
  "combo:ext_forcing=1,qs_forcing_depth=4,qs_threat_ext=1"
)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== RE-TEST forcing/threat ext (build develop = has_any_capture + opts NPS) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/search.cpp src/movegen.cpp src/movegen.hpp src/scan_eval.cpp src/scan_eval.hpp tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src/main.cpp src/search.cpp src/movegen.cpp src/movegen.hpp src/scan_eval.cpp src/scan_eval.hpp tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
grep -q "has_any_capture" src/search.cpp && say "  develop = has_any_capture ✓" || { say "ABORT: develop sans has_any_capture"; restore_src; exit 4; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0663 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
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
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG"; [ "$NG" -gt 20 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 7; }

say ""; say "=== A/B extension (A) vs gen2-mmto défaut (B), même éval, mt$ABMT généraliste ==="
docell(){ local name="$1" params="$2"; local pref="$W/ab_$name"; rm -f "${pref}".*
  local spa=(); [ -n "$params" ] && spa=(--search-params-a "$params")
  for s in $(seq 0 $((NCPU-1))); do timeout 3000 python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen2.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" "${spa[@]}" \
    --movetime "$ABMT" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$name" "$params" "$W/.c" "${pref}".* <<'PY'
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
vd="AJOUTE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [{name:12s} {params:44s}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.c" | tee -a "$RES"; }
for cell in "${CELLS[@]}"; do name="${cell%%:*}"; params="${cell#*:}"; docell "$name" "$params"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0663 cellule $name" >/dev/null 2>&1 || true; done
restore_src
say ""; say "  GATE : une extension rate_A>0.5 hors-IC => elle paie avec has_any_capture + eval rapide (là où elle était neutre avant)"
say "  => confirm mt0.3 + dilf + bake search. Neutre partout => les extensions ne composent toujours pas, même moins chères."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0663 FIN re-test forcing/threat : payent-elles avec les dernières optims" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin re-test forcing/threat ==="
