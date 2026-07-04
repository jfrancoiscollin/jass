#!/usr/bin/env bash
# id: ccx33-0565-threatext-play-oncoin
# description: RE-TEST qs_threat_ext AU JEU sur le nouveau defaut bake (coin corner+nmp, commit 4bda84da7) — plan JFC
# (co-adaptation). Historique : A/B 0554 => threat_ext ON coute -21 Elo au JEU a l'ancien defaut (gain fixe mange par
# le cout a temps egal). Hypothese : le coin corner+nmp a REDUIT l'EBF => plus de budget noeuds => threat_ext pourrait
# maintenant PAYER. Test : sur le defaut bake (coin actif des 2 cotes), A=qs_threat_ext=1 vs B=qs_threat_ext=0. movetime
# 0.3s, dilf, eval gen1, PAIRS=4 (~800 games). Capture BLINDEE (agrege prog LIVE, VERDICT atomique job-side).
# CRITERE : A borne basse IC>0.50 => threat_ext paie sur config reduite => confirmer defaut ON. Borne haute<0.50 =>
# coute encore => passer le defaut JEU a OFF. Parite => neutre, statu quo (ON). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0565-threatext-play-oncoin/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0565-threatext-play-oncoin/artefacts"
W=/root/cw-threatext; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen; MT=0.3; PAIRS=4; MAXPLIES=180
LOG="$W/run.log"; note(){ echo "$@" | tee -a "$LOG"; }

commit_to_main(){ local abspath="$1" relpath="$2" msg="$3"
  for a in 1 2 3 4 5; do
    git fetch origin main --quiet 2>/dev/null || true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"
    GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null || return 1
    local blob; blob=$(git hash-object -w "$abspath") || return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$blob" "$relpath"
    local tree; tree=$(GIT_INDEX_FILE="$idx" git write-tree)
    local commit; commit=$(printf '%s\n' "$msg" | git commit-tree "$tree" -p origin/main)
    if git push origin "$commit:main" 2>/dev/null; then rm -f "$idx"; return 0; fi
    sleep $((a*3))
  done; return 1; }

note "=== build jass depuis main (coin bake inclus) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { note "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { note "ABORT gen1"; exit 4; }
note "  confirme coin actif : $(git show origin/main:src/search_params.hpp | grep -cE 'probcut_min_depth = 5|eg_no_nmp  = false') /2 params-cle vus"
note "  A=qs_threat_ext=1  vs  B=qs_threat_ext=0  (coin des 2 cotes) ; mt${MT}s PAIRS=$PAIRS dilf eval gen1"

prog="$ART/prog"
for s in $(seq 0 $((NCPU-1))); do
  ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/gen1.pjtw" \
      --jass-b "$J" --pattern-b "$W/gen1.pjtw" --movetime "$MT" --pairs "$PAIRS" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
      --search-params-a "qs_threat_ext=1" --search-params-b "qs_threat_ext=0" \
      --progress-file "${prog}.$s" >"$W/o.$s" 2>&1; echo "$?" >"$W/rc.$s" ) &
done
note "  16 shards lances @ $(date -u +%H:%M:%S)Z"; wait; note "  finis @ $(date -u +%H:%M:%S)Z"

crash=0; mute=0; RAW="$ART/raw_shards.txt"; : > "$RAW"
for s in $(seq 0 $((NCPU-1))); do
  rc=$(cat "$W/rc.$s" 2>/dev/null || echo 99); [ "$rc" != "0" ] && crash=$((crash+1))
  grep -qiE 'traceback|segfault|core dumped|assert|abort' "$W/o.$s" 2>/dev/null && crash=$((crash+1))
  line=$(grep '^RESULT' "${prog}.$s" 2>/dev/null | tail -1); [ -z "$line" ] && mute=$((mute+1))
  echo "shard $s rc=$rc : ${line:-<muet>}" >> "$RAW"
done

VERD="$ART/VERDICT.txt"
python3 - "$prog" "$NCPU" "$crash" "$mute" "$MT" "$PAIRS" > "$VERD" <<'PY'
import sys,math
prog,nc,crash,mute,mt,pairs=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],sys.argv[6]
a=d=b=0; ns=0
for s in range(nc):
    try:
        last=[l for l in open(f"{prog}.{s}") if l.startswith("RESULT")][-1]
        _,x,y,z=last.split(); a+=int(x);d+=int(y);b+=int(z); ns+=1
    except: pass
g=a+d+b
print("=== VERDICT ccx33-0565 qs_threat_ext AU JEU sur le defaut BAKE (coin corner+nmp) ===")
print(f"A = qs_threat_ext=1  vs  B = qs_threat_ext=0   (coin des 2 cotes)")
print(f"config : movetime {mt}s ; PAIRS {pairs} ; dilf ; eval gen1")
print(f"shards : {ns}/{nc} avec RESULT ; crashs={crash} ; muets={mute}")
if not g: print("AUCUNE DONNEE"); sys.exit()
r=(a+0.5*d)/g; ex2=(a+0.25*d)/g; v=ex2-r*r
se=math.sqrt(v/g) if v>0 else 0.5/math.sqrt(g); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
if lo>0.5:   verd="threat_ext=1 PAIE hors-IC => CONFIRMER defaut ON (le coin a rentabilise threat_ext)"
elif hi<0.5: verd="threat_ext=1 COUTE hors-IC => passer le defaut JEU a OFF (qs_threat_ext=false)"
else:        verd="PARITE (IC contient 0.50) => neutre, statu quo (defaut reste ON, threat_ext utile en gen)"
print(f"games  : {g}  (A={a} wins  D={d} nulles  B={b})")
print(f"rate A : {r:.4f} +- {1.96*se:.4f}  elo {elo:+.0f}  IC [{lo:.4f}, {hi:.4f}]")
print(f"=> {verd}")
print("")
print("RAPPEL : A/B 0554 (ancien defaut, pre-coin) => threat_ext ON = -21 Elo au jeu. Ici on teste sur EBF reduit.")
PY
cat "$VERD"

commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0565 threat_ext@jeu sur coin : VERDICT job-side (capture blindee)" \
  && note "  VERDICT committe job-side ✓" || note "  ⚠ commit VERDICT echoue"
commit_to_main "$RAW"  "$ARTREL/raw_shards.txt" "0565 threat_ext : raw shards job-side" || true
note "=== fin 0565 ==="
