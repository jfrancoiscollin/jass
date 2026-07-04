#!/usr/bin/env bash
# id: cpx62-0570-rejudge-regen
# description: RE-JUGE le champion-regen (0568) vs gen1 — le fit a REUSSI (champion committe job-side 13:42) mais le
# verdict du juge a ete PERDU (0568 ne blindait pas le RESULTS => bug capture runner). On rejoue le juge, BLINDE cette
# fois. Build moteur COIN (defaut : corner+nmp + threat_ext), candidat ET gen1 dans le MEME build => mesure PURE de
# l'eval. d9, dilf, ~2440 games, SE ajustee nulles. GATE : regen-vs-gen1 borne basse IC>0.50 => COMPOSE => la boucle
# vertueuse a rouvert le plateau => promo. Sinon => plateau = capacite. VERDICT job-side. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0570-rejudge-regen/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0570-rejudge-regen/artefacts"
VERD="$ART/VERDICT.txt"; : > "$VERD"; say(){ echo "$@" | tee -a "$VERD"; }
W=/root/cw-rejudge; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CAND_GZ=jobs/results/cpx62-0568-fit-regen-oncoin/artefacts/champion-regen.pjtw.gz
EGDBMIX_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; JUDGE_DEPTH=9; JUDGE_PAIRS=4

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== RE-JUGE champion-regen vs gen1 (moteur COIN par defaut) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CAND_GZ" | gunzip > "$W/cand.pjtw" || { say "ABORT cand-regen"; exit 4; }
git show "origin/main:$EGDBMIX_GZ" | gunzip > "$W/egdbmix.pjtw" 2>/dev/null || : > "$W/egdbmix.pjtw"
say "  confirme coin : $(git show origin/main:src/search_params.hpp | grep -cE 'probcut_min_depth = 5|eg_no_nmp  = false|qs_threat_ext = true')/3 params-cle ; juge d${JUDGE_DEPTH} dilf x${JUDGE_PAIRS}"

pjudge(){ local np="$1" rp="$2" tag="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$np" \
    --jass-b "$J" --pattern-b "$rp" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" \
    --quiet --openings-file "$DILF" >"$W/j_${tag}.$s" 2>&1 & done; wait
  python3 - "$tag" "$W"/j_${tag}.* <<'PY'
import sys,math; tag=sys.argv[1]; a=d=b=0
for f in sys.argv[2:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
verd='COMPOSE (borne basse>0.50)' if lo>0.50 else ('REGRESSE (borne haute<0.50)' if hi<0.50 else 'NEUTRE (IC contient 0.50)')
print(f"  [{tag}] games={g} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  IC=[{lo:.4f},{hi:.4f}]  => {verd}")
PY
}
say ""; say "=== JUGE (moteur COIN par defaut, meme build des 2 cotes) ==="
pjudge "$W/cand.pjtw" "$W/gen1.pjtw" "regen-vs-gen1" | tee -a "$VERD"
[ -s "$W/egdbmix.pjtw" ] && pjudge "$W/cand.pjtw" "$W/egdbmix.pjtw" "regen-vs-egdbmix" | tee -a "$VERD"
say ""
say "  => regen-vs-gen1 COMPOSE => la boucle vertueuse a rouvert le plateau => promo cand-regen (nouveau champion EVAL)."
say "  => NEUTRE/REGRESSE => meme un meilleur pilote ne compose pas => plateau = CAPACITE (cf DOE 0569)."
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0570 re-juge regen vs gen1 : VERDICT job-side (blinde)" \
  && say "  VERDICT committe job-side ✓" || say "  ⚠ commit VERDICT echoue"
say "=== fin re-juge regen ==="
