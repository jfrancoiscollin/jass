#!/usr/bin/env bash
# id: cpx62-0539-qs-sacs-ab
# description: A/B DÉCISIF de la sac-quiescence SÉLECTIVE de Scan (add_sacs porté + validé bit-à-bit ; branche
# claude/scan-sac-quiescence). Le make-or-break du briefing : COMBOS↑ (0440) SANS EXPLOSION (node-EBF exact). Bras :
# base / qs_sacs / qs_sacs+qs_threat_ext. (1) 0440 conversion vs Scan (d11, eval-pur no-DB) — les combos montent-ils vers
# 0,95 ? (2) node-EBF EXACT (search-profile, ratio base vs ON) — l'arbre explose-t-il ? Les DEUX obligatoires. Build depuis
# la BRANCHE (pas main). AUCUN NNUE. expected_duration: ~2-4 h.
set -uo pipefail
ART="/root/jass/jobs/results/cpx62-0539-qs-sacs-ab/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; D=11

say "=== A/B sac-quiescence sélective (build depuis branche claude/scan-sac-quiescence) ==="
W=/root/jass-sacbranch; rm -rf "$W"
git clone /root/jass "$W" >/tmp/clone.log 2>&1 || { say "ABORT clone"; exit 4; }
cd "$W"
git fetch origin claude/scan-sac-quiescence >/tmp/fetch.log 2>&1 || { say "ABORT fetch branch"; exit 4; }
git checkout -B sacbranch FETCH_HEAD >/tmp/co.log 2>&1 || { say "ABORT checkout"; exit 4; }
say "  HEAD branche : $(git log --oneline -1 | cat)"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >/tmp/cm.log 2>&1
cmake --build build -j"$NCPU" --target jass >/tmp/bldjob.log 2>&1 || { say "BUILD FAIL"; tail -12 /tmp/bldjob.log|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >/tmp/sc.log 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ"; exit 4; }
cd /root/jass

say ""
say "=== (1) FIDÉLITÉ add_sacs (rappel : port validé) — sanity dump sur 3 positions ==="
head -3 "$W/$DILF" 2>/dev/null | grep -vE '^\s*#' | sed 's/#.*//' | "$J" --dump-sacs 2>/dev/null | sed 's/^/  /' | tee -a "$RES"

say ""
say "=== (2) node-EBF EXACT (search-profile d13, ratio base vs ON) — EXPLOSION ? ==="
python3 - "$J" "$W/champ.pjtw" "$W/$DILF" <<'PY' 2>&1 | tee -a "$RES"
import sys,subprocess,statistics
J,CH,DILF=sys.argv[1],sys.argv[2],sys.argv[3]
fens=[l.split('#')[0].strip() for l in open(DILF) if l.strip() and not l.startswith('#')][:60]
def nodes(fen,spec):
    o=subprocess.run([J,"--search-profile",fen,"13","0",CH,spec],capture_output=True,text=True).stdout
    import re; m=re.search(r'nodes=(\d+)',o); return int(m.group(1)) if m else 0
for spec,lbl in [("qs_sacs=1","qs_sacs"),("qs_sacs=1,qs_threat_ext=1","sacs+threat")]:
    ratios=[]
    for f in fens:
        n0=nodes(f,"qs_sacs=0"); n1=nodes(f,spec)
        if n0>0: ratios.append(n1/n0)
    ratios.sort()
    print(f"  {lbl:>12} node-ratio d13 : median={statistics.median(ratios):.2f} mean={statistics.mean(ratios):.2f} p90={ratios[int(0.9*len(ratios))]:.2f} max={max(ratios):.2f}")
PY

say ""
say "=== (3) CONVERSION 0440 vs Scan (d${D}, base / qs_sacs / sacs+threat) ==="
for cfg in "qs_sacs=0:base" "qs_sacs=1:sacs" "qs_sacs=1,qs_threat_ext=1:sacsThreat"; do
  spec="${cfg%%:*}"; lbl="${cfg##*:}"
  ( unset JASS_EGDB_PATH; timeout 8000 python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --jass-search-params "$spec" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$W/$DILF" \
      --dump-games-dir "$ART/conv-$lbl" >/tmp/cv-$lbl.log 2>&1 ) || say "  (0440 $lbl interrompu)"
  python3 - "$ART/conv-$lbl" "$W/$DILF" "$lbl" <<'PY' | tee -a "$RES"
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
print(f"  0440 {lbl:>10} : JASS-au-trait={aw/an:.3f} (n={an})" if an else f"  0440 {lbl}: n/a")
PY
done

say ""
say "================= LECTURE (make-or-break briefing) ================="
say "  0440 qs_sacs >> base (vers 0,95) ET node-EBF ~plat (ratio ~1.x) => BAKE : combos↑ SANS explosion 🎉"
say "  0440 ↑ MAIS node-EBF explose (ratio>>1) => relâcher depth0-only trop / resserrer add_sacs => trop cher dans jass."
say "  0440 plat => la sac-quiescence sélective n'est pas la pièce manquante => le gap combos est ailleurs => consigner."
say "  (baseline connue : 0440 base ~0,30 d11 ; Scan 0,95)"
say "==================================================================="
