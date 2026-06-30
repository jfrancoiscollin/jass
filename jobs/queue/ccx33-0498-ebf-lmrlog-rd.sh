#!/usr/bin/env bash
# id: ccx33-0498-ebf-lmrlog-rd
# description: CHANTIER EBF #1c (memo v2) — LE DECIDEUR. Le sweep 0497 a montre que les muls LMR-log doux (20/25/30) sont
# a PARITE Elo avec le lineaire (ne perdent pas). Gate v2 = Elo>=baseline (OK) ET EBF baisse. Ici on mesure la 2e moitie :
# R(d) d9/12/15 (= croissance temps/pos = facteur de branchement) sous lmr_formula=1 a chaque mul vs lineaire, champion
# egdbmix eval-pur, MEME corpus que #0 (0495 : baseline EBF_jass=1,69 ; R(15)=jass/scan a d15=2,40). VERDICT : si un mul
# doux baisse l'EBF / R(15) vers <=1 (croisement repousse >=d15) EN restant a parite Elo (0497) => le LMR-log MARCHE
# (meme force + plus de profondeur) => #4 (ext_forcing sur build bas-EBF). Si AUCUN mul ne baisse R(d) => le log ne mord
# pas l'arbre en dames => chantier LMR-log NEGATIF => pivot diagnostic #3 (part eval-noise de l'EBF). Cible ~6%/ply
# (1,69->1,59 => R(15)~1,0). Utilise nps_vs_scan --jass-search-params (PR #320). AUCUN re-entrainement, AUCUN NNUE.
# expected_duration: ~30-45 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-120}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0498-ebf-lmrlog-rd/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
W=/root/cw-ebf1c; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz

preflight_build 1
preflight_note "EBF #1c : R(d) d9/12/15 x4 configs (lineaire + mul20/25/30)" 90
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
B="$W/build"; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb off"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$B/jass"
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { say "ABORT champion absent"; exit 4; }
[ -f "$POS" ] || { say "ABORT corpus 0328 absent"; exit 4; }
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "ABORT Scan indispo (necessaire pour R(15) vs Scan)"; exit 5; }

say "=== CHANTIER EBF #1c — R(d) sous LMR-log (baseline #0 : EBF=1,69 ; R(15)=2,40) ==="
declare -A SPEC=( [linear]="lmr_formula=0" [mul20]="lmr_formula=1,lmr_log_mul=20" [mul25]="lmr_formula=1,lmr_log_mul=25" [mul30]="lmr_formula=1,lmr_log_mul=30" )
for cfg in linear mul20 mul25 mul30; do
  say "--- config=$cfg ($(echo ${SPEC[$cfg]})) ---"
  python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --jass-search-params "${SPEC[$cfg]}" --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 \
      2>&1 | tee "$W/nps-$cfg.log" | tee -a "$RES"
done

say ""; say "=== EBF + R(15) par config (verdict) ==="
python3 - "$W" linear mul20 mul25 mul30 <<'PY' | tee "$ART/VERDICT.txt" | tee -a "$RES"
import sys,re,math
Wd=sys.argv[1]; cfgs=sys.argv[2:]
def parse(cfg):
    rows={}
    for ln in open(f"{Wd}/nps-{cfg}.log",errors='ignore'):
        m=re.match(r'\s*(\d+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)',ln)
        if m: rows[int(m.group(1))]=(float(m.group(2)),float(m.group(3)),float(m.group(4)))
    return rows
print(f"{'config':>8} {'EBF_jass(d9-15)':>16} {'R(15)=j/s@d15':>14} {'vs baseline':>12}")
base=None
for cfg in cfgs:
    r=parse(cfg)
    if 9 not in r or 15 not in r: print(f"{cfg:>8}   (donnees incompletes)"); continue
    ebf=(r[15][0]/r[9][0])**(1/6)
    R15=r[15][2]
    if cfg=='linear': base=(ebf,R15)
    tag=""
    if base and cfg!='linear':
        de=(ebf/base[0]-1)*100; dr=(R15/base[1]-1)*100
        tag=f"EBF {de:+.1f}% R(15) {dr:+.1f}%"
    print(f"{cfg:>8} {ebf:>16.3f} {R15:>14.2f} {tag:>12}")
print()
print("LECTURE : un mul avec EBF NETTEMENT < linear ET R(15) qui chute vers ~1 (croisement repousse >=d15) =>")
print("          mecanisme OK (parite Elo 0497 + EBF baisse) => baker ce mul + #4 (ext_forcing sur build bas-EBF).")
print("          EBF ~ identique au lineaire a tous les muls => le log NE mord PAS l'arbre en dames (les noeuds calmes")
print("          ne dominent peut-etre pas comme en echecs) => chantier LMR-log NEGATIF => pivot diagnostic #3 (eval-noise).")
PY
say "=========================================================="
