#!/usr/bin/env bash
# id: cpx62-0500-ebf-evalbound
# description: CHANTIER EBF #3 (memo v2, version OUTIL-SEULE zero-risque) — l'EBF est-il EVAL-BOUND ou MECANIQUE ? #1 a
# montre que la forme LMR ne baisse pas l'EBF. Reste a savoir POURQUOI l'EBF (1,58) est coince. Hypothese memo : eval
# bruitee/faible -> mauvais move-ordering -> re-recherches/churn -> arbre touffu. TEST DIRECT sans instrumenter : mesurer
# R(d)/EBF avec une eval FAIBLE (hc handcrafted, defaut) vs FORTE (champion egdbmix). Si meilleure eval => EBF NETTEMENT
# plus bas => l'eval pilote l'EBF (EVAL-BOUND) => le levier EBF restant = un objectif d'eval-STABILITE (!= 0440 tactique).
# Si EBF ~identique hc vs egdbmix => l'EBF est MECANIQUE/structurel aux dames => la recherche n'est PAS le levier =>
# clore le chantier EBF et revenir au gen/eval. Meme corpus/methode que #0/#1c. AUCUN re-entrainement, AUCUN NNUE.
# expected_duration: ~20-30 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-90}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0500-ebf-evalbound/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
W=/root/cw-ebf3; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz

preflight_build 1
preflight_note "EBF #3 : R(d) hc vs egdbmix (2 evals) d9/12/15" 60
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
[ -x "$SCAN_BIN" ] || { say "ABORT Scan indispo"; exit 5; }

say "=== CHANTIER EBF #3 — EBF eval-bound ? (hc faible vs egdbmix fort) ==="
# eval hc = defaut (pas de --jass-pattern) ; eval egdbmix = --jass-pattern champ
say "--- eval=hc (handcrafted, defaut faible) ---"
python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
    --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee "$W/nps-hc.log" | tee -a "$RES"
say "--- eval=egdbmix (champion fort) ---"
python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee "$W/nps-egdbmix.log" | tee -a "$RES"

say ""; say "=== VERDICT : EBF vs qualite d'eval ==="
python3 - "$W" hc egdbmix <<'PY' | tee "$ART/VERDICT.txt" | tee -a "$RES"
import sys,re
Wd=sys.argv[1]; evals=sys.argv[2:]
def parse(e):
    rows={}
    for ln in open(f"{Wd}/nps-{e}.log",errors='ignore'):
        m=re.match(r'\s*(\d+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)',ln)
        if m: rows[int(m.group(1))]=(float(m.group(2)),float(m.group(3)),float(m.group(4)))
    return rows
print(f"{'eval':>10} {'EBF_jass(d9-15)':>16} {'R(15)=j/s@d15':>14}")
res={}
for e in evals:
    r=parse(e)
    if 9 in r and 15 in r:
        ebf=(r[15][0]/r[9][0])**(1/6); res[e]=(ebf,r[15][2])
        print(f"{e:>10} {ebf:>16.3f} {r[15][2]:>14.2f}")
    else: print(f"{e:>10}  (incomplet)")
print()
if 'hc' in res and 'egdbmix' in res:
    de=(res['egdbmix'][0]/res['hc'][0]-1)*100
    print(f"  delta EBF (egdbmix vs hc) = {de:+.1f}%")
    print("  LECTURE : egdbmix EBF NETTEMENT < hc (>~5-8%) => l'EBF est EVAL-BOUND (meilleure eval = meilleur ordering =")
    print("            arbre plus petit) => le levier EBF restant = OBJECTIF D'EVAL-STABILITE (!= 0440) => relie EBF et eval.")
    print("            EBF ~ identique => l'EBF est MECANIQUE/structurel aux dames => la recherche n'est PAS le levier =>")
    print("            CLORE le chantier EBF, le gap movetime n'est pas adressable par la recherche => retour gen/eval.")
PY
say "=================================================="
