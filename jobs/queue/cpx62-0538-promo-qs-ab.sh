#!/usr/bin/env bash
# id: cpx62-0538-promo-qs-ab
# NB: A/B QUIESCENCE DE PROMOTION (PR #328) — base vs forcing vs forcing+promo1/2, detection/tempi + 0440 + noeuds.
# description: A/B de la QUIESCENCE FORÇANTE (PR #327, qs_forcing_depth). Décideur : trouver les sacs au horizon aide-t-il
# à TEMPS RÉEL, net du coût-nœuds ? (1) DÉTECTION par tempi sur la suite gradée 0534 (move-match fiable) : baseline qs=0 vs
# qs=2 vs qs=3, à movetime 3s ET fixe d12. (2) CONVERSION 0440 vs Scan : baseline vs qs=2. (3) COÛT-NŒUDS : search-profile
# OFF vs ON (ratio). LECTURE : détection ↑ par tempi + 0440 ↑ à coût-nœuds raisonnable => baker + relancer la boucle. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0538-promo-qs-ab/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-fqab; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SUITE_SRC="jobs/results/cpx62-0534-combo-gen-balanced/artefacts/combos_balanced.fen"
DILF=data/dilf_combinations.fen; D=11; MT=3.0; DFIX=12; SUBN=40

say "=== A/B quiescence forçante (qs_forcing_depth) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 \
    || { say "ABORT cmake"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ"; exit 4; }
git show "origin/main:$SUITE_SRC" > "$W/suite.fen" 2>/dev/null || { say "ABORT suite 0534"; exit 4; }

say "=== (1) DÉTECTION par tempi (move-match, baseline vs qs=2 vs qs=3) ==="
export JASS="$J" CHAMP="$W/champ.pjtw" SUITE="$W/suite.fen" MT="$MT" DFIX="$DFIX" SUBN="$SUBN" TABLE="$ART/detection.txt"
set +e
python3 - <<'PY' 2>&1 | tee -a "$RES"
import os,sys,re,collections
sys.path.insert(0,'tools'); from calibrate_vs_scan import JassEngine
J=os.environ["JASS"]; CH=os.environ["CHAMP"]; SUITE=os.environ["SUITE"]; MT=float(os.environ["MT"])
DFIX=int(os.environ["DFIX"]); SUBN=int(os.environ["SUBN"]); TABLE=os.environ["TABLE"]
byt=collections.defaultdict(list)
for ln in open(SUITE):
    if '#' not in ln: continue
    fen,meta=ln.split('#',1); fen=fen.strip(); m=dict(re.findall(r'(\w+)=([^\s]+)',meta))
    if 'tempi' in m and m.get('win'): byt[int(m['tempi'])].append((fen,m['win']))
combos=[]
for t in sorted(byt): combos += [(f,t,w) for f,w in byt[t][:SUBN]]
print(f"  {len(combos)} combos (≤{SUBN}/bin)", flush=True)
CFG={'base':'', 'f3':'qs_forcing_depth=3', 'f3p1':'qs_forcing_depth=3,qs_promo_depth=1', 'f3p2':'qs_forcing_depth=3,qs_promo_depth=2'}
def rate(cb, cfg, movetime=None, depth=None):
    if not cb: return None
    eng=JassEngine(J,pattern_path=CH,no_book=True,search_params=cfg) if cfg else JassEngine(J,pattern_path=CH,no_book=True)
    hit=0
    for fen,t,win in cb:
        try:
            eng.set_position_fen(fen); mv=eng.go(depth=depth, movetime=movetime)
            if mv is not None and mv.jass_str()==win: hit+=1
        except Exception: pass
    eng.close(); return hit/len(cb)
def f(x): return "n/a" if x is None else f"{x:.2f}"
hdr=f"  {'tempi':>5} {'n':>3} | mt3s: {'base':>5} {'f3':>5} {'f3p1':>5} {'f3p2':>5}"
lines=[hdr]; tot={k:[0,0] for k in CFG}
for t in sorted(byt):
    cb=[c for c in combos if c[1]==t]
    if not cb: continue
    r={k:rate(cb,v,movetime=MT) for k,v in CFG.items()}
    lines.append(f"  {t:>5} {len(cb):>3} | mt3s: {f(r['base']):>5} {f(r['f3']):>5} {f(r['f3p1']):>5} {f(r['f3p2']):>5}")
open(TABLE,'w').write("\n".join(lines)+"\n"); print("\n".join(lines), flush=True)
PY
PYRC=${PIPESTATUS[0]}; set -e
[ "$PYRC" = 0 ] && [ -s "$ART/detection.txt" ] || { say "ABORT: détection échouée (PYRC=$PYRC)"; exit 8; }

say ""
say "=== (2) CONVERSION 0440 vs Scan (baseline vs qs=2, d${D}) ==="
for cfg in "qs_forcing_depth=0:base" "qs_forcing_depth=3,qs_promo_depth=1:fp1"; do
  spec="${cfg%%:*}"; lbl="${cfg##*:}"
  ( unset JASS_EGDB_PATH; timeout 9000 python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --jass-search-params "$spec" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" \
      --dump-games-dir "$ART/conv-$lbl" >"$W/cv-$lbl.log" 2>&1 ) || say "  (0440 $lbl interrompu)"
  python3 - "$ART/conv-$lbl" "$DILF" "$lbl" <<'PY' | tee -a "$RES"
import json,glob,sys,os
gdir,fens,lbl=sys.argv[1],sys.argv[2],sys.argv[3]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=an=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    aw+=1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else (0.5 if out=="D" else 0.0); an+=1
print(f"  0440 {lbl} : JASS-au-trait={aw/an:.3f} (n={an})" if an else f"  0440 {lbl}: n/a")
PY
done

say ""
say "=== (3) COÛT-NŒUDS (search-profile fixe d10, OFF vs ON sur 5 combos) ==="
head -5 "$W/suite.fen" | grep -vE '^\s*#' | while IFS= read -r line; do
  fen="${line%%#*}"; fen="$(echo "$fen"|xargs)"
  n0=$("$J" --search-profile "$fen" 10 0 "$W/champ.pjtw" "qs_forcing_depth=0" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1 | cut -d= -f2)
  n2=$("$J" --search-profile "$fen" 10 0 "$W/champ.pjtw" "qs_forcing_depth=2" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1 | cut -d= -f2)
  say "  nodes OFF=${n0:-?} ON=${n2:-?}  ratio=$(python3 -c "print(f'{${n2:-0}/max(${n0:-1},1):.2f}')" 2>/dev/null||echo ?)"
done

say ""
say "================= LECTURE ================="
say "  détection ↑ par tempi (qs2/qs3 > qs0) à mt3s + 0440 ↑ (qsF > base) à ratio-nœuds raisonnable => BAKER + relancer la boucle."
say "  détection ↑ mais 0440 ~ / coût-nœuds explose => l'extra-qsearch mange la profondeur => tuner qs_forcing_depth / cap."
say "  rien ne bouge à movetime => comme ext_forcing, gain de profondeur-fixe non transférable => clore."
say "==========================================="
