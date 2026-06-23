#!/usr/bin/env bash
# id: ccx33-0435-scan-handicap-ladder
# description: EVAL PUR vs Scan (no-DB des 2 cotes, jass SANS egdb) — ECHELLE DE HANDICAP + ANALYSE DES PARTIES.
# But (JFC) : (1) comprendre OU/POURQUOI on perd (les parties), (2) "a combien de plies on est derriere Scan" =
# jass-depth in {11,13,15} vs Scan depth 11, on cherche ou jass croise 0.5. Dump des parties (JSON) + breakdown
# (issues, longueurs, defaites par BLOCAGE 'no legal move'=zugzwang, nb pieces a la perte = phase). 18 parties
# distinctes/rung (deterministe a depth fixe). ⚠️ petit echantillon + hors-plateau = ordre de grandeur / diagnostic.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0435-scan-handicap-ladder/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-ladder; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
DEPTHS="11 13 15"; SCAN_D=11; PAIRS=1   # pairs 1 = 18 parties distinctes (repeter = identique, deterministe)

# ---------- probe + build jass SANS egdb (eval+search pur) ----------
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 4; }
say "=== build jass (32-pat, extras du champion, SANS egdb = eval pur) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion 3e-5 absent"; exit 4; }
unset JASS_EGDB_PATH   # eval PUR, aucun DB finale
DUMP="$ART/games"; mkdir -p "$DUMP"

# ---------- echelle de handicap ----------
say "=== ECHELLE DE HANDICAP (jass-depth vs Scan d${SCAN_D}, no-DB, champion 3e-5) ==="
for JD in $DEPTHS; do
  echo "  [rung] jass d${JD} vs Scan d${SCAN_D} ..."
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --scan-bb-size 0 --jass-depth "$JD" --scan-depth "$SCAN_D" --pairs "$PAIRS" \
      --dump-games-dir "$DUMP/d${JD}" >"$W/m${JD}.log" 2>&1 || { say "  (rung d${JD} a echoue, voir m${JD}.log)"; tail -4 "$W/m${JD}.log"|sed 's/^/    /'|tee -a "$RES"; continue; }
  SC=$(grep -oiE "score rate:?\s*[0-9.]+" "$W/m${JD}.log" | tail -1)
  WDL=$(grep -oiE "Jass=[0-9]+\s+Scan=[0-9]+\s+Draws=[0-9]+" "$W/m${JD}.log" | tail -1)
  say "  jass d${JD} vs Scan d${SCAN_D} : ${SC}   [${WDL}]"
done
say "# LECTURE LADDER : ou jass croise ~0.5 = la profondeur qui compense l'eval -> (jass_d - ${SCAN_D}) plies derriere."
say "#   si jass reste ~0 meme a d15 => ecart EVAL fondamental (la profondeur ne rattrape pas -> territoire NNUE)."

# ---------- analyse des parties (toutes les parties dumpees) ----------
say ""
say "=== ANALYSE : ou/pourquoi on perd ==="
python3 - "$DUMP" <<'PY' 2>&1 | tee -a "$RES" || say "(analyse: voir games/)"
import json,glob,os,sys
root=sys.argv[1]
def pc(fen):
    # FEN jass "W:Wxx..:Bxx.." -> compte pieces (approx via nb de cases listees)
    try:
        n=0
        for part in fen.split(":")[1:]:
            body=part[1:] if part[:1] in "WB" else part
            n+=len([x for x in body.split(",") if x])
        return n
    except: return -1
for d in sorted(glob.glob(os.path.join(root,"d*"))):
    games=[json.load(open(f)) for f in glob.glob(os.path.join(d,"*.json"))]
    if not games: continue
    n=len(games); res={}; nomove=0; plies=[]; lost_pc=[]
    for g in games:
        r=g.get("result") or g.get("outcome") or "?"; res[r]=res.get(r,0)+1
        rs=str(g.get("reason",""));
        if "no legal move" in rs.lower(): nomove+=1
        p=g.get("plies") or len(g.get("moves",[])); plies.append(p)
        # phase a la perte : nb pieces dans la derniere FEN
        fl=g.get("fens") or g.get("fens_log") or []
        if fl: lost_pc.append(pc(fl[-1]))
    import statistics as st
    print(f"  [{os.path.basename(d)}] {n} parties | issues {res} | blocage(no-move) {nomove}/{n} | "
          f"plies med {int(st.median(plies)) if plies else '?'} | pieces fin med {int(st.median([x for x in lost_pc if x>=0])) if any(x>=0 for x in lost_pc) else '?'}")
PY
say "# (JSON par partie dans artefacts/games/ pour analyse plus fine ulterieure)"
