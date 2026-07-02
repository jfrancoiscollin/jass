#!/usr/bin/env bash
# id: ccx33-0540-qs-sacs-movetime
# description: TRANSFERT à MOVETIME de la sac-quiescence sélective (complément de 0539 qui teste la profondeur FIXE). Le naïf
# (0537) gagnait à profondeur fixe MAIS était neutre à movetime (explosion 6x mange la profondeur). Le sélectif a un coût
# borné (~1.1-2x) => doit-il transférer ? 0440 vs Scan à MOVETIME 0,3s : base / qs_sacs / qs_sacs+qs_threat_ext. Build depuis
# la branche claude/scan-sac-quiescence. AUCUN NNUE. expected_duration: ~2-3 h.
set -uo pipefail
ART="/root/jass/jobs/results/ccx33-0540-qs-sacs-movetime/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MT=0.3
say "=== transfert movetime sac-quiescence (build branche) ==="
W=/root/jass-sacbranch-mt; rm -rf "$W"
git clone /root/jass "$W" >/tmp/cl.log 2>&1 || { say ABORT clone; exit 4; }
( cd "$W" && git fetch origin claude/scan-sac-quiescence >/tmp/f.log 2>&1 && git checkout -B sb FETCH_HEAD >/tmp/co.log 2>&1 ) || { say ABORT branch; exit 4; }
say "  HEAD : $(cd "$W" && git log --oneline -1|cat)"
cmake -S "$W" -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >/tmp/cm.log 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >/tmp/bl.log 2>&1 || { say "BUILD FAIL"; tail -10 /tmp/bl.log|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >/tmp/s.log 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say ABORT champ; exit 4; }
DILF="$W/data/dilf_combinations.fen"
say "=== 0440 à MOVETIME ${MT}s (base / qs_sacs / sacs+threat) ==="
for cfg in "qs_sacs=0:base" "qs_sacs=1:sacs" "qs_sacs=1,qs_threat_ext=1:sacsThreat"; do
  spec="${cfg%%:*}"; lbl="${cfg##*:}"
  ( unset JASS_EGDB_PATH; timeout 9000 python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --jass-search-params "$spec" --scan-bb-size 0 --movetime "$MT" --pairs 1 --openings-file "$DILF" \
      --dump-games-dir "$ART/conv-$lbl" >/tmp/cv-$lbl.log 2>&1 ) || say "  (0440 $lbl interrompu)"
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
print(f"  0440@mt{__import__('os').environ.get('MT','0.3')} {lbl:>10} : JASS-au-trait={aw/an:.3f} (n={an})" if an else f"  0440 {lbl}: n/a")
PY
done
say ""
say "  LECTURE : qs_sacs @movetime >> base => le sélectif TRANSFÈRE (contrairement au naïf) => BAKE. ~base => coût borné mais gain non-transféré."
