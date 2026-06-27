#!/usr/bin/env bash
# id: ccx33-0476-champ3-tactique-0440
# description: JUGE 0440 du champion gagnant de 0465 (demande JFC). La recette "tactique" (50% d10 + 50% d12, seeds = combinaisons
# dilf) a produit champion-3-tactique qui BAT egdbmix en SELF-PLAY (vs_base=0.528) -> adopte pilote. Mais vs_base = force
# self-play, PAS la conversion combinaisons. Ici on mesure ce qui compte : sa conversion 0440 vs Scan (eval-pur, depth-fixe d11,
# no-DB) + bootstrap IC95, compare a egdbmix (0.302). Si > 0.35 (hors IC) => le gain self-play de la recette tactique se traduit
# en conversion de combinaisons => premier vrai signe que la diversification-mu seedee-combinaisons + profondeur paie sur la
# cible. Si ~0.30 => gain self-play positionnel sans effet tactique. Lean : build + 1 juge, pas de gen/fit. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0476-champ3-tactique-0440/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-champ3judge; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/cpx62-0465-freshmix-12m/artefacts/champion-3-tactique.pjtw.gz
DILF=data/dilf_combinations.fen
D=11

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable ($SCAN_BIN)"; exit 4; }
say "=== build jass standard (SANS egdb, juge eval-pur) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ3.pjtw" || { say "ABORT: champion-3-tactique absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== juge 0440 : champion-3-tactique vs Scan (DILF complet, d${D}, no-DB) ==="
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ3.pjtw" --scan-bb-size 0 \
    --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-champ3" >"$W/cj.log" 2>&1 || say "  (juge echoue, voir cj.log)"

python3 - "$ART/conv-champ3" "$DILF" <<'PY' | tee -a "$RES"
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=[]; tot=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    tot+=1
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    aw.append(0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0))
n=len(aw)
if not n: print("  conversion 0440 : NA (pas de games)"); sys.exit(0)
m=sum(aw)/n; seed=12345; boots=[]
for _ in range(2000):
    acc=0
    for _ in range(n):
        seed=(1103515245*seed+12345)&0x7fffffff; acc+=aw[seed%n]
    boots.append(acc/n)
boots.sort(); lo=boots[50]; hi=boots[1949]
print(f"  conversion 0440 : champion-3-tactique = {m:.3f} ({sum(aw):.0f}/{n})  IC95=[{lo:.3f},{hi:.3f}]  [games={tot}]")
print(f"  rappels : egdbmix=0.302 [0.25,0.35] ; deep-relabel bootstrap ~0.25-0.29 ; sparring v1=0.279 ; Scan=0.95")
print(f"  => egdbmix 0.302 {'DANS' if lo<=0.302<=hi else 'HORS'} l'IC ; seuil compte >0.35")
PY
say ""; say "================= LECTURE ================="
say "  > 0.35 (egdbmix hors IC) => la recette tactique (seeds combinaisons + 50% d12) convertit MIEUX les combinaisons"
say "       => la diversification-mu PAIE sur la cible 0440 ; on refit cette recette a plein volume + 2e generation autour."
say "  ~ 0.30 => gain self-play positionnel sans effet tactique ; le seedage-combinaisons n'a pas transfere la conversion."
say "=========================================="
