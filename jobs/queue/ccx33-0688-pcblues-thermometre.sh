#!/usr/bin/env bash
# id: ccx33-0688-pcblues-thermometre
# description: THERMOMETRE PC BLUES (go JFC 2026-07-12). Photo tactique de reference du champion gen2-mmto sur les 224
# positions FIGEES pcblues-thermo-v1 (combinaisons certifiees-jouees BK/NL, verifiees par re-jeu FMJD cote dilf, dedup
# croisee vs master-2000/0464 : matiere neuve). Harnais 0440 : match vs Scan depuis chaque position (d11, pairs=1),
# ANALYSE = conversion du camp AU TRAIT (qui a la combinaison). Sert aussi d'instrument recurrent pour la lignee
# from-scratch (JAMAIS entrainement). PRE-ESTIMATION (ancre 0440 : 305 pos d11 < 4h ccx33) : 224 pos => ~2-3h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0688-pcblues-thermometre/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0688-pcblues-thermometre/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-pcbthermo; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
D=11; PAIRS=1

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0688 ABORT scan absent"; exit 4; }
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
git show "origin/$SRC_BRANCH:data/pcblues_thermometre.fen" > "$W/thermo.fen" \
  || { say "ABORT: thermometre absent de origin/$SRC_BRANCH"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0688 ABORT thermo absent"; exit 4; }
NPOS=$(grep -cvE '^\s*(#|$)' "$W/thermo.fen"); say "# thermometre pcblues-thermo-v1 : ${NPOS} positions figees"

say "=== build jass (main, 32-pat extras champion, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT: champion gen2-mmto absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== match gen2-mmto vs Scan depuis ${NPOS} positions (depth ${D}, no-DB, timeout 4h) ==="
timeout 14400 python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --scan-bb-size 0 --depth "$D" --pairs "$PAIRS" --openings-file "$W/thermo.fen" \
    --dump-games-dir "$ART/games" >"$W/match.log" 2>&1 || say "  (match interrompu/timeout — on analyse ce qui est dumpe)"
tail -6 "$W/match.log" | sed 's/^/    /' | tee -a "$RES"

say ""
say "=== ANALYSE : conversion du camp AU TRAIT (qui a la combinaison) — harnais 0440 ==="
python3 - "$ART/games" "$W/thermo.fen" <<'PY' | tee -a "$RES"
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm[b]=b.split(':',1)[0].strip()
ja_w=ja_n=0; sc_w=sc_n=0; tot=0; nolegal=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except Exception: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    tot+=1
    jw=g.get("jass_is_white"); out=g.get("outcome")
    if g.get("reason","")=="no-legal-move" and g.get("plies",1)<=1: nolegal+=1
    jass_is_attacker = (jw and s=="W") or ((not jw) and s=="B")
    if out=="D": att_win=0.5
    elif (out=="W" and s=="W") or (out=="L" and s=="B"): att_win=1.0
    else: att_win=0.0
    if jass_is_attacker: ja_w+=att_win; ja_n+=1
    else:                sc_w+=att_win; sc_n+=1
def pct(w,n): return f"{w/n:.3f} ({w:.1f}/{n})" if n else "n/a"
print(f"  parties analysees      : {tot}  (positions sans coup legal au depart : {nolegal})")
print(f"  JASS au trait (convertit la combinaison) : {pct(ja_w,ja_n)}")
print(f"  SCAN au trait (convertit la combinaison) : {pct(sc_w,sc_n)}")
if ja_n and sc_n:
    d=ja_w/ja_n - sc_w/sc_n
    print(f"  ECART jass - scan : {d:+.3f}  => {'jass convertit MIEUX' if d>0.02 else ('parite' if abs(d)<=0.02 else 'jass convertit MOINS = trou tactique')}")
PY

say ""
say "================= LECTURE ================="
say "  Ce run = T0 du thermometre PC Blues (gen2-mmto). Re-passer le MEME set fige sur chaque"
say "  champion from-scratch (T2, T3...) => courbe de conversion tactique SANS contamination"
say "  (les positions ne servent jamais a l'entrainement)."
say "==========================================="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0688 thermometre PC Blues T0 (gen2-mmto vs Scan, 224 pos figees d$D)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin 0688 ==="
