#!/usr/bin/env bash
# id: cpx62-0542-post-bake-sweep
# description: SWEEP post-bake qs_sacs. Les leviers de recherche (razor/rfp/multicut/LMR/extensions) ont ete calibres
# sur une quiescence AVEUGLE aux combos ; maintenant que la quiescence VOIT les sacs (qs_sacs baké ON), certains
# reglages sont peut-etre sous-optimaux. Chaque bras = une variation vs BASELINE(defaut baké) en head-to-head jass-vs-jass
# a movetime, dilf combos, meme eval champion egdbmix. On classe par score-rate (>0.50 = le bras ameliore la config bakée).
# Les gagnants alimentent la config de la passe self-play suivante. Judge combo-oriente (dilf) ; la force generale sera
# validee par le test vs-champion apres self-play. AUCUN NNUE. expected_duration: ~3-5 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0542-post-bake-sweep/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
RANK="$ART/RANKING.txt"; : > "$RANK"
W=/root/cw-postbake; rm -rf "$W"; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; MT=0.25; PAIRS=1; MAXPLIES=180

say "=== build jass depuis main (qs_sacs BAKED ON) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$EGDBMIX" | gunzip > "$W/champ.pjtw" || { say "ABORT champ egdbmix absent"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"

# ---- bras du sweep : name|spec (B = baseline vide = defaut baké) ----
# Priorite : (1) les 2 gates internes de qs_sacs, (2) le pruning qui court-circuite la quiescence
#            (razor/rfp/probcut), (3) multicut, (4) extensions forçantes, (5) forcing-qs par-dessus les sacs.
ARMS=(
  "sac_recurse|qs_sacs_depth0_only=0"
  "threat_ext|qs_threat_ext=1"
  "threat+recurse|qs_threat_ext=1,qs_sacs_depth0_only=0"
  "razor_off|razor_max_depth=0"
  "razor_deep|razor_max_depth=6"
  "rfp_loose|rfp_margin=140"
  "rfp_shallow|rfp_max_depth=3"
  "rfp_off|rfp_max_depth=0"
  "noreduce_forcing|no_reduce_forcing=1"
  "single_reply|ext_single_reply=1"
  "ext_forcing|ext_forcing=1,forcing_ext_cap=6"
  "forcing_qs2|qs_forcing_depth=2"
  "mc_deep|multicut_min_depth=8"
  "probcut_on|probcut_min_depth=5"
)

run_arm(){ local name="$1" spec="$2"
  local prog="$ART/prog_${name}"
  say ""
  say "=== BRAS ${name}  (A=$spec  vs  B=baseline baké)  @ mt${MT}s dilf ==="
  for s in $(seq 0 $((NCPU-1))); do
    ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/champ.pjtw" \
         --jass-b "$J" --pattern-b "$W/champ.pjtw" --movetime "$MT" --pairs "$PAIRS" \
         --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
         --search-params-a "$spec" --search-params-b "" \
         --progress-file "${prog}.$s" >"$W/o_${name}.$s" 2>"$W/e_${name}.$s"; echo "DONE $s" ) &
  done
  wait
  python3 - "$prog" "$NCPU" "$name" "$spec" "$RANK" <<'PY' 2>&1 | tee -a "$RES"
import sys, math
prog,nc,name,spec,rankf = sys.argv[1],int(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5]
A=B=D=0
for s in range(nc):
    try:
        last=[l for l in open(f"{prog}.{s}") if l.startswith("RESULT")][-1]
        _,a,d,b=last.split(); A+=int(a);D+=int(d);B+=int(b)
    except Exception: pass
g=A+B+D; rate=(A+0.5*D)/g if g else 0.0
se=(0.5/(g**0.5)) if g else 1.0
elo=(-400*math.log10(1.0/rate-1.0)) if 0.0<rate<1.0 else 0.0
print(f"  {name:16s} games={g:4d}  A={A:4d} B={B:4d} D={D:4d}  rate={rate:.3f}+-{1.96*se:.3f}  elo~{elo:+.0f}")
open(rankf,"a").write(f"{rate:.4f}\t{1.96*se:.4f}\t{elo:+.0f}\t{name}\t{spec}\n")
PY
}

say ""
say "############ SWEEP post-bake : ${#ARMS[@]} bras vs baseline baké, mt${MT}s, dilf n=305 ############"
for e in "${ARMS[@]}"; do run_arm "${e%%|*}" "${e#*|}"; done

say ""
say "############ CLASSEMENT (score-rate decroissant ; >0.50 hors-IC = ameliore le baké) ############"
sort -rn "$RANK" | awk -F'\t' '{printf "  %6.3f +-%.3f  elo~%s  %-16s  %s\n",$1,$2,$3,$4,$5}' | tee -a "$RES"
say "=== fin sweep post-bake ==="
