#!/usr/bin/env bash
# id: ccx33-0447-forcing-ab
# description: A/B du FIX search no_reduce_forcing (exempte de LMR/LMP les coups TRANCHANTS qui forcent une prise =
# sacrifices/combinaisons). 0446 a montré LMR+LMP cachent ~40% des combos ratées ; ce param les dé-réduit ciblé (preview
# local : +36/305 combos vues à d11, sans baisse notable). Ici on tranche par RÉSULTATS de parties :
#   (1) CONVERSION vs Scan depuis les 305 combinaisons (d11, no-DB) : baseline vs fix — la conversion 0.246 (0440) monte-t-elle ?
#   (2) A/B self-play À PROFONDEUR FIXE (d11) : jass(fix) vs jass(baseline), meme champion — le fix choisit-il de MEILLEURS
#       coups en jeu general (score>0.5) ou ça coûte ailleurs ? (3) coût NPS à movetime fixe (le fix ajoute un movegen par
#       coup tranquille tardif). Si conversion monte ET self-play >=0.5 => candidat à passer en défaut. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0447-forcing-ab/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-forcing-ab; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
FENS=data/dilf_combinations.fen
FIX="no_reduce_forcing=1"; D=11

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
[ -f "$FENS" ]     || { say "ABORT: positions absentes"; exit 4; }

say "=== build jass (avec le fix no_reduce_forcing, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

# --- helper : conversion camp-au-trait depuis un dump de parties (metrique 0440) ---
conv(){ python3 - "$1" "$FENS" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0].strip()
jw_w=jw_n=sw_w=sw_n=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    jatt=(jiw and s=="W") or ((not jiw) and s=="B")
    aw=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0)
    if jatt: jw_w+=aw; jw_n+=1
    else: sw_w+=aw; sw_n+=1
print(f"{jw_w/jw_n:.3f}" if jw_n else "NA")
PY
}

say ""; say "=== (1) CONVERSION combinaisons vs Scan (d${D}, no-DB) : baseline vs fix ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$FENS" --dump-games-dir "$ART/games-base" >"$W/cv-base.log" 2>&1 || say "  (conv base: voir log)"
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$FENS" --jass-search-params "$FIX" --dump-games-dir "$ART/games-fix" >"$W/cv-fix.log" 2>&1 || say "  (conv fix: voir log)"
CB=$(conv "$ART/games-base"); CF=$(conv "$ART/games-fix")
say "  conversion JASS-au-trait : baseline=${CB}   fix=${CF}   (reference 0440 = 0.246 ; Scan ~0.95)"

say ""; say "=== (2) A/B self-play a profondeur fixe d${D} : jass(fix) vs jass(baseline) ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$JASS" --pattern-a "$W/champ.pjtw" \
    --jass-b "$JASS" --pattern-b "$W/champ.pjtw" --search-params-a "$FIX" --depth "$D" --pairs 28 --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet >"$W/sp.$s" 2>&1 & done; wait
SP=$(python3 - "$W"/sp.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (A={a} D={d} B={b}, n={g})" if g else "NA")
PY
)
say "  jass(fix) vs jass(baseline) @d${D} : ${SP}   (>0.5 = le fix choisit de meilleurs coups)"

say ""; say "=== (3) cout NPS a movetime fixe (300ms) sur 20 combinaisons ==="
python3 - "$JASS" "$W/champ.pjtw" "$FENS" "$FIX" <<'PY' 2>&1 | tee -a "$RES"
import sys,re
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
JASS,CH,FENS,FIX=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
fens=[ln.split('#',1)[0].strip() for ln in open(FENS) if ln.split('#',1)[0].strip()][:20]
def avg_depth(sp):
    e=JassEngine(JASS, pattern_path=CH, no_book=True, search_params=(sp or None))
    tot=0; n=0
    for f in fens:
        e.set_position_fen(f); e._drain(); e._send("go movetime 300")
        L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=5)[-1]
        m=re.search(r"depth=(\d+)",L)
        if m: tot+=int(m.group(1)); n+=1
    e.close(); return tot/n if n else 0
db=avg_depth(""); df=avg_depth(FIX)
print(f"  profondeur moyenne atteinte @300ms : baseline={db:.1f}  fix={df:.1f}  (delta={df-db:+.1f} plies = cout vitesse)")
PY

say ""; say "================= LECTURE ================="
say "  conversion fix >> baseline  ET  self-play >= 0.5  => le fix gagne des combinaisons sans coûter ailleurs => PASSER EN DEFAUT."
say "  self-play < 0.5 ou conversion ~ baseline => le coût (NPS / instabilite) annule le gain => garder OFF / re-tuner."
say "=========================================="
