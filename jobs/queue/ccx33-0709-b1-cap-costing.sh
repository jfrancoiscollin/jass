#!/usr/bin/env bash
# id: ccx33-0709-b1-cap-costing
# description: CHIFFRAGE B1 (L3 bloquant 3, LE GATE AVANT INTÉGRATION) — l'arbitre-d14-au-cap remplace le label
# ply-cap menteur (~19% nulle par épuisement) par deep-relabel d14+egdb. Mémo : chiffrer le surcoût AVANT d'intégrer.
# Mesure : (1) cap_costing.py = self-play témoin gen2 d10 cap200 -> plycap_rate + coût/partie + JNNW des finales cappées ;
# (2) deep-relabel d14+egdb sur ces finales -> coût_d14/pos + TAUX DE DÉSACCORD vs nulle (= le mensonge corrigé, attendu
# élevé) ; (3) surcoût/tour = plycap_rate × coût_d14 ÷ coût/partie -> VERDICT vs seuil +25% (JFC). Si dépassé : d12 /
# arbitre ciblé |matériel| ambigu. Build egdb, dilf non requis. AUCUN NNUE. AUCUNE intégration ici (chiffrage seul).
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0709.lock
if ! flock -n 9; then echo "ABORT 0709 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0709-b1-cap-costing/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0709-b1-cap-costing/artefacts"
W=/root/cw-0709
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
GAMES=1500; DEPTH=10; MAXPLIES=200; ARB_DEPTH=14; NSH="$NCPU"; SHARD_TIMEOUT=6000; THRESHOLD_PCT=25

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import struct,glob,sys,re
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+"*")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
}

say "=== CHIFFRAGE B1 arbitre-d14-au-cap — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
git show "origin/$SRC_BRANCH:tools/cap_costing.py" > tools/cap_costing.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py tools/scan_selfplay_gen.py 2>/dev/null||true; rm -f tools/cap_costing.py; }
[ -s tools/cap_costing.py ] || { say "ABORT: cap_costing.py absent de $SRC_BRANCH"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/cap_costing.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0709 ABORT egdb"; exit 4; }

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0709 BUILD FAIL"; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' > "$W/open.fen"
say "  ✓ build egdb + gen2 ; egdb=$EGDIR ; games=$GAMES d$DEPTH cap$MAXPLIES"

# --- (1) témoin gen sharded -> plycap_rate + cout/partie + finales cappées ---
say ""; say "=== témoin self-play gen2 ($GAMES parties, $NSH shards) -> plycap_rate + coût/partie ==="
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/cap_costing.py --jass "$J" --pattern "$W/gen2.pjtw" \
    --openings-file "$W/open.fen" --games "$GAMES" --depth "$DEPTH" --max-plies "$MAXPLIES" \
    --shard "$s" --nshards "$NSH" --caps-out "$W/caps.$s.jnnw" --out "$W/cost.$s.json" \
    >"$W/cost.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
NCAPS=$(merge_jnnw "$W/caps.jnnw" "$W/caps.")
read NG NCAP PLYCAP SPG < <(python3 - "$W"/cost.*.json <<'PY'
import json,sys
ng=nc=0; sec=0.0
for f in sys.argv[1:]:
    try: j=json.load(open(f)); ng+=j["n_games"]; nc+=j["n_cap"]; sec+=j["play_sec"]
    except Exception: pass
plycap = nc/ng if ng else 0.0; spg = sec/ng if ng else 0.0
print(ng, nc, f"{plycap:.4f}", f"{spg:.4f}")
PY
)
say "  parties=$NG  cappées=$NCAP  plycap_rate=$PLYCAP  coût/partie=${SPG}s  (finales collectées=$NCAPS)"

# --- (2) arbitre d14+egdb sur les finales cappées : coût_d14 + désaccord vs nulle ---
DISAG="n/a"; COSTD14="n/a"
if [ "${NCAPS:-0}" -gt 0 ] 2>/dev/null; then
  say ""; say "=== deep-relabel d$ARB_DEPTH + egdb sur $NCAPS finales cappées (coût + désaccord vs nulle) ==="
  T0=$(date +%s.%N)
  "$J" --deep-relabel "$W/caps.jnnw" "$W/caps_rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/rel.log" 2>&1 || say "  (deep-relabel warn: $(tail -1 "$W/rel.log"))"
  T1=$(date +%s.%N)
  COSTD14=$(python3 -c "print(f'{($T1-$T0)/max($NCAPS,1):.4f}')")
  DISAG=$(python3 - "$W/caps_rel.jnnw" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]
nz=sum(1 for i in range(n) if struct.unpack_from('<b',b,8+i*38+37)[0]!=0)  # wdl != 0 = décisif (pas nulle)
print(f"{nz/max(n,1):.4f}")
PY
)
  say "  coût_d14/pos=${COSTD14}s  ;  DÉSACCORD (finale décisive ≠ nulle) = $DISAG  (= le mensonge ply-cap corrigé)"
fi

# --- (3) surcoût/tour + VERDICT vs seuil ---
say ""; say "=== VERDICT CHIFFRAGE B1 (surcoût ≤ +${THRESHOLD_PCT}% ?) ==="
python3 - "$PLYCAP" "$SPG" "$COSTD14" "$DISAG" "$THRESHOLD_PCT" <<'PY' | tee -a "$RES"
import sys
plycap=float(sys.argv[1]); spg=float(sys.argv[2])
costd14=sys.argv[3]; disag=sys.argv[4]; thr=float(sys.argv[5])
if spg<=0 or costd14=="n/a":
    print("  INCONCLUANT : coût/partie ou coût_d14 non mesuré — relancer"); sys.exit(0)
c14=float(costd14)
# surcoût/tour = (plycap_rate × coût_d14) / coût_par_partie  (chaque partie cappée ajoute 1 recherche d14)
overhead = plycap * c14 / spg
pct = 100*overhead
ok = pct <= thr
print(f"  plycap_rate={plycap:.4f}  coût/partie={spg:.3f}s  coût_d14/pos={c14:.3f}s")
print(f"  SURCOÛT/tour = plycap×coût_d14/coût_partie = {plycap:.4f}×{c14:.3f}/{spg:.3f} = {pct:.1f}%")
print(f"  désaccord (mensonge corrigé) = {disag}")
if ok:
    print(f"  => ADMIS ({pct:.1f}% ≤ {thr:.0f}%) : INTÉGRER l'arbitre-d14-au-cap (flag --cap-arbiter d14) à la gen L3.")
else:
    print(f"  => DÉPASSE ({pct:.1f}% > {thr:.0f}%) : fallback d12 OU arbitre ciblé |matériel| ambigu (les gains nets clairs -> adjud matérielle, moins chère). Re-chiffrer.")
PY
cp "$W/caps.jnnw" "$ART/cap_finals.jnnw" 2>/dev/null || true
commit_to_main "$ART/cap_finals.jnnw" "$ARTREL/cap_finals.jnnw" "0709 finales cappées (chiffrage)" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0709 FIN chiffrage B1 : plycap=$PLYCAP coutd14=$COSTD14 desaccord=$DISAG" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0709 FINI ==="
rm -rf "$W"
